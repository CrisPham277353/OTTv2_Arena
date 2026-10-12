import time
from fastapi.testclient import TestClient
from arena.core.storage import Store
from arena.web.app import create_app


def wait_complete(client, match_id):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        match = client.get(f'/api/matches/{match_id}').json()
        if match['status'] not in ('QUEUED', 'RUNNING'):
            assert match['status'] == 'COMPLETED', match
            return match
        time.sleep(0.02)
    raise AssertionError('Match did not complete')


def test_api_create_complete_replay_history_stats_restart(tmp_path):
    app = create_app(tmp_path, frame_delay_ms=0)
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert len(client.get('/api/bots').json()) == 3
        assert client.get('/api/games').json()[0]['gameId'] == 'ottv2'
        response = client.post('/api/matches', json={'botA':'random', 'botB':'goal_rush', 'format':'BO3', 'seed':42})
        assert response.status_code == 202
        match_id = response.json()['matchId']
        completed = wait_complete(client, match_id)
        replay = client.get(f'/api/matches/{match_id}/replay').json()
        assert replay['status'] == 'COMPLETED'
        assert replay['games'][0]['initialState']['pieces'] and replay['games'][0]['frames']
        assert len(replay['games']) in (2,3)
        assert replay['scores'] == completed['scores']
        assert client.get('/api/matches').json()[0]['matchId'] == match_id
        stats = client.get('/api/stats').json()
        assert sum(s['wins'] for s in stats) == 1 and sum(s['losses'] for s in stats) == 1
        assert client.get('/api/matches/no-such-match').status_code == 404
        assert client.get('/api/matches/no-such-match/replay').status_code == 404
        for payload in [{'botA':'../bad.py','botB':'random'}, {'botA':'random','botB':'random','format':'BO5'},
                        {'botA':'random','botB':'random','seed':-1}, {'botA':'random','botB':'random','seed':True},
                        {'botA':'random','botB':'random','gameId':'unknown'}]:
            assert client.post('/api/matches', json=payload).status_code == 422
    with TestClient(create_app(tmp_path, frame_delay_ms=0)) as restarted:
        assert restarted.get(f'/api/matches/{match_id}').json() == completed
        assert restarted.get(f'/api/matches/{match_id}/replay').json() == replay


def test_interrupted_match_is_reported_on_restart(tmp_path):
    store = Store(tmp_path)
    store.put({'matchId':'interrupted', 'status':'RUNNING'})
    with TestClient(create_app(tmp_path, frame_delay_ms=0)) as client:
        match = client.get('/api/matches/interrupted').json()
        assert match['status'] == 'INTERRUPTED'
        assert client.get('/api/matches/interrupted/replay').status_code == 409


def test_recover_completed_replay_before_metadata_commit(tmp_path):
    store = Store(tmp_path)
    store.put({'matchId':'recover', 'status':'RUNNING'})
    store.save_replay({'matchId':'recover', 'status':'COMPLETED', 'scores':{'botA':1,'botB':0},
                       'winnerSlot':'botA', 'winnerBot':'random', 'reason':'GOAL_REACHED',
                       'games':[{'result':{'winner':'A','reason':'GOAL_REACHED','plies':15}}]})
    store.recover()
    assert store.get('recover')['status'] == 'COMPLETED'
    assert store.get('recover')['gameResults'][0]['winner'] == 'A'


def test_finite_queue_validation_and_forbidden_fields(tmp_path):
    app = create_app(tmp_path, frame_delay_ms=0)
    with TestClient(app) as client:
        for i in range(8):
            app.state.store.put({'matchId':f'queued-{i}', 'status':'QUEUED'})
        assert client.post('/api/matches', json={'botA':'random','botB':'goal_rush'}).status_code == 429
        assert client.post('/api/matches', json={'botA':'random','botB':'goal_rush','script':'/tmp/bot.py'}).status_code == 422
        assert client.post('/api/matches', json={'botA':'random','botB':'goal_rush','gameVersion':'missing'}).status_code == 422


def test_versioned_matches_default_and_legacy(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        catalog=client.get('/api/games').json()
        assert {g['gameVersion'] for g in catalog}=={'1.0.0','1.1.0'}
        assert next(g for g in catalog if g.get('isDefault'))['gameVersion']=='1.1.0'
        for version in (None,'1.0.0'):
            payload={'botA':'random','botB':'random','seed':42}
            if version:payload['gameVersion']=version
            r=client.post('/api/matches',json=payload)
            assert r.status_code==202
            mid=r.json()['matchId'];match=wait_complete(client,mid)
            replay=client.get(f'/api/matches/{mid}/replay').json()
            expected=version or '1.1.0'
            assert match['gameVersion']==replay['gameVersion']==expected
            initial=replay['games'][0]['initialState']
            assert ('antiStall' in initial)==(expected=='1.1.0')
            assert replay['games'][0]['result']['winner'] in ('A','B')


def test_large_seed_replay_has_exact_display_text(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        seed = 2**63-1
        response = client.post('/api/matches',json={'botA':'random','botB':'goal_rush','seed':seed})
        assert response.status_code == 202
        mid = response.json()['matchId']
        wait_complete(client,mid)
        replay = client.get(f'/api/matches/{mid}/replay').json()
        assert replay['seed'] == seed
        assert replay['seedText'] == '9223372036854775807'
