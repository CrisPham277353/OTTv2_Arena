"""Real HTTP competition with team-owned Python submissions in the Linux sandbox."""
import argparse
import json
from pathlib import Path
import time
from smoke_submissions import request


def wait_ready(sid, key):
    deadline = time.monotonic()+30
    while time.monotonic()<deadline:
        row = request(f'/api/submissions/{sid}', key=key)
        if row['status'] not in ('PENDING_CHECK','CHECKING'):
            assert row['status']=='READY', row
            return row
        time.sleep(.1)
    raise AssertionError('Sandbox check timed out')


def run(join=None):
    assert request('/api/runtime')['ready'], 'Linux sandbox is required'
    organizer = None
    if join:
        tournament = request(f'/api/tournaments/{join}')
        assert tournament['status']=='OPEN'
    else:
        organizer = request('/api/teams', {'name':'QA HTTP Organizer'})
        tournament = request('/api/tournaments', {'name':'QA HTTP Round Robin','format':'BO3','seed':42}, organizer['teamKey'])
    roster = []
    if join:
        remaining = max(0, 3-len(tournament['entries']))
        sources = ('capture_greedy','random_bot')[-remaining:] if remaining else ()
    else:
        sources = ('goal_rush','capture_greedy','random_bot')
    for index, source in enumerate(sources):
        team = organizer if organizer and index==0 else request('/api/teams', {'name':f'QA HTTP {source}'})
        row = request('/api/submissions', {'botName':f'{source} QA','filename':'bot.py',
                      'source':Path(f'bots/{source}.py').read_text(), 'gameId':tournament['gameId'],
                      'gameVersion':tournament['gameVersion']}, team['teamKey'])
        wait_ready(row['id'], team['teamKey'])
        request(f"/api/tournaments/{tournament['tournamentId']}/entries", {'botId':row['id']}, team['teamKey'])
        roster.append((team,row))
    tid = tournament['tournamentId']
    if join:
        return {'status':'REGISTERED','tournamentId':tid,'addedTeams':len(roster)}
    frozen = request(f'/api/tournaments/{tid}/start', {}, organizer['teamKey'])
    assert len(frozen['fixtures'])==3
    # A new source version after lock must never replace the chosen v1 artifact.
    new = request('/api/submissions', {'botName':roster[0][1]['botName'], 'filename':'bot.py',
                  'source':Path('bots/goal_rush.py').read_text()+'\n# post-lock version\n',
                  'gameVersion':tournament['gameVersion']}, organizer['teamKey'])
    assert new['version']==2
    live_seen=False
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        current=request(f'/api/tournaments/{tid}')
        for fixture in current['fixtures']:
            if fixture['status'] in ('QUEUED','RUNNING'):
                live=request(f"/api/matches/{fixture['matchId']}/live")
                if live['game'] and live['game']['state']['ply']>0 and live['match']['status']=='RUNNING':
                    live_seen=True
        if current['status']!='RUNNING':break
        time.sleep(.1)
    assert current['status']=='COMPLETED', current
    assert live_seen, 'No live board observed; run with the default frame delay'
    standings=request(f'/api/tournaments/{tid}/standings')
    assert standings['completedMatches']==standings['totalMatches']==3
    assert sum(row['points'] for row in standings['rows'])==9
    assert all(row['played']==2 and row['botVersion']==1 for row in standings['rows'])
    for fixture in current['fixtures']:
        replay=request(f"/api/matches/{fixture['matchId']}/replay")
        assert replay['tournamentId']==tid and max(replay['scores'].values())==2
        for game in replay['games']:
            assert game['result']['reason']!='BOT_FORFEIT'
            assert {log['runtime'] for log in game['botLogs'].values()}=={'bubblewrap+seccomp'}
            assert all(artifact['version']==1 for artifact in game['botArtifacts'].values())
    return {'status':'PASS','tournamentId':tid,'teams':3,'completedMatches':3,'liveSeen':live_seen,
            'lockedVersion':1,'newSubmissionVersion':2,
            'standings':[{key:row[key] for key in ('rank','teamName','points','gameDifference')} for row in standings['rows']]}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--join',help='Add two QA teams to an existing OPEN competition; leave starting to the web UI')
    args=parser.parse_args()
    print(json.dumps(run(args.join),ensure_ascii=False,indent=2))
