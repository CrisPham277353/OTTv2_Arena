"""SQLite metadata + atomic JSON replay files. No game-specific table."""
from datetime import datetime, timezone
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import threading

MATCH_QUEUE_LIMIT = 8


class CapacityError(ValueError):
    """A durable capacity limit was reached; callers may retry later."""


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        self.replays = directory / 'replays'
        self.replays.mkdir(parents=True, exist_ok=True)
        self.database = directory / 'arena.sqlite3'
        self._live_cache = OrderedDict()
        self._live_lock = threading.Lock()
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS matches_status_idx ON matches(json_extract(payload, '$.status'))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            # sqlite3's own context manager commits/rolls back but does not close.
            db.close()

    def put(self, match: dict):
        with self.connect() as db:
            db.execute('INSERT INTO matches VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (match['matchId'], json.dumps(match, ensure_ascii=False)))

    def get(self, match_id):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM matches WHERE id=?', (match_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit=100, *, statuses=None):
        parameters = []
        where = ''
        if statuses is not None:
            if not statuses:
                return []
            where = " WHERE json_extract(payload, '$.status') IN (" + ','.join('?' for _ in statuses) + ')'
            parameters.extend(statuses)
        sql = 'SELECT payload FROM matches' + where + ' ORDER BY rowid DESC'
        if limit is not None:
            sql += ' LIMIT ?'
            parameters.append(limit)
        with self.connect() as db:
            rows = db.execute(sql, parameters).fetchall()
        return [json.loads(row[0]) for row in rows]

    def active_count(self, db=None):
        if db is None:
            with self.connect() as connection:
                return self.active_count(connection)
        return db.execute("SELECT COUNT(*) FROM matches WHERE json_extract(payload, '$.status') IN ('QUEUED','RUNNING')").fetchone()[0]

    def enqueue(self, match, limit=MATCH_QUEUE_LIMIT):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.active_count(db) >= limit:
                raise CapacityError(f'Hàng đợi local đã đầy ({limit} trận); chờ trận hiện tại hoàn tất.')
            db.execute('INSERT INTO matches VALUES (?, ?)', (match['matchId'], json.dumps(match, ensure_ascii=False)))

    def save_replay(self, replay):
        path = self.replays / f"{replay['matchId']}.json"
        tmp = path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as file:
            json.dump(replay, file, ensure_ascii=False, separators=(',', ':'))
            file.flush()
            os.fsync(file.fileno())
        tmp.replace(path)
        self._cache_live(replay['matchId'], self._live_from_replay(replay))

    @staticmethod
    def _live_from_replay(replay):
        if not replay.get('games'):
            return None
        game = replay['games'][-1]
        if not {'frames', 'sideMapping', 'botNames', 'initialState', 'renderMetadata'} <= game.keys():
            return None
        frames = game['frames']
        return {'gameNumber': len(replay['games']), 'sideMapping': game['sideMapping'], 'botNames': game['botNames'],
                'state': frames[-1]['state'] if frames else game['initialState'],
                'renderMetadata': game['renderMetadata'], 'frames': frames[-20:], 'result': game.get('result'),
                'replayRenderer': replay.get('replayRenderer')}

    def _cache_live(self, match_id, live):
        snapshot = deepcopy(live)
        with self._live_lock:
            self._live_cache[match_id] = snapshot
            self._live_cache.move_to_end(match_id)
            while len(self._live_cache) > 32:
                self._live_cache.popitem(last=False)

    def live(self, match_id):
        with self._live_lock:
            if match_id in self._live_cache:
                self._live_cache.move_to_end(match_id)
                return deepcopy(self._live_cache[match_id])
        replay = self.replay(match_id)
        if not replay:
            return None
        live = self._live_from_replay(replay)
        # Do not replace a newer live frame that the writer published during disk read.
        with self._live_lock:
            if match_id not in self._live_cache:
                self._live_cache[match_id] = deepcopy(live)
                while len(self._live_cache) > 32:
                    self._live_cache.popitem(last=False)
            return deepcopy(self._live_cache[match_id])

    def replay(self, match_id):
        # IDs are resolved through the database first; never use arbitrary API paths.
        if not self.get(match_id):
            return None
        path = self.replays / f'{match_id}.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

    def recover(self):
        # A restart cannot resume live subprocesses. Preserve completed replay if present.
        for match in self.list(None, statuses=('RUNNING', 'QUEUED')):
            self.recover_match(match['matchId'])

    def recover_match(self, match_id, *, failed_status='INTERRUPTED', error='Server đã dừng giữa trận; hãy tạo trận mới.'):
        match = self.get(match_id)
        if not match or match['status'] not in ('RUNNING', 'QUEUED'):
            return match
        replay = self.replay(match_id)
        if replay and replay['status'] == 'COMPLETED':
            match.update({k: replay[k] for k in ('status', 'scores', 'winnerSlot', 'winnerBot', 'reason')})
            match['gameResults'] = [g['result'] for g in replay['games']]
            match.pop('error', None)
        else:
            match.update(status=failed_status, error=error)
        match.setdefault('finishedAt', now())
        self.put(match)
        return match

    def stats(self, bot_ids):
        result = {name: {'botId': name, 'matches': 0, 'wins': 0, 'losses': 0, 'gameWins': 0, 'gameLosses': 0}
                  for name in bot_ids}
        for match in self.list(None, statuses=('COMPLETED',)):
            for slot in ('botA', 'botB'):
                name = match[slot]
                row = result.setdefault(name, {'botId': name, 'matches': 0, 'wins': 0, 'losses': 0, 'gameWins': 0, 'gameLosses': 0})
                other = 'botB' if slot == 'botA' else 'botA'
                row['matches'] += 1
                row['wins'] += int(match['winnerSlot'] == slot)
                row['losses'] += int(match['winnerSlot'] != slot)
                row['gameWins'] += match['scores'][slot]
                row['gameLosses'] += match['scores'][other]
        return list(result.values())
