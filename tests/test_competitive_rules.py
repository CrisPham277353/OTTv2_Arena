import json
import random
from copy import deepcopy
import pytest
from arena.bootstrap import ROOT, build_registry
from arena.core.plugin import IllegalAction
from arena.games.ottv2.competitive import CompetitiveOTTPlugin, CompetitiveState, nearest_goal
from arena.games.ottv2.engine import OTTPlugin, state_key
from arena.games.ottv2.state import Piece, State

P=CompetitiveOTTPlugin()


def board(items, **kwargs):
    s=CompetitiveState({at:Piece(side,kind) for at,side,kind in items},**kwargs)
    if not s.best_goal_distance:s.best_goal_distance={side:nearest_goal(s,side) for side in ('A','B')}
    return s


def move(src,dst):return {'type':'MOVE','from':src,'to':dst}


@pytest.mark.parametrize('side,src,dst',[('A','d4','e5'),('B','e5','d4')])
def test_final_enemy_piece_wins_army_before_type(side,src,dst):
    enemy='B' if side=='A' else 'A'
    s=board([(src,side,'D'),(dst,enemy,'K')],turn=side)
    r=P.step(s,side,move(src,dst))
    assert (s.winner,s.reason)==(side,'ARMY_ELIMINATED')
    assert len(s.board)==1 and r.events[-1]['reason']=='ARMY_ELIMINATED'


def test_goal_retains_priority_over_army_and_stall():
    s=board([('h8','A','D'),('i9','B','K')],no_capture_plies=49,no_progress_turns={'A':14,'B':14})
    P.step(s,'A',move('h8','i9'))
    assert s.reason=='GOAL_REACHED' and s.winner=='A'
    assert s.no_capture_plies==0 and s.no_progress_turns['A']==0


def test_type_elimination_remains_a_win_with_enemies_surviving():
    s=board([('d4','A','D'),('e5','B','K'),('h8','B','D'),('i8','B','L')])
    P.step(s,'A',move('d4','e5'))
    assert s.reason=='TYPE_ELIMINATED' and s.winner=='A'
    assert sum(p.side=='B' for p in s.board.values())==2


def test_counters_reset_on_capture_that_does_not_end_game():
    s=board([('d4','A','D'),('e4','B','K'),('i8','B','K'),('h8','B','D'),('i7','B','L')],
            no_capture_plies=49,no_progress_turns={'A':14,'B':8})
    P.step(s,'A',move('d4','e4'))
    assert not s.winner and s.no_capture_plies==0
    assert s.no_progress_turns=={'A':0,'B':8}


def test_new_best_distance_resets_own_counter_but_not_quiet_counter():
    s=board([('d4','A','D'),('h8','B','L')],no_progress_turns={'A':14,'B':3},no_capture_plies=20)
    P.step(s,'A',move('d4','e5'))
    assert s.no_progress_turns=={'A':0,'B':3} and s.no_capture_plies==21
    assert s.best_goal_distance['A']==4 and not s.winner


def test_forward_then_back_cannot_farm_progress():
    s=board([('e5','A','D'),('h8','B','L')])
    P.step(s,'A',move('e5','d4'))
    P.step(s,'B',move('h8','g7'))
    P.step(s,'A',move('d4','e5'))
    assert s.no_progress_turns['A']==2 and s.best_goal_distance['A']==4


@pytest.mark.parametrize('side,src,dst', [('A','d4','c3'),('B','f6','g7')])
def test_15_own_stalled_turns_lose(side,src,dst):
    enemy='B' if side=='A' else 'A'
    other='h8' if side=='A' else 'b2'
    s=board([(src,side,'D'),(other,enemy,'L')],turn=side,
            no_progress_turns={side:14,enemy:5})
    r=P.step(s,side,move(src,dst))
    assert s.winner==enemy and s.reason=='NO_PROGRESS'
    assert s.details['ownTurnsWithoutProgress']==15 and s.details['loser']==side
    assert r.events[-1]['details']==s.details


def test_14_stalled_turns_are_not_terminal():
    s=board([('d4','A','D'),('h8','B','L')],no_progress_turns={'A':13,'B':0})
    P.step(s,'A',move('d4','c3'))
    assert s.no_progress_turns['A']==14 and not s.winner


def test_50_no_capture_plies_adjudicate_once():
    s=board([('d4','A','D'),('h8','B','L')],no_capture_plies=49)
    r=P.step(s,'A',move('d4','e5'))
    assert s.reason=='ADJUDICATED' and s.winner in ('A','B')
    assert s.details['trigger']=='NO_CAPTURE_LIMIT' and s.details['noCapturePlies']==50
    assert r.events[-1]['details']==s.details
    with pytest.raises(IllegalAction):P.step(s,s.turn,move('h8','g7'))


def test_49_no_capture_plies_continue():
    s=board([('d4','A','D'),('h8','B','L')],no_capture_plies=48)
    P.step(s,'A',move('d4','e5'))
    assert s.no_capture_plies==49 and not s.winner


def test_no_legal_moves_has_priority_over_stall():
    s=board([('a1','B','D'),('a2','A','L'),('b1','A','D'),('c3','A','L')],
            no_progress_turns={'A':14,'B':0})
    P.step(s,'A',move('c3','b2'))
    assert s.winner=='A' and s.reason=='NO_LEGAL_MOVES'


def test_repetition_precedes_quiet_adjudication():
    s=board([('d4','A','D'),('h8','B','L')],no_capture_plies=49)
    target=deepcopy(s);target.board['e5']=target.board.pop('d4');target.turn='B'
    s.repetitions[state_key(target)]=2
    P.step(s,'A',move('d4','e5'))
    assert s.details['trigger']=='THREEFOLD_REPETITION'


def test_ply_limit_still_applies_after_capture():
    s=board([('d4','A','D'),('e4','B','K'),('i8','B','K'),('h8','B','D'),('i7','B','L')],ply=299)
    P.step(s,'A',move('d4','e4'))
    assert s.ply==300 and s.details['trigger']=='PLY_LIMIT'


def test_invalid_action_does_not_change_pressure():
    s=P.create({},42,('A','B'));before=P.serialize_state(s)
    with pytest.raises(IllegalAction):P.step(s,'A',move('a1','i9'))
    assert P.serialize_state(s)==before


def test_pressure_snapshot_and_observation_are_copies():
    s=P.create({},42,('A','B'))
    snapshot=P.serialize_state(s);obs=P.observe(s,'A')
    assert snapshot['antiStall']['bestGoalDistance']=={'A':7,'B':7}
    P.step(s,'A',move('a1','a2'))
    assert snapshot['antiStall']['noProgressTurns']['A']==0
    assert obs['antiStall']['noCapturePlies']==0
    assert P.serialize_state(s)['antiStall']['noCapturePlies']==1


def test_plugin_versions_and_legacy_rules_preserved():
    registry=build_registry()
    assert registry.get('ottv2')[0]['gameVersion']=='1.1.0'
    assert type(registry.get('ottv2','1.0.0')[1]) is OTTPlugin
    old=State({'d4':Piece('A','D'),'e5':Piece('B','K')})
    OTTPlugin().step(old,'A',move('d4','e5'))
    assert old.reason=='TYPE_ELIMINATED'
    assert 'antiStall' not in OTTPlugin().serialize_state(old)


def test_competitive_fixture_and_seeded_playouts():
    s=P.create({},42,('A','B'))
    fixture=json.loads((ROOT/'arena/games/ottv2/test-data/initial-state-v1.1.json').read_text())
    assert fixture=={'state':P.serialize_state(s),'metadata':P.render_metadata(s)}
    assert fixture==json.loads((ROOT/'arena/web/static/initial-state-v1.1.json').read_text())
    for seed in range(10):
        s=P.create({},seed,('A','B'));rng=random.Random(seed)
        while not P.status(s).terminal:
            P.step(s,s.turn,rng.choice(P.legal_actions(s,s.turn)))
            assert len(s.board)==len(P.serialize_state(s)['pieces'])
            assert s.no_capture_plies<=50 and s.ply<=300
        assert s.winner in ('A','B') and s.reason!='DRAW'
