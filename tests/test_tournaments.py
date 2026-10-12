from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
import time
import threading
import pytest
from fastapi.testclient import TestClient
from arena.bootstrap import ROOT
from arena.core.storage import Store
from arena.core.tournaments import TournamentStore, TournamentError, round_robin
from arena.web.app import create_app
from tests.test_submissions import SOURCE, team, submit, wait_checked


@pytest.mark.parametrize('size', range(2, 17))
def test_circle_schedule_complete_unique_pairs_and_byes(size):
    ids = [str(i) for i in range(size)]
    schedule = round_robin(ids)
    assert len(schedule) == size * (size-1) // 2
    assert {frozenset((a, b)) for _, a, b in schedule} == {frozenset(pair) for pair in combinations(ids, 2)}
    assert Counter(a for _, a, _ in schedule) + Counter(b for _, _, b in schedule) == Counter({i: size-1 for i in ids})
    for number in range(1, (size if size % 2 else size-1) + 1):
        playing = [team_id for round_number, a, b in schedule if round_number == number for team_id in (a, b)]
        assert len(playing) == len(set(playing)) == size - size % 2
    assert schedule == round_robin(ids)


def setup_tournament(tmp_path, count=3):
    store = Store(tmp_path)
    tournaments = TournamentStore(store)
    organizer = {'teamId': '0', 'name': 'Organizer'}
    tournament = tournaments.create('Test cup', organizer, 'any-plugin', '7.0', 'BO3', 42)
    artifacts = {str(i): {'teamId': str(i), 'teamName': f'Team {i}', 'botId': f'bot-{i}',
                          'botLabel': f'Bot {i}', 'botName': f'Bot {i}', 'botVersion': 1,
                          'gameVersion': '7.0', 'artifactSha256': f'hash-{i}', 'sourceSha256': f'source-{i}'}
                 for i in range(count)}
    def resolve(tournament, team_id, bot_id):
        assert bot_id == artifacts[team_id]['botId']
        return artifacts[team_id].copy()
    for team_id in artifacts:
        tournaments.register(tournament['tournamentId'], {'teamId': team_id}, artifacts[team_id]['botId'], resolve)
    return store, tournaments, tournament['tournamentId'], resolve, artifacts


def finish(store, tournaments, match, winner_slot='botA', scores=None):
    match.update(status='COMPLETED', winnerSlot=winner_slot, scores=scores or {'botA': 2, 'botB': 0})
    store.put(match)
    tournaments.record_result(match)


def test_freeze_schedule_durable_claim_and_completion(tmp_path):
    store, tournaments, tid, resolve, artifacts = setup_tournament(tmp_path)
    with pytest.raises(TournamentError) as denied:
        tournaments.start(tid, '1', resolve)
    assert denied.value.status == 403
    tournament = tournaments.start(tid, '0', resolve)
    assert tournament['status'] == 'RUNNING' and tournament['lockedAt']
    assert len(tournament['fixtures']) == 3
    assert all(0 <= fixture['seed'] <= 2**53-1 for fixture in tournament['fixtures'])
    assert {store.get(f['matchId'])['status'] for f in tournament['fixtures']} == {'SCHEDULED'}
    artifacts['0']['botVersion'] = 2
    assert tournaments.get(tid)['entries'][0]['botVersion'] == 1
    for action in (lambda: tournaments.register(tid, {'teamId':'0'}, 'bot-0', resolve),
                   lambda: tournaments.withdraw(tid, '0'), lambda: tournaments.start(tid, '0', resolve)):
        with pytest.raises(TournamentError): action()
    claimed = tournaments.claim_next()
    assert claimed['gameId'] == 'any-plugin' and claimed['gameVersion'] == '7.0'
    assert tournaments.claim_next() is None
    finish(store, tournaments, claimed)
    for _ in range(2):
        match = tournaments.claim_next()
        finish(store, tournaments, match)
    assert tournaments.get(tid)['status'] == 'COMPLETED'
    assert tournaments.claim_next() is None
    ranking = tournaments.standings(tid)
    assert ranking['completedMatches'] == 3
    assert sum(r['points'] for r in ranking['rows']) == 9
    assert sum(r['played'] for r in ranking['rows']) == 6
    assert sum(r['gameWins'] for r in ranking['rows']) == 6
    assert TournamentStore(Store(tmp_path)).standings(tid) == ranking


def test_claim_is_atomic_between_workers(tmp_path):
    _, tournaments, tid, resolve, _ = setup_tournament(tmp_path)
    tournaments.start(tid, '0', resolve)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(lambda _: tournaments.claim_next(), range(4)))
    assert sum(m is not None for m in claimed) == 1


def test_recovery_and_explicit_retry_preserve_finished_results_and_frozen_hash(tmp_path):
    store, tournaments, tid, resolve, artifacts = setup_tournament(tmp_path)
    tournaments.start(tid, '0', resolve)
    first = tournaments.claim_next()
    finish(store, tournaments, first)
    interrupted = tournaments.claim_next()
    interrupted.update(status='RUNNING')
    store.put(interrupted)
    store.recover()
    tournaments.recover()
    assert tournaments.get(tid)['status'] == 'PAUSED'
    assert tournaments.standings(tid)['completedMatches'] == 1
    artifacts['0']['artifactSha256'] = 'changed'
    with pytest.raises(TournamentError): tournaments.resume(tid, '0', resolve)
    assert tournaments.get(tid)['status'] == 'PAUSED'
    artifacts['0']['artifactSha256'] = 'hash-0'
    resumed = tournaments.resume(tid, '0', resolve)
    replacement = next(f for f in resumed['fixtures'] if f['fixtureId'] == interrupted['fixtureId'])
    assert replacement['matchId'] != interrupted['matchId']
    assert replacement['seed'] == interrupted['seed']
    assert replacement['attempts'][0]['matchId'] == interrupted['matchId']
    assert store.get(interrupted['matchId'])['status'] == 'INTERRUPTED'
    assert resumed['fixtures'][0]['matchId'] == first['matchId']
    # Late callbacks from the old attempt cannot replace the new fixture.
    tournaments.record_result(interrupted)
    assert tournaments.get(tid)['status'] == 'RUNNING'
    assert tournaments.standings(tid)['completedMatches'] == 1


def test_restart_recovers_completed_replay_without_replaying_fixture(tmp_path):
    store, tournaments, tid, resolve, _ = setup_tournament(tmp_path, 2)
    tournaments.start(tid, '0', resolve)
    match = tournaments.claim_next()
    store.save_replay({'matchId': match['matchId'], 'status': 'COMPLETED', 'scores': {'botA':2,'botB':1},
                       'winnerSlot':'botA', 'winnerBot':match['botA'], 'reason':'TEST', 'games':[]})
    store.recover()
    tournaments.recover()
    assert tournaments.get(tid)['status'] == 'COMPLETED'
    assert tournaments.claim_next() is None
    assert tournaments.standings(tid)['rows'][0]['points'] == 3


def test_standings_game_difference_then_head_to_head_and_shared_rank(tmp_path):
    store, tournaments, tid, resolve, _ = setup_tournament(tmp_path, 4)
    tournaments.start(tid, '0', resolve)
    # Teams 0 and 1 have equal points, game difference and game wins; 0 won their direct meeting.
    winners = {frozenset(('0','1')):'0', frozenset(('0','2')):'0', frozenset(('0','3')):'3',
               frozenset(('1','2')):'1', frozenset(('1','3')):'1', frozenset(('2','3')):'2'}
    while (match := tournaments.claim_next()) is not None:
        tournament = tournaments.get(tid)
        fixture = next(f for f in tournament['fixtures'] if f['matchId'] == match['matchId'])
        winner = winners[frozenset((fixture['teamA'],fixture['teamB']))]
        slot = 'botA' if winner == fixture['teamA'] else 'botB'
        finish(store, tournaments, match, slot, {'botA':2,'botB':0} if slot=='botA' else {'botA':0,'botB':2})
    rows = tournaments.standings(tid)['rows']
    assert [r['teamId'] for r in rows[:2]] == ['0','1']
    assert [r['points'] for r in rows[:2]] == [6,6]
    assert [r['gameDifference'] for r in rows[:2]] == [2,2]
    assert [r['headToHeadPoints'] for r in rows[:2]] == [3,0]
    # A rock-paper-scissors circle remains honestly tied, with shared rank 1.
    other = tmp_path / 'tie'
    store, tournaments, tid, resolve, _ = setup_tournament(other, 3)
    tournaments.start(tid, '0', resolve)
    winners = {frozenset(('0','1')):'0', frozenset(('1','2')):'1', frozenset(('0','2')):'2'}
    while (match := tournaments.claim_next()) is not None:
        fixture = next(f for f in tournaments.get(tid)['fixtures'] if f['matchId'] == match['matchId'])
        slot = 'botA' if winners[frozenset((fixture['teamA'],fixture['teamB']))] == fixture['teamA'] else 'botB'
        finish(store, tournaments, match, slot, {'botA':2,'botB':0} if slot=='botA' else {'botA':0,'botB':2})
    assert [r['rank'] for r in tournaments.standings(tid)['rows']] == [1,1,1]


def wait_tournament(client, tid):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        tournament = client.get(f'/api/tournaments/{tid}').json()
        if tournament['status'] != 'RUNNING':
            assert tournament['status'] == 'COMPLETED', tournament
            return tournament
        time.sleep(.03)
    raise AssertionError('Tournament did not complete')


def test_three_teams_auto_bo3_freezes_version_live_ranking_and_restart(tmp_path):
    app = create_app(tmp_path, frame_delay_ms=2)
    with TestClient(app) as client:
        teams = [team(client, label) for label in ('Alpha','Beta','Gamma')]
        bots = []
        for (headers,_), source in zip(teams, (SOURCE, (ROOT/'bots/goal_rush.py').read_text(), (ROOT/'bots/capture_greedy.py').read_text())):
            row = submit(client, headers, source).json()
            assert wait_checked(client, row['id'], headers)['status'] == 'READY'
            bots.append(row)
        headers, organizer_id = teams[0]
        created = client.post('/api/tournaments', headers=headers, json={'name':'Three teams cup','seed':42})
        assert created.status_code == 201
        tid = created.json()['tournamentId']
        for (key,_), bot in zip(teams,bots):
            assert client.post(f'/api/tournaments/{tid}/entries',headers=key,json={'botId':bot['id']}).status_code == 200
        assert client.post(f'/api/tournaments/{tid}/start',headers=teams[1][0]).status_code == 403
        started = client.post(f'/api/tournaments/{tid}/start',headers=headers)
        assert started.status_code == 200 and len(started.json()['fixtures']) == 3
        assert client.post(f'/api/tournaments/{tid}/start',headers=headers).status_code == 409
        assert client.post(f'/api/tournaments/{tid}/withdraw',headers=teams[1][0]).status_code == 409
        second = submit(client,headers,SOURCE+'\n# future version\n').json()
        assert second['version'] == 2
        assert client.post(f'/api/tournaments/{tid}/entries',headers=headers,json={'botId':second['id']}).status_code == 409
        completed = wait_tournament(client, tid)
        assert completed['organizerTeamId'] == organizer_id
        assert completed['entries'][0]['botVersion'] == 1
        standings = client.get(f'/api/tournaments/{tid}/standings').json()
        assert standings['completedMatches'] == standings['totalMatches'] == 3
        assert all(r['played'] == 2 for r in standings['rows'])
        assert sum(r['points'] for r in standings['rows']) == 9
        for fixture in completed['fixtures']:
            match = client.get(f"/api/matches/{fixture['matchId']}").json()
            replay = client.get(f"/api/matches/{fixture['matchId']}/replay").json()
            assert match['format'] == 'BO3' and max(match['scores'].values()) == 2
            assert replay['tournamentId'] == tid and replay['fixtureId'] == fixture['fixtureId']
            assert replay['gameVersion'] == '1.1.0'
            assert replay['seedText'] == str(match['seed'])
            assert client.get(f"/api/matches/{fixture['matchId']}/live").json()['game']['state']['pieces']
            for game in replay['games']:
                assert {log['runtime'] for log in game['botLogs'].values()} == {'bubblewrap+seccomp'}
                assert all(artifact['version'] == 1 for artifact in game['botArtifacts'].values())
        assert client.get('/api/tournaments').json()[0]['completedMatches'] == 3
    with TestClient(create_app(tmp_path,frame_delay_ms=0)) as restarted:
        assert restarted.get(f'/api/tournaments/{tid}').json() == completed
        assert restarted.get(f'/api/tournaments/{tid}/standings').json() == standings
        assert len(restarted.get('/api/matches').json()) == 3


def test_tournament_api_ownership_version_ready_and_input_guards(tmp_path):
    app = create_app(tmp_path,frame_delay_ms=0)
    with TestClient(app) as client:
        owner, _ = team(client)
        other, _ = team(client, 'Other')
        assert client.post('/api/tournaments',json={'name':'No auth'}).status_code == 401
        for payload in ({'name':' '}, {'name':'Bad','gameVersion':'missing'}, {'name':'Bad','seed':True}, {'name':'Bad','extra':1}):
            assert client.post('/api/tournaments',headers=owner,json=payload).status_code == 422
        created = client.post('/api/tournaments',headers=owner,json={'name':'Legacy','gameVersion':'1.0.0'})
        assert created.status_code == 201
        tid = created.json()['tournamentId']
        assert client.post(f'/api/tournaments/{tid}/start',headers=owner).status_code == 409
        # Samples cannot represent a team; an arbitrary READY bot cannot be borrowed.
        assert client.post(f'/api/tournaments/{tid}/entries',headers=owner,json={'botId':'random'}).status_code == 403
        invalid = submit(client,owner,'def broken(').json()
        assert client.post(f'/api/tournaments/{tid}/entries',headers=owner,json={'botId':invalid['id']}).status_code == 422
        row = submit(client,owner).json()
        assert wait_checked(client,row['id'],owner)['status'] == 'READY'
        assert client.post(f'/api/tournaments/{tid}/entries',headers=other,json={'botId':row['id']}).status_code == 403
        assert client.post(f'/api/tournaments/{tid}/entries',headers=owner,json={'botId':row['id']}).status_code == 422
        assert client.get('/api/tournaments/missing').status_code == 404
        assert client.get('/api/tournaments/missing/standings').status_code == 404
        assert client.post('/api/tournaments',headers={**owner,'Origin':'https://evil.example'},json={'name':'Bad'}).status_code == 403
        assert client.post('/api/tournaments',headers=owner,content=b'x'*524289).status_code == 413


def test_entry_replace_withdraw_and_failed_lock_is_atomic(tmp_path):
    store, tournaments, tid, resolve, artifacts = setup_tournament(tmp_path, 2)
    artifacts['0']['botVersion'] = 2
    tournaments.register(tid, {'teamId':'0'}, 'bot-0', resolve)
    assert len(tournaments.get(tid)['entries']) == 2
    assert tournaments.get(tid)['entries'][0]['botVersion'] == 2
    def invalid(tournament, team_id, bot_id):
        if team_id == '1':raise TournamentError('Hash mismatch')
        return resolve(tournament,team_id,bot_id)
    with pytest.raises(TournamentError):tournaments.start(tid, '0', invalid)
    assert tournaments.get(tid)['status'] == 'OPEN'
    assert store.list() == []
    tournaments.withdraw(tid, '1')
    with pytest.raises(TournamentError):tournaments.start(tid, '0', resolve)


def test_runtime_unavailable_cannot_lock_tournament(tmp_path):
    app = create_app(tmp_path,frame_delay_ms=0)
    with TestClient(app) as client:
        key, _ = team(client)
        tid = client.post('/api/tournaments',headers=key,json={'name':'No sandbox'}).json()['tournamentId']
        app.state.runtime.ready = False
        assert client.post(f'/api/tournaments/{tid}/start',headers=key).status_code == 503
        assert client.get(f'/api/tournaments/{tid}').json()['status'] == 'OPEN'


def test_changed_artifact_pauses_without_awarding_points_and_can_retry_after_restore(tmp_path):
    app = create_app(tmp_path,frame_delay_ms=0)
    gate = threading.Event()
    with TestClient(app) as client:
        owner, _ = team(client, 'Owner')
        opponent, _ = team(client, 'Opponent')
        left, right = submit(client,owner).json(), submit(client,opponent).json()
        for row, key in ((left,owner),(right,opponent)):
            assert wait_checked(client,row['id'],key)['status'] == 'READY'
        tid = client.post('/api/tournaments',headers=owner,json={'name':'Integrity cup'}).json()['tournamentId']
        for row, key in ((left,owner),(right,opponent)):
            assert client.post(f'/api/tournaments/{tid}/entries',headers=key,json={'botId':row['id']}).status_code == 200
        app.state.executor.submit(lambda: gate.wait(10))
        try:
            assert client.post(f'/api/tournaments/{tid}/start',headers=owner).status_code == 200
            path = app.state.submissions.verify(left['id'])
            original = path.read_bytes()
            path.chmod(0o644)
            path.write_bytes(b'print("tampered")')
        finally:
            gate.set()
        deadline = time.monotonic()+10
        while time.monotonic()<deadline:
            paused = client.get(f'/api/tournaments/{tid}').json()
            if paused['status']=='PAUSED':break
            time.sleep(.02)
        assert paused['status']=='PAUSED'
        assert client.get(f'/api/tournaments/{tid}/standings').json()['completedMatches']==0
        assert 'hash' in paused['fixtures'][0]['error']
        assert client.post(f'/api/tournaments/{tid}/resume',headers=owner).status_code==409
        path.write_bytes(original)
        path.chmod(0o444)
        assert client.post(f'/api/tournaments/{tid}/resume',headers=owner).status_code==200
        completed=wait_tournament(client,tid)
        assert len(completed['fixtures'][0]['attempts'])==1
        assert len(client.get('/api/matches').json())==2
        assert client.get(f'/api/tournaments/{tid}/standings').json()['completedMatches']==1


def test_maximum_teams(tmp_path):
    _, tournaments, tid, resolve, artifacts = setup_tournament(tmp_path, 16)
    artifacts['16'] = {**artifacts['0'], 'teamId':'16', 'botId':'bot-16'}
    with pytest.raises(TournamentError):tournaments.register(tid, {'teamId':'16'}, 'bot-16', resolve)
    assert len(tournaments.get(tid)['entries']) == 16
    tournaments.start(tid,'0',resolve)
    assert len(tournaments.get(tid)['fixtures']) == 120


def test_scheduler_retries_result_commit_without_running_match_twice(tmp_path,monkeypatch):
    app=create_app(tmp_path,frame_delay_ms=0)
    with TestClient(app) as client:
        owner,_=team(client,'Commit owner');other,_=team(client,'Commit opponent')
        left,right=submit(client,owner).json(),submit(client,other).json()
        for row,key in ((left,owner),(right,other)):
            assert wait_checked(client,row['id'],key)['status']=='READY'
        tid=client.post('/api/tournaments',headers=owner,json={'name':'Commit recovery'}).json()['tournamentId']
        for row,key in ((left,owner),(right,other)):
            assert client.post(f'/api/tournaments/{tid}/entries',headers=key,json={'botId':row['id']}).status_code==200
        original=app.state.tournaments.record_result
        failures=[]
        def transient_failure(match):
            if match['status']=='COMPLETED' and len(failures)<2:
                failures.append(match['matchId'])
                raise RuntimeError('Injected temporary result commit failure')
            return original(match)
        monkeypatch.setattr(app.state.tournaments,'record_result',transient_failure)
        assert client.post(f'/api/tournaments/{tid}/start',headers=owner).status_code==200
        completed=wait_tournament(client,tid)
        assert len(failures)==2 and len(set(failures))==1
        assert len(client.get('/api/matches').json())==1
        assert completed['standings']['completedMatches']==1
        assert completed['fixtures'][0]['attempts']==[]
