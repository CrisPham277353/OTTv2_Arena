"""Persistent JSONL subprocess. Local resource guards, NOT a security sandbox."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys

MAX_LINE = 64 * 1024
MAX_STDERR = 1024 * 1024


class BotError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f'{code}: {message}')


class BotCatalog:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.entries = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        self.by_id = {}
        for entry in self.entries:
            path = (self.directory / entry['script']).resolve()
            if path.parent != self.directory or path.suffix != '.py' or not path.is_file():
                raise ValueError('Bot must be a registered Python script directly inside bots/')
            if entry['id'] in self.by_id:
                raise ValueError('Duplicate bot id')
            self.by_id[entry['id']] = (entry, path)

    def path(self, bot_id: str) -> Path:
        return self.by_id[bot_id][1]

    def catalog(self):
        return [{k: v for k, v in e.items() if k != 'script'} for e in self.entries]


class BotProcess:
    def __init__(self, script: Path, seed: int, deadline_ms: int = 500):
        self.script, self.seed, self.deadline_ms = script, seed, deadline_ms
        self.process = None
        self.stderr_task = None
        self.stderr_log = bytearray()
        self.stderr_bytes = 0
        self.output_error = None

    async def start(self):
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, '-u', str(self.script), cwd=str(self.script.parent),
                env={**os.environ, 'ARENA_BOT_SEED': str(self.seed)},
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=MAX_LINE,
                start_new_session=(os.name == 'posix'))
            self.stderr_task = asyncio.create_task(self._drain_stderr())
        except OSError as exc:
            raise BotError('BOT_CRASH', str(exc)) from exc

    async def _drain_stderr(self):
        while chunk := await self.process.stderr.read(4096):
            self.stderr_bytes += len(chunk)
            # Bounded log kept in replay; continue draining to prevent pipe deadlock.
            available = 8192 - len(self.stderr_log)
            if available > 0:
                self.stderr_log.extend(chunk[:available])
            if self.stderr_bytes > MAX_STDERR:
                self.output_error = 'stderr exceeded 1 MiB per game'
                self._kill_group()
                break

    async def decide(self, envelope: dict) -> dict:
        async def exchange():
            if self.output_error:
                raise BotError('OUTPUT_LIMIT', self.output_error)
            if self.process.returncode is not None:
                raise BotError('BOT_CRASH', f'Process exited with code {self.process.returncode}')
            self.process.stdin.write((json.dumps(envelope, ensure_ascii=False) + '\n').encode())
            await self.process.stdin.drain()
            try:
                line = await self.process.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError) as exc:
                raise BotError('OUTPUT_LIMIT', 'stdout line exceeds 64 KiB') from exc
            if self.output_error:
                raise BotError('OUTPUT_LIMIT', self.output_error)
            if not line:
                raise BotError('BOT_CRASH', 'stdout closed before an action was returned')
            if len(line) > MAX_LINE or not line.endswith(b'\n'):
                raise BotError('OUTPUT_LIMIT', 'Expected a JSONL line of at most 64 KiB')
            try:
                response = json.loads(line)
            except (ValueError, UnicodeDecodeError, RecursionError) as exc:
                raise BotError('PROTOCOL_ERROR', 'Invalid JSON or UTF-8 on stdout') from exc
            if (not isinstance(response, dict) or response.get('type') != 'action'
                    or response.get('protocolVersion') != '1.0'
                    or response.get('requestId') != envelope['requestId']
                    or type(response.get('turnId')) is not int
                    or response['turnId'] != envelope['turnId']
                    or not isinstance(response.get('action'), dict)):
                raise BotError('PROTOCOL_ERROR', 'Invalid action envelope or mismatched requestId/turnId')
            return response['action']
        try:
            return await asyncio.wait_for(exchange(), self.deadline_ms / 1000)
        except TimeoutError as exc:
            raise BotError('TIMEOUT', f'Decision exceeded {self.deadline_ms} ms') from exc
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise BotError('BOT_CRASH', 'Bot closed stdin') from exc

    def _kill_group(self):
        if not self.process:
            return
        try:
            if os.name == 'posix':
                os.killpg(self.process.pid, signal.SIGKILL)
            elif self.process.returncode is None:
                self.process.kill()
        except ProcessLookupError:
            pass

    async def close(self):
        self._kill_group()
        if self.stderr_task:
            self.stderr_task.cancel()
            await asyncio.gather(self.stderr_task, return_exceptions=True)
        if self.process:
            # Close pipes BEFORE wait: a flooded paused stdout can otherwise deadlock.
            for stream in (self.process.stdout, self.process.stderr):
                if stream:
                    # Close pipe transports even if a Windows child inherited a pipe.
                    stream._transport.close()
            await asyncio.wait_for(self.process.wait(), 5)

    def logs(self):
        return {'stderr': self.stderr_log.decode('utf-8', errors='replace'),
                'stderrBytes': self.stderr_bytes, 'truncated': self.stderr_bytes > len(self.stderr_log)}
