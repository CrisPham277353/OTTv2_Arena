"""OTT v2 1.0 rules. Pure Python, no UI, process, database or HTTP dependency."""
from copy import deepcopy
from hashlib import sha256
import json
from arena.core.plugin import GameStatus, IllegalAction, StepResult
from arena.games.ottv2.state import Piece, State

BEATS = {'D': 'K', 'K': 'L', 'L': 'D'}
TARGETS = {'A': 'i9', 'B': 'a1'}
INITIAL_A = {'a1': 'D', 'c1': 'L', 'e1': 'K', 'g1': 'D', 'i1': 'L',
             'b2': 'K', 'd2': 'D', 'f2': 'L', 'h2': 'K'}


def xy(at: str) -> tuple[int, int]:
    if not isinstance(at, str) or len(at) != 2 or at[0] not in 'abcdefghi' or at[1] not in '123456789':
        raise IllegalAction(f'Invalid coordinate: {at!r}')
    return ord(at[0]) - 97, int(at[1]) - 1


def coord(x: int, y: int) -> str:
    return chr(97 + x) + str(y + 1)


def distance(a: str, b: str) -> int:
    ax, ay = xy(a)
    bx, by = xy(b)
    return max(abs(ax - bx), abs(ay - by))


def opponent(side: str) -> str:
    return 'B' if side == 'A' else 'A'


def state_key(state: State) -> str:
    return json.dumps([sorted((at, p.side, p.kind) for at, p in state.board.items()), state.turn], separators=(',', ':'))


def adjudicate(state: State, trigger: str) -> tuple[str, dict]:
    metrics = {}
    for side in ('A', 'B'):
        ds = [distance(at, TARGETS[side]) for at, p in state.board.items() if p.side == side]
        metrics[side] = {'alive': len(ds), 'nearGoal': sum(d <= 2 for d in ds),
                         'minDistance': min(ds, default=9), 'totalDistance': sum(ds)}
    for criterion, larger in [('alive', True), ('nearGoal', True), ('minDistance', False), ('totalDistance', False)]:
        a, b = metrics['A'][criterion], metrics['B'][criterion]
        if a != b:
            winner = 'A' if (a > b) == larger else 'B'
            return winner, {'trigger': trigger, 'metrics': metrics, 'criterion': criterion}
    # Exact concatenation with no delimiter; final SHA256 bit, 0=A, 1=B.
    source = f'{state.seed}{state.game_instance_id}{trigger}'
    digest = sha256(source.encode('utf-8')).hexdigest()
    bit = int(digest[-1], 16) & 1
    return ('B' if bit else 'A'), {'trigger': trigger, 'metrics': metrics, 'criterion': 'sha256',
                                'hashInput': source, 'sha256': digest, 'bit': bit}


class OTTPlugin:
    def create(self, config: dict, seed: int, players: tuple[str, str]) -> State:
        if players != ('A', 'B') or set(config) - {'gameInstanceId'}:
            raise ValueError('OTT v2 uses players A/B and its fixed 1.0 rules')
        board = {at: Piece('A', kind) for at, kind in INITIAL_A.items()}
        for at, kind in INITIAL_A.items():
            x, y = xy(at)
            board[coord(8 - x, 8 - y)] = Piece('B', kind)
        state = State(board, seed, config.get('gameInstanceId', 'game-1'))
        state.repetitions[state_key(state)] = 1
        return state

    def legal_actions(self, state: State, player: str) -> list[dict]:
        if state.winner or player not in ('A', 'B'):
            return []
        actions = []
        for at, piece in sorted(state.board.items()):
            if piece.side != player:
                continue
            x, y = xy(at)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if (dx == dy == 0) or not (0 <= x + dx < 9 and 0 <= y + dy < 9):
                        continue
                    dst = coord(x + dx, y + dy)
                    q = state.board.get(dst)
                    if q is None or (q.side != player and BEATS[piece.kind] == q.kind):
                        actions.append({'type': 'MOVE', 'from': at, 'to': dst})
        return actions

    def status(self, state: State) -> GameStatus:
        # Initial/custom blocked boards lose before a bot is invoked.
        if not state.winner and not self.legal_actions(state, state.turn):
            state.winner, state.reason = opponent(state.turn), 'NO_LEGAL_MOVES'
        return GameStatus(state.turn, state.ply, state.winner, state.reason, deepcopy(state.details))

    def _record_progress(self, state: State, player: str, captured: bool):
        pass

    def _capture_victory(self, state: State, player: str) -> str | None:
        if any(not any(p.side == opponent(player) and p.kind == k for p in state.board.values()) for k in BEATS):
            return 'TYPE_ELIMINATED'
        return None

    def _stalled_player(self, state: State, player: str) -> bool:
        return False

    def _adjudication_trigger(self, state: State) -> str | None:
        if state.repetitions[state_key(state)] >= 3:
            return 'THREEFOLD_REPETITION'
        return 'PLY_LIMIT' if state.ply >= 300 else None

    def step(self, state: State, player: str, action: dict) -> StepResult:
        if self.status(state).terminal or player != state.turn:
            raise IllegalAction('Game ended or wrong player')
        if not isinstance(action, dict) or set(action) != {'type', 'from', 'to'} or action.get('type') != 'MOVE':
            raise IllegalAction('Expected exactly {type: MOVE, from, to}')
        src, dst = action['from'], action['to']
        xy(src)
        xy(dst)
        p, q = state.board.get(src), state.board.get(dst)
        if p is None or p.side != player or distance(src, dst) != 1:
            raise IllegalAction('Move must use your piece and travel one adjacent square')
        if q and (q.side == player or BEATS[p.kind] != q.kind):
            raise IllegalAction('Destination is blocked by this piece')
        events = []
        if q:
            events.append({'type': 'PIECE_CAPTURED', 'at': dst, 'side': q.side, 'kind': q.kind})
        del state.board[src]
        state.board[dst] = p
        state.ply += 1
        state.last_move = dict(action, side=player, kind=p.kind, captured={'side': q.side, 'kind': q.kind} if q else None)
        events.append({'type': 'PIECE_MOVED', **state.last_move})
        self._record_progress(state, player, q is not None)
        if dst == TARGETS[player]:
            state.winner, state.reason = player, 'GOAL_REACHED'
        elif q and (capture_reason := self._capture_victory(state, player)):
            state.winner, state.reason = player, capture_reason
        else:
            state.turn = opponent(player)
            if not self.legal_actions(state, state.turn):
                state.winner, state.reason = player, 'NO_LEGAL_MOVES'
            elif self._stalled_player(state, player):
                state.winner, state.reason = opponent(player), 'NO_PROGRESS'
            else:
                key = state_key(state)
                state.repetitions[key] = state.repetitions.get(key, 0) + 1
                trigger = self._adjudication_trigger(state)
                if trigger:
                    state.winner, state.details = adjudicate(state, trigger)
                    state.reason = 'ADJUDICATED'
        if state.winner:
            events.append({'type': 'GAME_ENDED', 'winner': state.winner, 'reason': state.reason, 'details': deepcopy(state.details)})
        return StepResult(state, events)

    def observe(self, state: State, player: str) -> dict:
        return {'side': player, 'target': TARGETS[player], 'ply': state.ply,
                'pieces': self.serialize_state(state)['pieces'], 'lastMove': deepcopy(state.last_move),
                'legalActions': self.legal_actions(state, player)}

    def serialize_state(self, state: State) -> dict:
        return {'pieces': [{'at': at, 'side': p.side, 'kind': p.kind} for at, p in sorted(state.board.items())],
                'sideToMove': state.turn, 'ply': state.ply, 'winner': state.winner,
                'reason': state.reason, 'details': deepcopy(state.details), 'lastMove': deepcopy(state.last_move)}

    def render_metadata(self, state: State) -> dict:
        return {'size': 9, 'columns': list('abcdefghi'), 'targets': TARGETS.copy(),
                'pieceLabels': {'D': 'Đấm', 'L': 'Lá', 'K': 'Kéo'}}
