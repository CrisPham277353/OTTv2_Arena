import time
from fastapi.testclient import TestClient
from arena.web.app import create_app
from tests.test_api import wait_complete


def test_live_snapshot_visible_before_completion(tmp_path):
    with TestClient(create_app(tmp_path,frame_delay_ms=30)) as client:
        r=client.post('/api/matches',json={'botA':'capture_greedy','botB':'goal_rush','seed':42})
        mid=r.json()['matchId']
        found=None
        end=time.monotonic()+5
        while time.monotonic()<end:
            live=client.get(f'/api/matches/{mid}/live').json()
            if live['match']['status']=='RUNNING' and live['game'] and live['game']['state']['ply']>0:
                found=live;break
            time.sleep(.01)
        assert found and found['game']['state']['pieces']
        assert found['game']['frames'][-1]['state']==found['game']['state']
        completed=wait_complete(client,mid)
        replay=client.get(f'/api/matches/{mid}/replay').json()
        assert completed['status']=='COMPLETED'
        assert replay['games'][0]['frames'][found['game']['state']['ply']-1]['state']==found['game']['state']
