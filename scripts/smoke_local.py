"""Run against an already running local server; stdlib HTTP only."""
import json
import time
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8000'


def request(path, body=None):
    req = Request(BASE + path, data=json.dumps(body).encode() if body else None,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


if __name__ == '__main__':
    assert len(request('/api/bots')) >= 3
    assert request('/api/games')[0]['gameId'] == 'ottv2'
    created = request('/api/matches', {'gameId':'ottv2', 'botA':'capture_greedy',
                                     'botB':'goal_rush', 'format':'BO3', 'seed':42})
    mid = created['matchId']
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        match = request(f'/api/matches/{mid}')
        if match['status'] not in ('RUNNING', 'QUEUED'):
            break
        time.sleep(0.1)
    assert match['status'] == 'COMPLETED', match
    replay = request(f'/api/matches/{mid}/replay')
    assert replay['games'][0]['frames']
    assert replay['scores'] == match['scores']
    assert request('/api/matches')[0]['matchId'] == mid
    assert request('/api/stats')
    print(json.dumps({'status':'PASS', 'matchId':mid, 'scores':match['scores'],
                      'winner':match['winnerBot'], 'games':len(replay['games']),
                      'plies':[g['result']['plies'] for g in replay['games']]}, ensure_ascii=False, indent=2))
