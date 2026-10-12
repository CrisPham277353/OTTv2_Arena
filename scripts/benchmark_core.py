"""Reproducible, synthetic core measurements; never touches the application's data."""
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from arena.core.storage import Store
from arena.core.tournaments import TournamentStore


def measure(function, count=30):
    start=time.perf_counter()
    for _ in range(count):function()
    return round(1000*(time.perf_counter()-start)/count,3)


def main():
    with tempfile.TemporaryDirectory(prefix='ott-benchmark-') as folder:
        store=Store(Path(folder));tournaments=TournamentStore(store)
        with store.connect() as db:
            db.executemany('INSERT INTO matches VALUES (?,?)',[(str(i),json.dumps({'matchId':str(i),'status':'COMPLETED'})) for i in range(10000)])
            db.executemany('INSERT INTO tournaments VALUES (?,?)',[(str(i),json.dumps({'tournamentId':str(i),'status':'COMPLETED',
                'fixtures':[{'number':n,'status':'COMPLETED','matchId':f'{i}-{n}'} for n in range(120)]})) for i in range(100)])
        pieces=[{'at':chr(97+i%9)+str(1+i//9),'side':'A' if i<9 else 'B','kind':'D'} for i in range(18)]
        replay={'matchId':'live-benchmark','status':'RUNNING','replayRenderer':'/renderer.js','games':[
            {'sideMapping':{'A':'botA','B':'botB'},'botNames':{'botA':'a','botB':'b'},'renderMetadata':{'size':9},
             'initialState':{'ply':0,'pieces':pieces},
             'frames':[{'ply':i,'state':{'ply':i,'pieces':pieces},'events':[]} for i in range(1,301)]}]}
        store.put({'matchId':replay['matchId'],'status':'RUNNING'});store.save_replay(replay)
        def idle_scan():
            return next((t for t in tournaments.list() if t['status']=='RUNNING'),None)
        output={'fixture':{'matches':10000,'completedTournaments':100,'fixturesPerTournament':120,'replayFrames':300},
                'millisecondsPerCall':{
                    'queueFullScan':measure(lambda:sum(m['status'] in ('QUEUED','RUNNING') for m in store.list(None))),
                    'queueIndexedCount':measure(store.active_count),
                    'schedulerFullScan':measure(idle_scan),'schedulerIndexedClaim':measure(tournaments.claim_next),
                    'completeReplayDiskRead':measure(lambda:store.replay(replay['matchId'])),
                    'liveSnapshotCache':measure(lambda:store.live(replay['matchId']))}}
        if Path('/proc/self/fd').exists():
            gc.collect();before=len(os.listdir('/proc/self/fd'));enabled=gc.isenabled();gc.disable()
            try:
                for _ in range(200):store.get('1')
                after=len(os.listdir('/proc/self/fd'))
            finally:
                if enabled:gc.enable()
                gc.collect()
            output['fileDescriptors']={'before':before,'after200Reads':after,'gcDisabledDuringReads':True}
        print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
