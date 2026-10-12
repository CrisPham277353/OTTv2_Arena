import asyncio
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import threading
import time
from typing import Literal
from uuid import uuid4
from urllib.parse import urlparse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from arena.bootstrap import ROOT, build_bots, build_registry
from arena.core.bot_runner import BotError, BotProcess
from arena.core.match_runner import MatchRunner
from arena.core.sandbox import SandboxBotProcess, SandboxRuntime, SandboxUnavailable
from arena.core.storage import Store, now, CapacityError
from arena.core.submissions import SubmissionCatalog, SubmissionStore, MAX_BODY_BYTES
from arena.core.tournaments import TournamentStore, TournamentError

log = logging.getLogger(__name__)


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    gameId: str = Field(default='ottv2', max_length=64)
    gameVersion: str | None = Field(default=None, max_length=32)
    botA: str = Field(max_length=64)
    botB: str = Field(max_length=64)
    format: Literal['BO1', 'BO3'] = 'BO1'
    seed: int = Field(default=42, ge=0, le=2**63-1, strict=True)


class TeamRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=60)


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    botName: str = Field(min_length=1, max_length=60)
    filename: str = Field(max_length=103)
    source: str = Field(min_length=1, max_length=256*1024)
    gameId: str = Field(default='ottv2', max_length=64)
    gameVersion: str | None = Field(default=None, max_length=32)


class TournamentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    gameId: str = Field(default='ottv2', max_length=64)
    gameVersion: str | None = Field(default=None, max_length=32)
    format: Literal['BO1', 'BO3'] = 'BO3'
    seed: int = Field(default=42, ge=0, le=2**63-1, strict=True)


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    botId: str = Field(min_length=1, max_length=64)


def create_app(data_dir: Path | None = None, frame_delay_ms: int | None = None):
    registry, samples = build_registry(), build_bots()
    store = Store(data_dir or Path(os.environ.get('ARENA_DATA_DIR', ROOT / 'data')))
    submissions = SubmissionStore(store, ROOT / 'bots/bot_sdk.py')
    tournaments = TournamentStore(store)
    bots = SubmissionCatalog(samples, submissions)
    runtime = SandboxRuntime()
    def process_factory(path, seed):
        if path.parent.resolve() == samples.directory:
            return BotProcess(path, seed)
        if not runtime.ready:
            raise SandboxUnavailable(runtime.message)
        return SandboxBotProcess(path, seed)
    runner = MatchRunner(registry, bots, process_factory)
    delay = frame_delay_ms if frame_delay_ms is not None else int(os.environ.get('ARENA_MOVE_DELAY_MS', '120'))
    writes = defaultdict(deque)
    write_lock, queue_lock = threading.Lock(), threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        tournaments.recover()
        await runtime.probe(store.directory / 'sandbox-probe')
        app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='arena')
        app.state.stopping = False
        try:
            # Jobs interrupted by restart re-enter validation, never gain READY automatically.
            for row in submissions.list(statuses=('PENDING_CHECK', 'CHECKING', 'SANDBOX_UNAVAILABLE')):
                if runtime.ready:
                    app.state.executor.submit(check_submission, row['id'])
                else:
                    submissions.set_status(row['id'], 'SANDBOX_UNAVAILABLE', runtime.message)
            scheduler = asyncio.create_task(schedule_tournaments())
            try:
                yield
            finally:
                app.state.stopping = True
                # Finish the current match; leave all unclaimed fixtures durable for restart.
                await scheduler
        finally:
            app.state.executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title='OTT v2 Arena', version='1.1.0', lifespan=lifespan)
    public_host = urlparse(os.environ.get('ARENA_PUBLIC_URL', '')).hostname
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost','127.0.0.1','testserver'] + ([public_host] if public_host else []))
    app.state.store, app.state.runner = store, runner
    app.state.submissions, app.state.runtime = submissions, runtime
    app.state.tournaments = tournaments
    templates = Jinja2Templates(directory=str(ROOT / 'arena/web/templates'))
    app.mount('/static', StaticFiles(directory=str(ROOT / 'arena/web/static')), name='static')

    def authorize(request):
        team = submissions.authenticate(request.headers.get('X-Team-Key'))
        if not team:
            raise HTTPException(401, 'Cần mã truy cập đội hợp lệ.')
        return team

    def limit_write(request):
        # Local limiter for one server process. Do not trust X-Forwarded-For from arbitrary callers.
        peer = request.client.host if request.client else 'unknown'
        with write_lock:
            if peer not in writes and len(writes) >= 4096:
                raise HTTPException(429, 'Server đang có nhiều yêu cầu; thử lại sau.')
            queue = writes[peer]
            moment = time.monotonic()
            while queue and queue[0] < moment - 60:
                queue.popleft()
            if len(queue) >= 20:
                raise HTTPException(429, 'Tối đa 20 thao tác ghi mỗi phút từ một địa chỉ.')
            queue.append(moment)

    @app.middleware('http')
    async def same_origin(request, call_next):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            allowed = {str(request.base_url).rstrip('/'), os.environ.get('ARENA_PUBLIC_URL', '').rstrip('/')}
            if origin and origin.rstrip('/') not in allowed:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'Yêu cầu phải gửi từ website Arena.'}, status_code=403)
        return await call_next(request)

    async def bounded_json(request, model):
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_BODY_BYTES:
                raise HTTPException(413, 'Request quá lớn; file .py tối đa 256 KiB.')
            content.extend(chunk)
        try:
            return model.model_validate_json(bytes(content))
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_context=False, include_url=False)
            messages = ['.'.join(str(part) for part in e['loc']) + ': ' + e['msg'] for e in errors[:3]]
            raise HTTPException(422, 'Dữ liệu nộp không hợp lệ: ' + '; '.join(messages)) from exc

    @app.exception_handler(TournamentError)
    async def tournament_error(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc)}, status_code=exc.status)

    @app.exception_handler(CapacityError)
    async def capacity_error(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc)}, status_code=429)

    @app.get('/')
    def index(request: Request):
        return templates.TemplateResponse(request=request, name='index.html')

    @app.get('/api/games')
    def games(): return registry.catalog()

    @app.get('/api/bots')
    def list_bots(): return bots.catalog()

    @app.get('/api/runtime')
    def runtime_info():
        return {'ready':runtime.ready, 'runtime':'bubblewrap+seccomp', 'message':runtime.message,
                'submissionMaxBytes':256*1024, 'livePollMs':250}

    @app.post('/api/teams', status_code=201, openapi_extra={'requestBody': {'required':True, 'content':{'application/json':{'schema':TeamRequest.model_json_schema()}}}})
    async def register_team(request: Request):
        limit_write(request)
        payload = await bounded_json(request, TeamRequest)
        name = payload.name.strip()
        if not name:
            raise HTTPException(422, 'Tên đội không được để trống.')
        return await asyncio.to_thread(submissions.register_team, name)

    @app.get('/api/team')
    def read_team(request: Request): return authorize(request)

    def own_submission(sid, request):
        team = authorize(request)
        record = submissions.get(sid)
        if not record or record['teamId'] != team['teamId']:
            raise HTTPException(404, 'Không tìm thấy bài nộp của đội.')
        return record

    @app.get('/api/submissions')
    def list_submissions(request: Request):
        team = authorize(request)
        return submissions.list(team_id=team['teamId'])

    async def validate(sid):
        row = submissions.get(sid)
        manifest, plugin = registry.get(row['gameId'], row['gameVersion'])
        path = submissions.verify(sid)
        process = SandboxBotProcess(path, 42)
        state = plugin.create({'gameInstanceId':f'check:{sid}'}, 42, ('A','B'))
        side = plugin.status(state).turn
        opponent = 'B' if side == 'A' else 'A'
        try:
            await process.start()
            # Several decisions from the same persistent process; check both protocol and legal moves.
            for turn in range(6):
                status = plugin.status(state)
                if status.terminal:
                    break
                request = {'type':'observation', 'protocolVersion':'1.0', 'requestId':f'{sid}:check:{turn}',
                           'turnId':status.ply, 'gameId':row['gameId'], 'gameVersion':row['gameVersion'],
                           'playerId':side, 'deadlineMs':500, 'seed':42, 'observation':plugin.observe(state, side)}
                action = await process.decide(request)
                state = plugin.step(state, side, action).state
                if not plugin.status(state).terminal:
                    action = plugin.legal_actions(state, opponent)[0]
                    state = plugin.step(state, opponent, action).state
        finally:
            await process.close()

    def check_submission(sid):
        from arena.core.plugin import IllegalAction
        submissions.set_status(sid, 'CHECKING', 'Đang kiểm tra JSONL và nước đi trong sandbox…')
        try:
            if not runtime.ready:
                raise SandboxUnavailable(runtime.message)
            asyncio.run(validate(sid))
        except SandboxUnavailable as exc:
            submissions.set_status(sid, 'SANDBOX_UNAVAILABLE', str(exc))
        except (BotError, IllegalAction, ValueError) as exc:
            submissions.set_status(sid, 'CHECK_FAILED', str(exc))
        except Exception:
            log.exception('Submission validation failed: %s', sid)
            submissions.set_status(sid, 'CHECK_FAILED', 'Lỗi hệ thống khi kiểm tra bài nộp. Xem log server.')
        else:
            submissions.set_status(sid, 'READY', 'Đã qua kiểm tra cú pháp, JSONL và 6 nước đi hợp lệ trong sandbox. Có thể thi đấu.')

    @app.post('/api/submissions', status_code=201, openapi_extra={'requestBody': {'required':True, 'content':{'application/json':{'schema':SourceRequest.model_json_schema()}}}})
    async def submit_source(request: Request):
        team = authorize(request)
        limit_write(request)
        payload = await bounded_json(request, SourceRequest)
        try:
            manifest, _ = registry.get(payload.gameId, payload.gameVersion)
            if not payload.botName.strip():
                raise ValueError('Tên bot không được để trống.')
            row = await asyncio.to_thread(submissions.submit, team['name'], payload.botName.strip(), payload.filename, payload.source,
                                          payload.gameId, manifest['gameVersion'], team['teamId'])
        except CapacityError:
            raise
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        if row['status'] == 'PENDING_CHECK':
            if runtime.ready:
                with queue_lock:
                    pending = submissions.pending_count()
                    if pending > 16:
                        row = submissions.set_status(row['id'], 'CHECK_FAILED', 'Hàng đợi kiểm tra đầy; hãy thử nộp lại sau.')
                    else:
                        app.state.executor.submit(check_submission, row['id'])
            else:
                row = submissions.set_status(row['id'], 'SANDBOX_UNAVAILABLE', runtime.message)
        return row

    @app.get('/api/submissions/{sid}')
    def read_submission(sid: str, request: Request): return own_submission(sid, request)

    @app.get('/api/submissions/{sid}/source')
    def download_source(sid: str, request: Request):
        own_submission(sid, request)
        try:
            path = submissions.verify(sid)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, 'File bài nộp không còn đúng hash.') from exc
        return PlainTextResponse(path.read_text(encoding='utf-8'),
                                 headers={'Content-Disposition':'attachment; filename="bot.py"'})

    def execute(match):
        match.update(status='RUNNING', startedAt=now())
        store.put(match)
        try:
            if match.get('tournamentId'):
                tournament = tournaments.get(match['tournamentId'])
                for entry in tournament['entries']:
                    if entry['botId'] not in (match['botA'], match['botB']):
                        continue
                    actual = resolve_entry(tournament, entry['teamId'], entry['botId'])
                    if any(actual[key] != entry[key] for key in ('botVersion', 'artifactSha256', 'sourceSha256')):
                        raise TournamentError('Artifact không khớp phiên bản đã khóa.')
            def progress(replay):
                if match.get('tournamentId'):
                    replay.update(tournamentId=match['tournamentId'], fixtureId=match['fixtureId'])
                store.save_replay(replay)
                match.update(scores=replay['scores'].copy(), gameResults=[g['result'] for g in replay['games'] if 'result' in g])
                store.put(match)
            replay = asyncio.run(runner.run_match(match['matchId'], match['gameId'], match['botA'], match['botB'],
                                                 match['format'], match['seed'], progress, match['gameVersion'], max(0,delay)))
            if match.get('tournamentId'):
                replay.update(tournamentId=match['tournamentId'], fixtureId=match['fixtureId'])
            store.save_replay(replay)
            match.update({k: replay[k] for k in ('status','scores','winnerSlot','winnerBot','reason')})
            match['gameResults'] = [g['result'] for g in replay['games']]
        except TournamentError as exc:
            match.update(status='FAILED', error=str(exc))
        except Exception:
            log.exception('Match infrastructure failure: %s', match['matchId'])
            match.update(status='FAILED', error='Lỗi hệ thống/runtime khi chạy trận. Xem log server.')
        match['finishedAt'] = now()
        store.put(match)

    def execute_fixture(match):
        tournaments.record_result({**match, 'status': 'RUNNING'})
        execute(match)
        tournaments.record_result(store.get(match['matchId']))

    async def schedule_tournaments():
        unsettled = None
        def settle(match_id):
            saved = store.recover_match(match_id, failed_status='FAILED',
                error='Lỗi hệ thống khi điều phối trận. Xem log server.')
            tournaments.record_result(saved)
        while not app.state.stopping:
            try:
                if unsettled:
                    # Retry only the result commit, never an already executed bot match.
                    await asyncio.to_thread(settle, unsettled)
                    unsettled = None
                match = await asyncio.to_thread(tournaments.claim_next)
                if match:
                    unsettled = match['matchId']
                    await asyncio.get_running_loop().run_in_executor(app.state.executor, execute_fixture, match)
                    unsettled = None
                else:
                    await asyncio.sleep(.2)
            except Exception:
                log.exception('Tournament scheduler failure')
                await asyncio.sleep(.5)

    def resolve_entry(tournament, team_id, bot_id):
        row = submissions.get(bot_id)
        if not row or row['teamId'] != team_id:
            raise TournamentError('Chỉ được đăng ký bot do đội mình nộp.', 403)
        if row['status'] != 'READY':
            raise TournamentError('Bot phải đạt kiểm tra sandbox (READY) trước khi đăng ký.', 422)
        if (row['gameId'], row['gameVersion']) != (tournament['gameId'], tournament['gameVersion']):
            raise TournamentError('Bot không tương thích bộ luật đã chọn cho giải.', 422)
        try:
            submissions.verify(bot_id)
        except (ValueError, OSError, KeyError) as exc:
            raise TournamentError('File bot không còn đúng hash; hãy nộp phiên bản mới trước khi khóa giải.') from exc
        return {'teamId': team_id, 'teamName': row['team'], 'botId': bot_id, 'botLabel': row['name'],
                'botName': row['botName'], 'botVersion': row['version'], 'gameVersion': row['gameVersion'],
                'sourceSha256': row['sourceSha256'], 'artifactSha256': row['artifactSha256']}

    @app.post('/api/tournaments', status_code=201, openapi_extra={'requestBody': {'required':True, 'content':{'application/json':{'schema':TournamentRequest.model_json_schema()}}}})
    async def create_tournament(request: Request):
        team = authorize(request)
        limit_write(request)
        payload = await bounded_json(request, TournamentRequest)
        try:
            manifest, _ = registry.get(payload.gameId, payload.gameVersion)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from exc
        return tournaments.create(payload.name, team, payload.gameId, manifest['gameVersion'], payload.format, payload.seed)

    @app.get('/api/tournaments')
    def list_tournaments():
        return [{k: v for k, v in row.items() if k not in ('entries', 'fixtures')} |
                {'teamCount': len(row['entries']), 'totalMatches': len(row['fixtures']),
                 'completedMatches': sum(f['status'] == 'COMPLETED' for f in row['fixtures'])}
                for row in tournaments.list()]

    @app.get('/api/tournaments/{tournament_id}')
    def read_tournament(tournament_id: str):
        tournament = tournaments.get(tournament_id)
        return {**tournament, 'standings': tournaments.standings(tournament_id, tournament=tournament)}

    @app.get('/api/tournaments/{tournament_id}/standings')
    def read_standings(tournament_id: str):
        return tournaments.standings(tournament_id)

    @app.post('/api/tournaments/{tournament_id}/entries', openapi_extra={'requestBody': {'required':True, 'content':{'application/json':{'schema':EntryRequest.model_json_schema()}}}})
    async def register_entry(tournament_id: str, request: Request):
        team = authorize(request)
        limit_write(request)
        payload = await bounded_json(request, EntryRequest)
        return tournaments.register(tournament_id, team, payload.botId, resolve_entry)

    @app.post('/api/tournaments/{tournament_id}/withdraw')
    def withdraw_entry(tournament_id: str, request: Request):
        team = authorize(request)
        limit_write(request)
        return tournaments.withdraw(tournament_id, team['teamId'])

    @app.post('/api/tournaments/{tournament_id}/start')
    def start_tournament(tournament_id: str, request: Request):
        team = authorize(request)
        limit_write(request)
        # Check authority and state before disclosing runtime or bot diagnostics.
        tournament = tournaments.get(tournament_id)
        tournaments._organizer(tournament, team['teamId'])
        if not runtime.ready:
            raise HTTPException(503, runtime.message)
        return tournaments.start(tournament_id, team['teamId'], resolve_entry)

    @app.post('/api/tournaments/{tournament_id}/resume')
    def resume_tournament(tournament_id: str, request: Request):
        team = authorize(request)
        limit_write(request)
        tournament = tournaments.get(tournament_id)
        tournaments._organizer(tournament, team['teamId'])
        if not runtime.ready:
            raise HTTPException(503, runtime.message)
        return tournaments.resume(tournament_id, team['teamId'], resolve_entry)

    @app.post('/api/matches', status_code=202, openapi_extra={'requestBody': {'required':True, 'content':{'application/json':{'schema':MatchRequest.model_json_schema()}}}})
    async def start_match(request: Request):
        limit_write(request)
        payload = await bounded_json(request, MatchRequest)
        try:
            manifest, _ = registry.get(payload.gameId, payload.gameVersion)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from exc
        catalog = bots.by_id
        selected = []
        for bot in (payload.botA,payload.botB):
            if bot not in catalog or payload.gameId not in catalog[bot][0].get('gameIds', []):
                raise HTTPException(422, f'Bot chưa qua kiểm tra hoặc chưa đăng ký cho game: {bot}')
            entry = catalog[bot][0]
            if entry.get('gameVersion',manifest['gameVersion']) != manifest['gameVersion']:
                raise HTTPException(422, 'Phiên bản bot không tương thích gameVersion.')
            if entry.get('source') == 'submission':
                selected.append(submissions.get(bot))
                try: bots.path(bot)
                except (ValueError,OSError) as exc:
                    raise HTTPException(409, 'Mã bot đã thay đổi; hãy nộp phiên bản mới.') from exc
        if selected:
            team = authorize(request)
            if not any(row['teamId'] == team['teamId'] for row in selected):
                raise HTTPException(403, 'Đội phải sở hữu ít nhất một bot trong trận.')
            if not runtime.ready:
                raise HTTPException(503, runtime.message)
        with queue_lock:
            match = {**payload.model_dump(), 'gameVersion':manifest['gameVersion'], 'matchId':uuid4().hex,
                     'createdAt':now(), 'status':'QUEUED', 'scores':{'botA':0,'botB':0}, 'gameResults':[],
                     'botLabels':{bot:catalog[bot][0]['name'] for bot in (payload.botA,payload.botB)}}
            store.enqueue(match)
            app.state.executor.submit(execute, match.copy())
        return {'matchId':match['matchId'],'status':'QUEUED'}

    @app.get('/api/matches')
    def history(limit: int = 50): return store.list(max(1,min(limit,200)))

    @app.get('/api/matches/{match_id}')
    def read_match(match_id: str):
        match = store.get(match_id)
        if not match: raise HTTPException(404,'Không tìm thấy trận')
        return match

    @app.get('/api/matches/{match_id}/replay')
    def read_replay(match_id: str):
        read_match(match_id)
        replay = store.replay(match_id)
        if not replay: raise HTTPException(409,'Replay chưa sẵn sàng; chờ snapshot đầu tiên.')
        if 'seed' in replay:
            replay['seedText'] = str(replay['seed'])
        return replay

    @app.get('/api/matches/{match_id}/live')
    def read_live(match_id: str):
        match = read_match(match_id)
        return {'match':match,'game':store.live(match_id)}

    @app.get('/api/stats')
    def stats(): return store.stats(bots.by_id)
    return app


app = create_app()
