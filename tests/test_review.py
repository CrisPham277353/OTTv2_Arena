from concurrent.futures import ThreadPoolExecutor
import pytest
from arena.bootstrap import ROOT
from arena.core.storage import Store, CapacityError
from arena.core.submissions import SubmissionStore
from arena.games.ottv2.engine import OTTPlugin, TARGETS
from arena.games.ottv2.competitive import CompetitiveOTTPlugin
from tests.test_submissions import SOURCE
from tests.test_submissions import team,wait_checked
from tests.test_api import wait_complete
from arena.core.plugin import GameStatus,IllegalAction,StepResult
from arena.web.app import create_app
from fastapi.testclient import TestClient


def test_team_and_submission_quotas_are_atomic(tmp_path,monkeypatch):
    import arena.core.submissions as module
    monkeypatch.setattr(module,'MAX_TEAMS',2)
    monkeypatch.setattr(module,'MAX_TEAM_SUBMISSIONS',2)
    submissions=SubmissionStore(Store(tmp_path),ROOT/'bots/bot_sdk.py')
    def register(number):
        try:return submissions.register_team(f'Team {number}')
        except CapacityError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        teams=[r for r in pool.map(register,range(8)) if r]
    assert len(teams)==2
    owner=teams[0]
    def submit(number):
        try:return submissions.submit(owner['name'],'Bot','bot.py',SOURCE,'ottv2','1.1.0',owner['teamId'])
        except CapacityError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows=[r for r in pool.map(submit,range(8)) if r]
    assert sorted(r['version'] for r in rows)==[1,2]
    assert len(list(submissions.directory.iterdir()))==2
    assert len(submissions.list(team_id=owner['teamId']))==2
    assert submissions.list(team_id=teams[1]['teamId'])==[]
    assert submissions.pending_count()==2


@pytest.mark.parametrize('plugin',[OTTPlugin,CompetitiveOTTPlugin])
def test_observations_snapshots_events_and_metadata_do_not_mutate_engine(plugin):
    engine=plugin();state=engine.create({},42,('A','B'))
    state.ply=299
    step=engine.step(state,'A',engine.legal_actions(state,'A')[0])
    assert state.reason=='ADJUDICATED'
    snapshot=engine.serialize_state(state)
    original_from=state.last_move['from']
    original_alive=state.details['metrics']['A']['alive']
    snapshot['lastMove']['from']='i9'
    snapshot['details']['metrics']['A']['alive']=0
    observation=engine.observe(state,'A');observation['lastMove']['from']='h9'
    status=engine.status(state);status.details['metrics']['A']['alive']=-1
    step.events[-1]['details']['metrics']['A']['alive']=-2
    assert state.last_move['from']==original_from
    assert state.details['metrics']['A']['alive']==original_alive
    metadata=engine.render_metadata(state);metadata['targets']['A']='h9'
    assert TARGETS['A']==engine.observe(state,'A')['target']=='i9'


class BFirstPlugin:
    def create(self,config,seed,players):return {'turn':'B','ply':0,'winner':None}
    def status(self,state):return GameStatus(state['turn'],state['ply'],state['winner'],'DONE' if state['winner'] else None)
    def legal_actions(self,state,side):return [{'type':'PLAY'}] if not state['winner'] else []
    def observe(self,state,side):return {'legalActions':self.legal_actions(state,side)}
    def step(self,state,side,action):
        if side!=state['turn'] or action!={'type':'PLAY'}:raise IllegalAction('Wrong turn/action')
        state['ply']+=1
        if state['ply']==3:state['winner']=side
        else:state['turn']='A' if side=='B' else 'B'
        return StepResult(state,[])
    def serialize_state(self,state):return dict(state)
    def render_metadata(self,state):return {}


def test_submitted_bot_validation_uses_initial_side_from_plugin(tmp_path):
    app=create_app(tmp_path,frame_delay_ms=0)
    app.state.runner.registry.register({'gameId':'b-first','gameVersion':'1.0','pluginApi':'1.0',
        'players':2,'turnMode':'alternating','resultMode':'winner_only','replayRenderer':'/unused.js'},BFirstPlugin())
    with TestClient(app) as client:
        key,_=team(client,'Independent plugin')
        response=client.post('/api/submissions',headers=key,json={'botName':'Generic bot','filename':'bot.py',
            'source':SOURCE,'gameId':'b-first','gameVersion':'1.0'})
        assert response.status_code==201
        sid=response.json()['id']
        assert wait_checked(client,sid,key)['status']=='READY'
        response=client.post('/api/matches',headers=key,json={'botA':sid,'botB':sid,'gameId':'b-first','format':'BO1'})
        assert response.status_code==202
        match=wait_complete(client,response.json()['matchId'])
        replay=client.get(f"/api/matches/{match['matchId']}/replay").json()
        assert replay['games'][0]['frames'][0]['playerId']=='B'
        assert replay['games'][0]['result']['reason']=='DONE'


def test_validation_errors_explain_fields_without_echoing_secrets(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        response=client.post('/api/matches',json={'botA':'random','botB':'goal_rush','seed':True,'secret':'do-not-echo'})
        assert response.status_code==422
        detail=response.json()['detail']
        assert 'seed:' in detail and 'secret:' in detail
        assert 'do-not-echo' not in detail
