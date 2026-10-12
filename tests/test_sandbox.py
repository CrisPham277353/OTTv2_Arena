import asyncio
from pathlib import Path
import pytest
from arena.core.sandbox import SandboxBotProcess, SandboxUnavailable


def run_bot(tmp_path, source):
    script=tmp_path/'bot.py'
    script.write_text(source)
    async def run():
        p=SandboxBotProcess(script,42)
        try:
            await p.start()
            return await p.decide({'requestId':'safety','turnId':0,'observation':{}})
        finally:await p.close()
    return asyncio.run(run())


def test_files_network_process_and_environment_are_isolated(tmp_path,monkeypatch):
    secret=tmp_path.parent/'host-secret.txt'
    secret.write_text('private host secret')
    monkeypatch.setenv('ARENA_TEST_SECRET','do-not-expose')
    source=f'''import os,socket,json,sys,resource
blocked=[]
for name,fn in [('host_file',lambda:open({str(secret)!r})),('write_bot',lambda:open('/bot/bot.py','w')),('write_root',lambda:open('/host-write','w')),('network',lambda:socket.socket()),('process',lambda:os.fork()),('reset_limits',lambda:resource.setrlimit(resource.RLIMIT_AS,(resource.RLIM_INFINITY,resource.RLIM_INFINITY)))]:
 try:fn()
 except (OSError,ValueError):blocked.append(name)
assert 'ARENA_TEST_SECRET' not in os.environ
assert 'X-Team-Key' not in os.environ
for line in sys.stdin:
 r=json.loads(line);print(json.dumps({{'type':'action','protocolVersion':'1.0','requestId':r['requestId'],'turnId':r['turnId'],'action':{{'blocked':blocked}}}}),flush=True)
'''
    action=run_bot(tmp_path,source)
    assert set(action['blocked'])=={'host_file','write_bot','write_root','network','process','reset_limits'}
    assert secret.read_text()=='private host secret'


def test_memory_ceiling(tmp_path):
    source='''import json,sys
try:
 data=bytearray(400*1024*1024)
 result=False
except MemoryError:result=True
for line in sys.stdin:
 r=json.loads(line);print(json.dumps({'type':'action','protocolVersion':'1.0','requestId':r['requestId'],'turnId':r['turnId'],'action':{'limited':result}}),flush=True)
'''
    assert run_bot(tmp_path,source)['limited'] is True


def test_missing_runtime_never_falls_back(tmp_path,monkeypatch):
    monkeypatch.setattr('arena.core.sandbox.shutil.which',lambda _:None)
    with pytest.raises(SandboxUnavailable):run_bot(tmp_path,'print("unsafe")')
