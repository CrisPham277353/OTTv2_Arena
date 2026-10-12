import asyncio
from hashlib import sha256
import json
from pathlib import Path
import pytest
from arena.bootstrap import ROOT, build_bots, build_registry
from arena.core.bot_runner import BotCatalog, BotProcess, BotError
from arena.core.match_runner import MatchRunner, snapshot_hash
from arena.core.plugin import GameStatus, StepResult
from arena.core.registry import PluginRegistry


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize('mode,code', [('bad_json','PROTOCOL_ERROR'), ('illegal','ILLEGAL_ACTION'),
    ('crash','BOT_CRASH'), ('timeout','TIMEOUT'), ('wrong_id','PROTOCOL_ERROR'),
    ('long_line','OUTPUT_LIMIT'), ('stdout_flood','OUTPUT_LIMIT'), ('bad_turn','PROTOCOL_ERROR'), ('stderr_flood','OUTPUT_LIMIT')])
def test_bot_forfeit(tmp_path, mode, code):
    script = tmp_path / f'{mode}.py'
    script.write_text((ROOT / 'tests/fixtures/fault_bot.py').read_text())
    (tmp_path / 'manifest.json').write_text(json.dumps([{'id':'fault', 'script':script.name},
       {'id':'ok', 'script':'ok.py'}]))
    (tmp_path / 'ok.py').write_text((ROOT / 'tests/fixtures/fault_bot.py').read_text())
    catalog = BotCatalog(tmp_path)
    r = run(MatchRunner(build_registry(), catalog).run_match('fixed', 'ottv2', 'fault', 'ok', 'BO1', 42))
    result = r['games'][0]['result']
    assert result['reason'] == 'BOT_FORFEIT' and result['winner'] == 'B'
    assert result['details']['errorCode'] == code
    assert r['scores'] == {'botA':0, 'botB':1}


@pytest.mark.parametrize('a,b', [('random','capture_greedy'), ('capture_greedy','goal_rush'), ('goal_rush','random')])
def test_real_bots_and_deterministic_replay(a, b):
    runner = MatchRunner(build_registry(), build_bots())
    first = run(runner.run_match('deterministic', 'ottv2', a, b, 'BO1', 42))
    second = run(runner.run_match('deterministic', 'ottv2', a, b, 'BO1', 42))
    assert first == second
    game = first['games'][0]
    assert game['result']['reason'] != 'BOT_FORFEIT' and game['frames']
    assert game['result']['plies'] <= 300
    for frame in game['frames']:
        assert snapshot_hash(frame['state']) == frame['stateHash']


def test_bo3_side_mapping_and_stop():
    r = run(MatchRunner(build_registry(), build_bots()).run_match('bo3', 'ottv2', 'capture_greedy', 'goal_rush', 'BO3', 42))
    assert r['games'][0]['sideMapping'] == {'A':'botA', 'B':'botB'}
    assert r['games'][1]['sideMapping'] == {'A':'botB', 'B':'botA'}
    assert len(r['games']) in (2, 3) and max(r['scores'].values()) == 2
    if len(r['games']) == 3:
        swap = sha256(b'42:side:3').digest()[-1] & 1
        assert r['games'][2]['sideMapping']['A'] == ('botB' if swap else 'botA')


class DummyGamePlugin:
    def create(self, config, seed, players): return {'turn':'A', 'n':0}
    def legal_actions(self, state, player): return [{'type':'PING'}]
    def observe(self, state, player): return {'legalActions':self.legal_actions(state, player)}
    def step(self, state, player, action):
        assert action == {'type':'PING'}
        state = {**state, 'n':state['n'] + 1, 'turn':'B' if player == 'A' else 'A'}
        return StepResult(state, [{'type':'PINGED'}])
    def status(self, state):
        return GameStatus(state['turn'], state['n'], 'B' if state['n'] == 2 else None, 'PING_WIN' if state['n'] == 2 else None)
    def serialize_state(self, state): return state.copy()
    def render_metadata(self, state): return {'renderer':'dummy'}


def test_dummy_plugin_through_same_runner(tmp_path):
    registry = PluginRegistry()
    registry.register({'gameId':'dummy', 'gameVersion':'1', 'pluginApi':'1.0', 'players':2,
                       'turnMode':'alternating', 'resultMode':'winner_only'}, DummyGamePlugin())
    (tmp_path / 'ok.py').write_text((ROOT / 'tests/fixtures/fault_bot.py').read_text())
    (tmp_path / 'manifest.json').write_text('[{"id":"ok", "script":"ok.py"}]')
    r = run(MatchRunner(registry, BotCatalog(tmp_path)).run_match('dummy-match','dummy','ok','ok','BO1',7))
    assert r['winnerSlot'] == 'botB' and r['reason'] == 'PING_WIN'
    assert len(r['games'][0]['frames']) == 2


def test_catalog_rejects_path_escape(tmp_path):
    (tmp_path / 'manifest.json').write_text('[{"id":"escape", "script":"../outside.py"}]')
    with pytest.raises(ValueError): BotCatalog(tmp_path)


def test_bot_process_persistent_and_cleanup():
    async def check():
        p = BotProcess(build_bots().path('random'), 42)
        await p.start()
        pid = p.process.pid
        for i in range(3):
            assert await p.decide({'type':'observation', 'requestId':str(i), 'turnId':i,
                'observation':{'legalActions':[{'type':'TEST'}]}}) == {'type':'TEST'}
            assert p.process.pid == pid and p.process.returncode is None
        await p.close()
        assert p.process.returncode is not None
    run(check())


def test_dummy_bo3_reaches_game_three(tmp_path):
    registry = PluginRegistry()
    registry.register({'gameId':'dummy', 'gameVersion':'1', 'pluginApi':'1.0', 'players':2,
                       'turnMode':'alternating', 'resultMode':'winner_only'}, DummyGamePlugin())
    (tmp_path / 'ok.py').write_text((ROOT / 'tests/fixtures/fault_bot.py').read_text())
    (tmp_path / 'manifest.json').write_text('[{"id":"ok", "script":"ok.py"}]')
    r = run(MatchRunner(registry, BotCatalog(tmp_path)).run_match('dummy-bo3','dummy','ok','ok','BO3',7))
    assert len(r['games']) == 3 and sorted(r['scores'].values()) == [1,2]
    swap = sha256(b'7:side:3').digest()[-1] & 1
    assert r['games'][2]['sideMapping'] == {'A':'botB' if swap else 'botA','B':'botA' if swap else 'botB'}


def test_posix_cleanup_includes_children(tmp_path):
    import os
    import sys
    if os.name != 'posix':
        pytest.skip('POSIX process-group behavior')
    child_pid = tmp_path / 'child.pid'
    script = tmp_path / 'parent.py'
    script.write_text('import subprocess,sys,time\nfrom pathlib import Path\n'
        "p=subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])\n"
        f'Path({str(child_pid)!r}).write_text(str(p.pid))\ntime.sleep(60)\n')
    async def check():
        p = BotProcess(script,42)
        await p.start()
        for _ in range(100):
            if child_pid.exists(): break
            await asyncio.sleep(.01)
        assert child_pid.exists()
        pid = int(child_pid.read_text())
        await p.close()
        for _ in range(100):
            stat = Path(f'/proc/{pid}/stat')
            try:
                if stat.read_text().split()[2] == 'Z':
                    break
            except (FileNotFoundError, ProcessLookupError):
                break  # Reaped between filesystem checks is successful cleanup.
            await asyncio.sleep(.01)
        else:
            pytest.fail('Bot child process survived group cleanup')
    run(check())
