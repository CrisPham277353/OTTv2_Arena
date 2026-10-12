"""OTT v2 1.1.0: explicit army victory and deterministic anti-stalling rules."""
from dataclasses import dataclass, field
from copy import deepcopy
from arena.games.ottv2.engine import OTTPlugin, TARGETS, opponent, distance, state_key
from arena.games.ottv2.state import State

NO_CAPTURE_LIMIT = 50  # plies, both teams combined
NO_PROGRESS_LIMIT = 15  # own turns, each side separately


@dataclass
class CompetitiveState(State):
    no_capture_plies: int = 0
    no_progress_turns: dict[str, int] = field(default_factory=lambda: {'A':0, 'B':0})
    best_goal_distance: dict[str, int] = field(default_factory=dict)


def nearest_goal(state, side):
    return min((distance(at, TARGETS[side]) for at, p in state.board.items() if p.side == side), default=9)


class CompetitiveOTTPlugin(OTTPlugin):
    def create(self, config, seed, players):
        base = super().create(config, seed, players)
        return CompetitiveState(**vars(base), best_goal_distance={s:nearest_goal(base,s) for s in ('A','B')})

    def _record_progress(self, state, player, captured):
        if not state.best_goal_distance:
            raise ValueError('Competitive state must record initial best goal distances')
        current = nearest_goal(state, player)
        improved = current < state.best_goal_distance[player]
        state.best_goal_distance[player] = min(current, state.best_goal_distance[player])
        state.no_capture_plies = 0 if captured else state.no_capture_plies + 1
        state.no_progress_turns[player] = 0 if captured or improved else state.no_progress_turns[player] + 1

    def _capture_victory(self, state, player):
        # Goal retains highest priority; total elimination precedes type elimination.
        if not any(p.side == opponent(player) for p in state.board.values()):
            return 'ARMY_ELIMINATED'
        return super()._capture_victory(state, player)

    def _stalled_player(self, state, player):
        if state.no_progress_turns[player] >= NO_PROGRESS_LIMIT:
            state.details = {'loser':player, 'ownTurnsWithoutProgress':state.no_progress_turns[player],
                             'limit':NO_PROGRESS_LIMIT, 'bestGoalDistance':state.best_goal_distance.copy(),
                             'noProgressTurns':state.no_progress_turns.copy()}
            return True
        return False

    def _adjudication_trigger(self, state):
        if state.repetitions[state_key(state)] >= 3:
            return 'THREEFOLD_REPETITION'
        if state.no_capture_plies >= NO_CAPTURE_LIMIT:
            return 'NO_CAPTURE_LIMIT'
        return 'PLY_LIMIT' if state.ply >= 300 else None

    def step(self, state, player, action):
        result = super().step(state, player, action)
        if state.reason == 'ADJUDICATED':
            state.details.update(noCapturePlies=state.no_capture_plies,
                                 noProgressTurns=state.no_progress_turns.copy(),
                                 bestGoalDistance=state.best_goal_distance.copy())
            # Snapshot/event agree; events are copied in the base engine.
            result.events[-1]['details'] = deepcopy(state.details)
        return result

    def pressure(self, state):
        return {'noCapturePlies':state.no_capture_plies, 'noCaptureLimit':NO_CAPTURE_LIMIT,
                'noProgressTurns':state.no_progress_turns.copy(), 'noProgressLimit':NO_PROGRESS_LIMIT,
                'bestGoalDistance':state.best_goal_distance.copy()}

    def observe(self, state, player):
        return {**super().observe(state,player), 'antiStall':self.pressure(state)}

    def serialize_state(self, state):
        return {**super().serialize_state(state), 'antiStall':self.pressure(state)}

    def render_metadata(self, state):
        return {**super().render_metadata(state), 'rules':{'version':'1.1.0', 'armyVictory':True,
                'typeVictory':True, 'noCaptureLimit':NO_CAPTURE_LIMIT, 'noProgressLimit':NO_PROGRESS_LIMIT,
                'repetitionLimit':3, 'plyLimit':300},
                'ruleSummary':[
                    'A vào i9 hoặc B vào a1 thắng. Ăn hết toàn bộ quân hoặc một loại D/L/K của đối phương cũng thắng.',
                    '15 lượt riêng liên tiếp không ăn quân và không lập khoảng cách gần đích mới: bên đó thua.',
                    '50 lượt liên tiếp không ăn quân, lặp cùng bàn + lượt 3 lần hoặc đạt 300 lượt: phân xử, không hòa.',
                    'Phân xử: số quân sống, quân cách đích ≤2, khoảng cách nhỏ nhất, tổng khoảng cách; cuối cùng SHA256 seed/ID/lý do.'
                ]}
