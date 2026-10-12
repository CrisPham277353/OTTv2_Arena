import hashlib
import random
from collections import Counter
import pytest
from arena.core.plugin import IllegalAction
from arena.games.ottv2.engine import OTTPlugin, INITIAL_A, adjudicate, coord, state_key, xy
from arena.games.ottv2.state import Piece, State

P = OTTPlugin()


def board(items, **kwargs):
    return State({at: Piece(side, kind) for at, side, kind in items}, **kwargs)


def move(src='d4', dst='e5'):
    return {'type': 'MOVE', 'from': src, 'to': dst}


def test_initial_distribution_and_rotation():
    s = P.create({}, 42, ('A', 'B'))
    assert len(s.board) == 18
    assert not P.status(s).terminal
    for side in ('A', 'B'):
        assert Counter(p.kind for p in s.board.values() if p.side == side) == {'D': 3, 'L': 3, 'K': 3}
    for at, kind in INITIAL_A.items():
        assert s.board[at] == Piece('A', kind)
        x, y = xy(at)
        assert s.board[coord(8-x, 8-y)] == Piece('B', kind)
    assert s.repetitions[state_key(s)] == 1


def test_empty_diagonal_move():
    s = board([('d4', 'A', 'D'), ('i8', 'B', 'L')])
    result = P.step(s, 'A', move())
    assert result.state.board['e5'] == Piece('A', 'D')
    assert 'd4' not in s.board and s.ply == 1 and s.turn == 'B'
    assert not s.winner  # missing types alone do not win without capture


def test_capture_d_beats_k():
    s = board([('d4', 'A', 'D'), ('e5', 'B', 'K'), ('h8', 'B', 'K'), ('i8', 'B', 'L'), ('h9', 'B', 'D')])
    events = P.step(s, 'A', move()).events
    assert len(s.board) == 4 and s.board['e5'] == Piece('A', 'D')
    assert events[0]['type'] == 'PIECE_CAPTURED' and not s.winner


@pytest.mark.parametrize('kind,side', [('L', 'B'), ('D', 'B'), ('K', 'A')])
def test_blocked_capture(kind, side):
    s = board([('d4', 'A', 'D'), ('e5', side, kind), ('i8', 'B', 'K')])
    before = P.serialize_state(s)
    with pytest.raises(IllegalAction):
        P.step(s, 'A', move())
    assert P.serialize_state(s) == before


@pytest.mark.parametrize('dst', ['f6', 'j5', 'e0', 'd4', 'e10', None])
def test_invalid_distance_and_bounds(dst):
    s = board([('d4', 'A', 'D'), ('i8', 'B', 'L')])
    with pytest.raises(IllegalAction):
        P.step(s, 'A', move(dst=dst))


@pytest.mark.parametrize('side,src,dst', [('A', 'h8', 'i9'), ('B', 'b2', 'a1')])
def test_goal_reached(side, src, dst):
    s = board([(src, side, 'D'), ('e5', 'B' if side == 'A' else 'A', 'L')], turn=side)
    P.step(s, side, move(src, dst))
    assert s.winner == side and s.reason == 'GOAL_REACHED'


def test_last_type_eliminated():
    s = board([('d4', 'A', 'D'), ('e5', 'B', 'K'), ('i8', 'B', 'L'), ('h9', 'B', 'D')])
    P.step(s, 'A', move())
    assert (s.winner, s.reason) == ('A', 'TYPE_ELIMINATED')


def test_goal_has_priority_over_type():
    s = board([('h8', 'A', 'D'), ('i9', 'B', 'K')])
    P.step(s, 'A', move('h8', 'i9'))
    assert s.reason == 'GOAL_REACHED'


def test_no_legal_moves_initial():
    s = board([('a1', 'A', 'D'), ('a2', 'B', 'L'), ('b1', 'B', 'D'), ('b2', 'B', 'L')])
    assert P.legal_actions(s, 'A') == []
    assert (P.status(s).winner, s.reason) == ('B', 'NO_LEGAL_MOVES')


def test_no_legal_moves_after_move():
    s = board([('a1', 'B', 'D'), ('a2', 'A', 'L'), ('b1', 'A', 'D'), ('c3', 'A', 'L')])
    P.step(s, 'A', move('c3', 'b2'))
    assert (s.winner, s.reason) == ('A', 'NO_LEGAL_MOVES')


def test_threefold_board_and_side():
    s = board([('d4', 'A', 'D'), ('h8', 'B', 'L')])
    s.repetitions[state_key(s)] = 1
    sequence = [('d4', 'e4'), ('h8', 'g8'), ('e4', 'd4'), ('g8', 'h8')]
    for _ in range(2):
        for src, dst in sequence:
            P.step(s, s.turn, move(src, dst))
    assert s.ply == 8 and s.reason == 'ADJUDICATED' and s.winner in ('A', 'B')
    assert s.details['trigger'] == 'THREEFOLD_REPETITION'
    s.turn = 'B'
    assert s.repetitions.get(state_key(s), 0) == 0


def test_300_plies():
    s = board([('d4', 'A', 'D'), ('h8', 'B', 'L')], ply=299)
    P.step(s, 'A', move())
    assert s.ply == 300 and s.reason == 'ADJUDICATED' and s.winner in ('A', 'B')
    assert s.details['trigger'] == 'PLY_LIMIT'


@pytest.mark.parametrize('items,criterion,winner', [
    ([('a2','A','D'), ('b2','A','L'), ('i8','B','D')], 'alive', 'A'),
    ([('g7','A','D'), ('i8','B','D')], 'nearGoal', 'A'),
    ([('d4','A','D'), ('i8','B','D')], 'minDistance', 'A'),
    ([('e5','A','D'), ('d4','A','L'), ('e5','B','D'), ('i8','B','L')], 'totalDistance', 'A'),
])
def test_adjudication_criteria(items, criterion, winner):
    # Use different squares for the two e5 pieces in total-distance case.
    if criterion == 'totalDistance':
        items[2] = ('e4', 'B', 'D')
    s = board(items)
    actual, details = adjudicate(s, 'PLY_LIMIT')
    assert actual == winner and details['criterion'] == criterion


def test_hash_tiebreak_is_exact_and_repeatable():
    s = board([('a2', 'A', 'D'), ('i8', 'B', 'D')], seed=17, game_instance_id='fixed-id')
    winner, d = adjudicate(s, 'PLY_LIMIT')
    digest = hashlib.sha256(b'17fixed-idPLY_LIMIT').hexdigest()
    assert d['criterion'] == 'sha256' and d['sha256'] == digest
    assert winner == ('B' if int(digest[-1], 16) & 1 else 'A')
    assert adjudicate(s, 'PLY_LIMIT') == (winner, d)


def test_wrong_side_terminal_and_schema():
    s = P.create({}, 42, ('A', 'B'))
    with pytest.raises(IllegalAction): P.step(s, 'B', move())
    with pytest.raises(IllegalAction): P.step(s, 'A', {'type': 'PASS'})
    s.winner = 'A'
    with pytest.raises(IllegalAction): P.step(s, 'A', move())


def test_playout_invariants():
    for seed in range(10):
        s = P.create({}, seed, ('A', 'B'))
        rng = random.Random(seed)
        while not P.status(s).terminal:
            action = rng.choice(P.legal_actions(s, s.turn))
            before = len(s.board)
            captured = action['to'] in s.board
            P.step(s, s.turn, action)
            assert len(s.board) == before - int(captured)
            assert len(P.serialize_state(s)['pieces']) == len(s.board)
            assert s.ply <= 300
        assert s.winner in ('A', 'B') and s.reason != 'DRAW'


@pytest.mark.parametrize('items,criterion', [
    ([('a2','A','D'), ('b2','A','L'), ('i8','B','D')], 'alive'),
    ([('g7','A','D'), ('i8','B','D')], 'nearGoal'),
    ([('d4','A','D'), ('i8','B','D')], 'minDistance'),
    ([('e5','A','D'), ('d4','A','L'), ('e4','B','D'), ('i8','B','L')], 'totalDistance'),
])
def test_adjudication_reverse_side_symmetry(items, criterion):
    rotated = [(coord(8-xy(at)[0],8-xy(at)[1]), 'B' if side == 'A' else 'A', kind) for at,side,kind in items]
    winner, details = adjudicate(board(rotated), 'PLY_LIMIT')
    assert winner == 'B' and details['criterion'] == criterion


def test_initial_fixture_matches_engine():
    import json
    from arena.bootstrap import ROOT
    fixture = json.loads((ROOT/'arena/games/ottv2/test-data/initial-state.json').read_text())
    s = P.create({},42,('A','B'))
    assert fixture == {'state':P.serialize_state(s), 'metadata':P.render_metadata(s)}
    assert json.loads((ROOT/'arena/web/static/initial-state.json').read_text()) == fixture
