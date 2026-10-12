from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient
from arena.bootstrap import ROOT
from arena.core.storage import Store
from arena.core.submissions import SubmissionStore, SubmissionCatalog
from arena.web.app import create_app
from tests.test_api import wait_complete

SOURCE = '''import json,sys
for line in sys.stdin:
 r=json.loads(line)
 print(json.dumps({'type':'action','protocolVersion':'1.0','requestId':r['requestId'],'turnId':r['turnId'],'action':r['observation']['legalActions'][0]}),flush=True)
'''


def team(client, name='Đội Alpha'):
    r = client.post('/api/teams', json={'name':name})
    assert r.status_code == 201, r.text
    return {'X-Team-Key':r.json()['teamKey']}, r.json()['teamId']


def submit(client, headers, source=SOURCE, filename='my_bot.py'):
    return client.post('/api/submissions', headers=headers,
        json={'botName':'Chiến thuật tự viết','filename':filename,'source':source})


def wait_checked(client, sid, headers):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        row = client.get(f'/api/submissions/{sid}', headers=headers).json()
        if row['status'] not in ('CHECKING','PENDING_CHECK'):
            return row
        time.sleep(.03)
    raise AssertionError('Submission validation did not finish')


def test_submit_automatic_sandbox_match_version_and_restart(tmp_path):
    with TestClient(create_app(tmp_path, frame_delay_ms=0)) as client:
        assert client.get('/api/runtime').json()['ready'], 'Run this integration test on Linux with usable bubblewrap'
        headers, tid = team(client)
        first = submit(client,headers)
        assert first.status_code == 201
        sid = first.json()['id']
        record = wait_checked(client,sid,headers)
        assert record['status'] == 'READY', record
        assert record['sourceSha256'] == sha256(SOURCE.encode()).hexdigest()
        assert sid in [b['id'] for b in client.get('/api/bots').json()]
        second = submit(client,headers, SOURCE+'\n# version 2\n').json()
        assert second['version'] == 2 and second['id'] != sid
        assert client.get(f'/api/submissions/{sid}/source',headers=headers).text == SOURCE
        assert client.get('/api/submissions').status_code == 401
        other, _ = team(client,'Đội Beta')
        assert client.get(f'/api/submissions/{sid}/source',headers=other).status_code == 404
        assert client.get('/api/submissions',headers=other).json() == []
        payload = {'botA':sid,'botB':'random','format':'BO1','seed':42}
        assert client.post('/api/matches',json=payload).status_code == 401
        assert client.post('/api/matches',json=payload,headers=other).status_code == 403
        r = client.post('/api/matches',json=payload,headers=headers)
        assert r.status_code == 202, r.text
        completed = wait_complete(client,r.json()['matchId'])
        replay = client.get(f"/api/matches/{completed['matchId']}/replay").json()
        assert replay['games'][0]['botLogs']['A']['runtime'] == 'bubblewrap+seccomp'
        assert replay['games'][0]['botArtifacts']['botA']['artifactSha256'] == record['artifactSha256']
        assert replay['games'][0]['botArtifacts']['botA']['version'] == 1
        assert replay['games'][0]['result']['reason'] != 'BOT_FORFEIT'
    with TestClient(create_app(tmp_path, frame_delay_ms=0)) as restarted:
        assert restarted.get('/api/team',headers=headers).json()['teamId'] == tid
        assert restarted.get(f'/api/submissions/{sid}',headers=headers).json()['status'] == 'READY'
        assert restarted.get(f"/api/matches/{completed['matchId']}").json() == completed


@pytest.mark.parametrize('source,expected', [('def broken(','INVALID'), ('print("not JSON",flush=True)','CHECK_FAILED'),
    ('import time\ntime.sleep(5)','CHECK_FAILED'), ('raise RuntimeError("crash")','CHECK_FAILED')])
def test_submission_failures_never_become_selectable(tmp_path,source,expected):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        headers,_ = team(client)
        r = submit(client,headers,source)
        assert r.status_code == 201
        sid = r.json()['id']
        row = wait_checked(client,sid,headers)
        assert row['status'] == expected, row
        assert sid not in [b['id'] for b in client.get('/api/bots').json()]
        assert client.post('/api/matches',json={'botA':sid,'botB':'random'},headers=headers).status_code == 422


def test_unavailable_runtime_fails_closed(tmp_path):
    app = create_app(tmp_path,frame_delay_ms=0)
    with TestClient(app) as client:
        app.state.runtime.ready=False
        app.state.runtime.message='Disabled for this test'
        headers,_=team(client)
        r=submit(client,headers)
        assert r.json()['status']=='SANDBOX_UNAVAILABLE'
        assert r.json()['id'] not in [b['id'] for b in client.get('/api/bots').json()]


def test_input_bounds_filename_origin_and_keys(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        headers,_=team(client)
        for filename in ['../evil.py','x.zip','bot.py/evil.py','/tmp/bot.py']:
            assert submit(client,headers,filename=filename).status_code==422
        assert submit(client,headers,source='a'*262145).status_code==422
        assert submit(client,{'X-Team-Key':'wrong'}).status_code==401
        assert client.post('/api/teams',json={'name':'other'},headers={'Origin':'https://evil.example'}).status_code==403
        response=client.post('/api/submissions',headers=headers,content=b'x'*524289)
        assert response.status_code==413


def test_version_allocation_and_tamper_guard(tmp_path):
    s=SubmissionStore(Store(tmp_path),ROOT/'bots/bot_sdk.py')
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda i:s.submit('Alpha','My bot','bot.py',SOURCE,'ottv2','1.0.0'),range(4)))
    assert sorted(r['version'] for r in rows)==[1,2,3,4]
    row=rows[0]
    path=s.verify(row['id'])
    path.chmod(0o644)
    path.write_text('print("changed")')
    with pytest.raises(ValueError):s.verify(row['id'])


def test_two_teams_submit_and_fight_in_sandbox(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        alpha,_=team(client,'Alpha tự code')
        beta,_=team(client,'Beta tự code')
        left=submit(client,alpha,(ROOT/'bots/goal_rush.py').read_text()).json()
        right=submit(client,beta,(ROOT/'bots/capture_greedy.py').read_text()).json()
        for row,headers in ((left,alpha),(right,beta)):
            assert wait_checked(client,row['id'],headers)['status']=='READY'
        mid=client.post('/api/matches',headers=alpha,json={'botA':left['id'],'botB':right['id'],'format':'BO3'}).json()['matchId']
        wait_complete(client,mid)
        replay=client.get(f'/api/matches/{mid}/replay').json()
        for game in replay['games']:
            assert game['result']['reason']!='BOT_FORFEIT'
            assert {log['runtime'] for log in game['botLogs'].values()}=={'bubblewrap+seccomp'}
            assert all(artifact['source']=='submission' for artifact in game['botArtifacts'].values())


def test_old_submission_requires_matching_game_version(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as client:
        headers,_=team(client)
        row=client.post('/api/submissions',headers=headers,json={'botName':'Luật cũ','filename':'bot.py',
               'source':SOURCE,'gameVersion':'1.0.0'}).json()
        assert wait_checked(client,row['id'],headers)['status']=='READY'
        payload={'botA':row['id'],'botB':'random'}
        assert client.post('/api/matches',headers=headers,json=payload).status_code==422
        payload['gameVersion']='1.0.0'
        r=client.post('/api/matches',headers=headers,json=payload)
        assert r.status_code==202
        assert wait_complete(client,r.json()['matchId'])['gameVersion']=='1.0.0'
