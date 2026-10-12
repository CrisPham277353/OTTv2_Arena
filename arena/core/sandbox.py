"""Fail-closed Linux Bubblewrap + seccomp runtime for submitted Python bots."""
import asyncio
import os
from pathlib import Path
import shutil
import sys
from arena.core.bot_runner import BotError, BotProcess, MAX_LINE

BOOTSTRAP = Path(__file__).with_name('sandbox_bootstrap.py')


class SandboxUnavailable(RuntimeError):
    pass


class SandboxBotProcess(BotProcess):
    def command(self):
        binary = shutil.which('bwrap')
        if sys.platform != 'linux' or not binary:
            raise SandboxUnavailable('Cần Linux, bubblewrap và libseccomp2 để chạy bài nộp; không có fallback subprocess.')
        cmd = [binary, '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
               '--clearenv', '--setenv', 'PATH', '/usr/bin', '--setenv', 'LANG', 'C.UTF-8',
               '--setenv', 'HOME', '/tmp', '--setenv', 'ARENA_BOT_SEED', str(self.seed),
               '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--ro-bind', '/usr', '/usr']
        for path in ('/lib', '/lib64'):
            if Path(path).exists():
                cmd += ['--ro-bind', path, path]
        return cmd + ['--proc', '/proc', '--dev', '/dev', '--size', str(64 * 1024 * 1024), '--tmpfs', '/tmp',
                      '--ro-bind', str(self.script.parent.resolve()), '/bot',
                      '--ro-bind', str(BOOTSTRAP), '/bootstrap.py', '--chdir', '/bot', '--remount-ro', '/',
                      '--', '/usr/bin/python3', '-I', '-S', '-u', '/bootstrap.py', f'/bot/{self.script.name}']

    async def start(self):
        try:
            self.process = await asyncio.create_subprocess_exec(*self.command(),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=MAX_LINE,
                env={'PATH': '/usr/bin:/bin'}, start_new_session=True)
            self.stderr_task = asyncio.create_task(self._drain_stderr())
            # A startup handshake separates namespace/setup failures from the 500ms decision budget.
            line = await asyncio.wait_for(self.process.stdout.readline(), 5)
            if line != b'ARENA_SANDBOX_READY\n':
                await asyncio.sleep(0)
                raise SandboxUnavailable('Sandbox không khởi động được: ' + self.logs()['stderr'][:1000])
        except (OSError, TimeoutError) as exc:
            raise SandboxUnavailable(f'Sandbox không sẵn sàng: {exc}') from exc

    def logs(self):
        return {**super().logs(), 'runtime': 'bubblewrap+seccomp'}


class SandboxRuntime:
    def __init__(self):
        self.ready = False
        self.message = 'Chưa kiểm tra runtime'

    async def probe(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        script = directory / 'probe.py'
        script.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({'type':'action','protocolVersion':'1.0','requestId':r['requestId'],'turnId':r['turnId'],'action':{'type':'PROBE'}}),flush=True)\n")
        p = SandboxBotProcess(script, 42)
        try:
            await p.start()
            action = await p.decide({'requestId':'probe', 'turnId':0, 'observation':{}})
            self.ready = action == {'type':'PROBE'}
            self.message = 'Linux namespace + seccomp hoạt động' if self.ready else 'Probe không hợp lệ'
        except (SandboxUnavailable, BotError) as exc:
            self.ready, self.message = False, str(exc)
        finally:
            await p.close()
        return self.ready
