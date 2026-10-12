"""Two-player BO1/BO3 orchestration. No dependency on any game implementation."""
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
from arena.core.bot_runner import BotError, BotProcess
from arena.core.plugin import IllegalAction


def snapshot_hash(state: dict) -> str:
    return sha256(json.dumps(state, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class MatchRunner:
    def __init__(self, registry, bots, process_factory=BotProcess):
        self.registry, self.bots, self.process_factory = registry, bots, process_factory

    async def run_game(self, game_id, version, game_instance_id, seed, side_map, bot_names, on_frame=None, move_delay_ms=0):
        manifest, plugin = self.registry.get(game_id, version)
        state = plugin.create({'gameInstanceId': game_instance_id}, seed, ('A', 'B'))
        initial_status = plugin.status(state)
        initial = plugin.serialize_state(state)
        catalog = self.bots.by_id
        replay = {'gameInstanceId': game_instance_id, 'gameId': game_id, 'gameVersion': version,
                  'seed': seed, 'botNames': bot_names, 'sideMapping': side_map,
                  'initialState': initial, 'renderMetadata': plugin.render_metadata(state),
                  'frames': [], 'botLogs': {}, 'botArtifacts': {
                      slot: {k: v for k, v in catalog[name][0].items()
                             if k in ('name','team','version','artifactSha256','source')}
                      for slot, name in bot_names.items()}, 'botDigests': {
                      slot: sha256(self.bots.path(name).read_bytes()).hexdigest() for slot, name in bot_names.items()}}
        if on_frame:
            on_frame(replay)
        processes = {}
        forfeit = None
        result = initial_status
        try:
            if not result.terminal:
                for side, slot in side_map.items():
                    processes[side] = self.process_factory(self.bots.path(bot_names[slot]), seed)
                    try:
                        await processes[side].start()
                    except BotError as exc:
                        forfeit = (side, exc)
                        break
            while not result.terminal and forfeit is None:
                side, ply = result.turn, result.ply
                request = {'type': 'observation', 'protocolVersion': '1.0',
                           'requestId': f'{game_instance_id}:turn-{ply}:{side}', 'turnId': ply,
                           'gameId': game_id, 'gameVersion': version, 'playerId': side,
                           'deadlineMs': 500, 'seed': seed, 'observation': plugin.observe(state, side)}
                try:
                    action = await processes[side].decide(request)
                    step = plugin.step(state, side, action)
                    state = step.state
                except BotError as exc:
                    forfeit = (side, exc)
                    break
                except IllegalAction as exc:
                    forfeit = (side, BotError('ILLEGAL_ACTION', str(exc)))
                    break
                result = plugin.status(state)
                snap = plugin.serialize_state(state)
                replay['frames'].append({'seq': len(replay['frames']) + 1, 'ply': result.ply,
                                         'playerId': side, 'action': action, 'events': step.events,
                                         'state': snap, 'stateHash': snapshot_hash(snap)})
                if on_frame:
                    on_frame(replay)
                if move_delay_ms and not result.terminal:
                    await asyncio.sleep(move_delay_ms / 1000)
            if forfeit:
                loser, error = forfeit
                winner = next(p for p in ('A', 'B') if p != loser)
                result_json = {'turn': result.turn, 'ply': result.ply, 'winner': winner, 'reason': 'BOT_FORFEIT',
                               'details': {'loser': loser, 'errorCode': error.code, 'message': error.message}}
                snap = plugin.serialize_state(state)
                replay['frames'].append({'seq': len(replay['frames']) + 1, 'ply': result.ply,
                                         'playerId': loser, 'action': None,
                                         'events': [{'type': 'BOT_FORFEIT', **result_json['details']}],
                                         'state': snap, 'stateHash': snapshot_hash(snap)})
            else:
                result_json = asdict(result)
        finally:
            for side, process in processes.items():
                await process.close()
                replay['botLogs'][side] = process.logs()
        if result_json['winner'] not in side_map:
            raise RuntimeError('Plugin must return exactly one registered winner')
        replay['result'] = {**result_json, 'plies': result_json['ply'],
                            'winnerSlot': side_map[result_json['winner']],
                            'winnerBot': bot_names[side_map[result_json['winner']]]}
        if on_frame:
            on_frame(replay)
        return replay

    async def run_match(self, match_id, game_id, bot_a, bot_b, format, seed, on_progress=None, version=None, move_delay_ms=0):
        manifest, _ = self.registry.get(game_id, version)
        version = manifest['gameVersion']
        names, scores = {'botA': bot_a, 'botB': bot_b}, {'botA': 0, 'botB': 0}
        match = {'matchId': match_id, 'gameId': game_id, 'gameVersion': version,
                 'format': format, 'seed': seed, 'botNames': names, 'scores': scores,
                 'status': 'RUNNING', 'games': [], 'replayRenderer': manifest.get('replayRenderer')}
        target = 1 if format == 'BO1' else 2
        for number in range(1, 2 * target):
            swap = number == 2 or (number == 3 and (sha256(f'{seed}:side:3'.encode()).digest()[-1] & 1))
            mapping = {'A': 'botB' if swap else 'botA', 'B': 'botA' if swap else 'botB'}
            def game_progress(current):
                if match['games'] and match['games'][-1]['gameInstanceId'] == current['gameInstanceId']:
                    match['games'][-1] = current
                else:
                    match['games'].append(current)
                if on_progress:
                    on_progress(match)
            game = await self.run_game(game_id, version, f'{match_id}:game-{number}', seed, mapping, names,
                                       game_progress, move_delay_ms)
            scores[game['result']['winnerSlot']] += 1
            if on_progress:
                on_progress(match)
            if max(scores.values()) == target:
                break
        slot = max(scores, key=scores.get)
        match.update(status='COMPLETED', winnerSlot=slot, winnerBot=names[slot], reason=match['games'][-1]['result']['reason'])
        return match
