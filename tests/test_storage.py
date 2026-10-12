from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
import pytest
from arena.core.storage import CapacityError, Store
from tests.test_tournaments import setup_tournament, finish


def test_connections_close_and_transactions_rollback(tmp_path):
    store=Store(tmp_path)
    with store.connect() as db:
        assert db.execute('SELECT 1').fetchone()[0]==1
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            db.execute('INSERT INTO matches VALUES (?,?)',('rollback','{"matchId":"rollback","status":"QUEUED"}'))
            raise RuntimeError('Abort transaction')
    assert store.get('rollback') is None


def test_atomic_queue_capacity_is_shared_with_tournament_scheduler(tmp_path):
    store,tournaments,tid,resolve,_=setup_tournament(tmp_path)
    tournaments.start(tid,'0',resolve)
    def enqueue(number):
        try:
            store.enqueue({'matchId':f'queued-{number}','status':'QUEUED'})
            return True
        except CapacityError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted=list(pool.map(enqueue,range(24)))
    assert sum(accepted)==store.active_count()==8
    assert tournaments.claim_next() is None
    assert all(f['status']=='SCHEDULED' for f in tournaments.get(tid)['fixtures'])
    released=store.list(None,statuses=('QUEUED',))[0]
    released['status']='COMPLETED';store.put(released)
    assert tournaments.claim_next() is not None
    assert store.active_count()==8


def test_claim_preserves_creation_time_and_completed_result_cannot_regress(tmp_path):
    store,tournaments,tid,resolve,_=setup_tournament(tmp_path)
    tournament=tournaments.start(tid,'0',resolve)
    planned=store.get(tournament['fixtures'][0]['matchId'])
    planned['createdAt']='2000-01-01T00:00:00+00:00';store.put(planned)
    claimed=tournaments.claim_next()
    assert claimed['createdAt']==planned['createdAt']
    finish(store,tournaments,claimed)
    ranking=tournaments.standings(tid)
    tournaments.record_result({**claimed,'status':'RUNNING'})
    assert tournaments.standings(tid)==ranking


def replay_for(mid,plies=30):
    state=lambda ply:{'ply':ply,'pieces':[{'at':'a1','side':'A','kind':'D'}]}
    return {'matchId':mid,'status':'RUNNING','replayRenderer':'/renderer.js','games':[
        {'sideMapping':{'A':'botA','B':'botB'},'botNames':{'botA':'one','botB':'two'},
         'initialState':state(0),'renderMetadata':{'size':9},
         'frames':[{'ply':i,'state':state(i),'events':[]} for i in range(1,plies+1)]}]}


def test_live_cache_is_detached_bounded_and_available_after_restart(tmp_path,monkeypatch):
    store=Store(tmp_path)
    store.put({'matchId':'live','status':'RUNNING'})
    replay=replay_for('live');store.save_replay(replay)
    original=deepcopy(store.live('live'))
    replay['games'][0]['frames'][-1]['state']['pieces'][0]['kind']='K'
    snapshot=store.live('live');snapshot['state']['pieces'][0]['kind']='L'
    assert store.live('live')==original
    assert len(original['frames'])==20
    def no_disk_read(mid):raise AssertionError('Live cache must avoid reading the complete replay')
    monkeypatch.setattr(store,'replay',no_disk_read)
    assert store.live('live')==original
    restarted=Store(tmp_path)
    assert restarted.live('live')==original
    reads=[]
    disk_read=restarted.replay
    monkeypatch.setattr(restarted,'replay',lambda mid:(reads.append(mid),disk_read(mid))[1])
    for number in range(32):
        mid=f'other-{number}';restarted.put({'matchId':mid,'status':'RUNNING'})
        restarted.save_replay(replay_for(mid,1))
    assert restarted.live('live')==original
    assert reads==['live']  # The least-recent entry was evicted and restored from disk.


def test_live_cache_does_not_replace_newer_frame_with_disk_result(tmp_path,monkeypatch):
    store=Store(tmp_path);store.put({'matchId':'race','status':'RUNNING'})
    old,new=replay_for('race',1),replay_for('race',2)
    def disk_read(mid):
        store.save_replay(new)
        return old
    monkeypatch.setattr(store,'replay',disk_read)
    assert store.live('race')['state']['ply']==2
