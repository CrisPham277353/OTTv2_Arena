"""Real HTTP smoke: register team, submit code, sandbox check, live match, replay."""
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

BASE='http://127.0.0.1:8000'


def request(path, body=None, key=None):
    headers={'Content-Type':'application/json'}
    if key:headers['X-Team-Key']=key
    req=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urlopen(req,timeout=10) as response:return json.load(response)


if __name__=='__main__':
    assert request('/api/runtime')['ready'], 'Sandbox must be ready; no unsafe fallback'
    team=request('/api/teams',{'name':'Đội smoke HTTP'})
    source=Path('bots/goal_rush.py').read_text()
    row=request('/api/submissions',{'botName':'Bot tự nộp','filename':'my_bot.py','source':source},team['teamKey'])
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        row=request(f"/api/submissions/{row['id']}",key=team['teamKey'])
        if row['status'] not in ('PENDING_CHECK','CHECKING'):break
        time.sleep(.1)
    assert row['status']=='READY',row
    match=request('/api/matches',{'botA':row['id'],'botB':'capture_greedy','format':'BO1','seed':42},team['teamKey'])
    mid=match['matchId']; live_seen=False;deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        live=request(f'/api/matches/{mid}/live')
        if live['match']['status']=='RUNNING' and live['game'] and live['game']['state']['ply']>0:live_seen=True
        if live['match']['status'] not in ('QUEUED','RUNNING'):break
        time.sleep(.08)
    assert live_seen and live['match']['status']=='COMPLETED',live
    replay=request(f'/api/matches/{mid}/replay')
    assert replay['games'][0]['botLogs']['A']['runtime']=='bubblewrap+seccomp'
    assert replay['games'][0]['result']['reason']!='BOT_FORFEIT'
    print(json.dumps({'status':'PASS','submissionStatus':row['status'],'liveSeen':live_seen,'matchId':mid,
                      'plies':replay['games'][0]['result']['plies'],'reason':replay['games'][0]['result']['reason']},ensure_ascii=False,indent=2))
