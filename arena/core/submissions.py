"""Persistent, versioned local bot submissions; receiving code never executes it."""
import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
import hmac
from uuid import uuid4
from arena.core.storage import now, CapacityError

MAX_TEAMS = 1000
MAX_SUBMISSIONS = 1000
MAX_TEAM_SUBMISSIONS = 100

MAX_SOURCE_BYTES = 256 * 1024
MAX_BODY_BYTES = 2 * MAX_SOURCE_BYTES


def artifact_digest(files: dict[str, bytes]) -> str:
    # Includes trusted SDK and entry point; independent of client filename.
    return sha256(json.dumps({name: sha256(data).hexdigest() for name, data in sorted(files.items())},
                             sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class SubmissionStore:
    def __init__(self, store, sdk_path: Path):
        self.store, self.sdk_path = store, sdk_path
        self.directory = (store.directory / 'submissions').resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS teams (id TEXT PRIMARY KEY, name TEXT NOT NULL, key_hash TEXT NOT NULL)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS teams_key_hash_idx ON teams(key_hash)')
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS bot_versions (
                id TEXT PRIMARY KEY, team TEXT NOT NULL, bot_name TEXT NOT NULL,
                version INTEGER NOT NULL, payload TEXT NOT NULL,
                UNIQUE(team, bot_name, version))''')
            db.execute("CREATE INDEX IF NOT EXISTS bot_versions_status_idx ON bot_versions(json_extract(payload, '$.status'))")

    def register_team(self, name):
        team_id, key = uuid4().hex, secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM teams').fetchone()[0] >= MAX_TEAMS:
                raise CapacityError(f'Đã đạt giới hạn {MAX_TEAMS} đội trên server này.')
            db.execute('INSERT INTO teams VALUES (?, ?, ?)', (team_id, name, sha256(key.encode()).hexdigest()))
        return {'teamId': team_id, 'name': name, 'teamKey': key}

    def authenticate(self, key):
        if not key:
            return None
        hashed = sha256(key.encode()).hexdigest()
        with self.store.connect() as db:
            row = db.execute('SELECT id, name, key_hash FROM teams WHERE key_hash=?', (hashed,)).fetchone()
        if row and hmac.compare_digest(row[2], hashed):
            return {'teamId': row[0], 'name': row[1]}
        return None

    def submit(self, team, bot_name, filename, source, game_id, game_version, team_id=None):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.py', filename):
            raise ValueError('Tên file phải là .py, chỉ chứa chữ/số/dấu _ - .; không chứa đường dẫn.')
        content = source.encode('utf-8')
        if not content or len(content) > MAX_SOURCE_BYTES:
            raise ValueError('File Python phải từ 1 byte đến 256 KiB.')
        status, validation = 'PENDING_CHECK', 'Cú pháp Python hợp lệ; đang chờ kiểm tra protocol trong sandbox.'
        try:
            ast.parse(source, filename=filename)
        except (SyntaxError, ValueError, RecursionError) as exc:
            status = 'INVALID'
            if isinstance(exc, SyntaxError):
                validation = f'Lỗi cú pháp dòng {exc.lineno}, cột {exc.offset}: {exc.msg}'
            else:
                validation = f'Không phân tích được mã Python: {exc}'
        sdk = self.sdk_path.read_bytes()
        files = {'bot.py': content, 'bot_sdk.py': sdk}
        sid = 'submitted-' + uuid4().hex
        folder = self.directory / sid
        # Transaction allocates version numbers atomically, even for simultaneous submissions.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if (db.execute('SELECT COUNT(*) FROM bot_versions').fetchone()[0] >= MAX_SUBMISSIONS
                    or db.execute('SELECT COUNT(*) FROM bot_versions WHERE team=?', (team_id or team,)).fetchone()[0] >= MAX_TEAM_SUBMISSIONS):
                raise CapacityError(f'Đã đạt giới hạn bài nộp ({MAX_TEAM_SUBMISSIONS}/đội, {MAX_SUBMISSIONS}/server).')
            previous = db.execute('SELECT COALESCE(MAX(version),0) FROM bot_versions WHERE team=? AND bot_name=?',
                                  (team_id or team, bot_name)).fetchone()[0]
            version = previous + 1
            record = {'id': sid, 'team': team, 'teamId': team_id, 'botName': bot_name, 'version': version,
                      'name': f'{team} / {bot_name} · v{version}', 'filename': filename,
                      'gameId': game_id, 'gameVersion': game_version, 'status': status,
                      'createdAt': now(), 'validation': validation,
                      'sourceSha256': sha256(content).hexdigest(), 'artifactSha256': artifact_digest(files),
                      'fileSha256': {n: sha256(data).hexdigest() for n, data in files.items()}}
            folder.mkdir()
            for name, data in files.items():
                path = folder / name
                path.write_bytes(data)
                path.chmod(0o444)
            db.execute('INSERT INTO bot_versions VALUES (?, ?, ?, ?, ?)',
                       (sid, team_id or team, bot_name, version, json.dumps(record, ensure_ascii=False)))
        return record

    def get(self, sid):
        with self.store.connect() as db:
            row = db.execute('SELECT payload FROM bot_versions WHERE id=?', (sid,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, *, team_id=None, statuses=None):
        conditions, parameters = [], []
        if team_id is not None:
            conditions.append('team=?')
            parameters.append(team_id)
        if statuses is not None:
            if not statuses:
                return []
            conditions.append("json_extract(payload, '$.status') IN (" + ','.join('?' for _ in statuses) + ')')
            parameters.extend(statuses)
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with self.store.connect() as db:
            rows = db.execute('SELECT payload FROM bot_versions' + where + ' ORDER BY rowid DESC', parameters).fetchall()
        return [json.loads(row[0]) for row in rows]

    def pending_count(self):
        with self.store.connect() as db:
            return db.execute("SELECT COUNT(*) FROM bot_versions WHERE json_extract(payload, '$.status') IN ('PENDING_CHECK','CHECKING')").fetchone()[0]

    def folder(self, sid):
        if not self.get(sid):
            raise KeyError(sid)
        return self._folder(sid)

    def _folder(self, sid):
        if not re.fullmatch(r'submitted-[a-f0-9]{32}', sid):
            raise KeyError(sid)
        folder = self.directory / sid
        if folder.is_symlink() or folder.resolve().parent != self.directory:
            raise ValueError('Submission path was modified')
        return folder

    def verify(self, sid):
        record = self.get(sid)
        if not record:
            raise KeyError(sid)
        folder = self._folder(sid)
        if {p.name for p in folder.iterdir()} != set(record['fileSha256']):
            raise ValueError('Submission contains unexpected files')
        files = {}
        for name, expected in record['fileSha256'].items():
            path = folder / name
            if path.is_symlink() or path.resolve().parent != folder or not path.is_file():
                raise ValueError('Submission files were modified')
            content = path.read_bytes()
            if sha256(content).hexdigest() != expected:
                raise ValueError('Submission hash mismatch; submit a new version')
            files[name] = content
        if artifact_digest(files) != record['artifactSha256']:
            raise ValueError('Submission artifact hash mismatch')
        return folder / 'bot.py'

    def set_status(self, sid, status, message):
        if status not in ('PENDING_CHECK', 'CHECKING', 'READY', 'CHECK_FAILED', 'SANDBOX_UNAVAILABLE'):
            raise ValueError('Invalid submission status')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM bot_versions WHERE id=?', (sid,)).fetchone()
            if not row:
                raise KeyError(sid)
            record = json.loads(row[0])
            record.update(status=status, validation=message, checkedAt=now())
            db.execute('UPDATE bot_versions SET payload=? WHERE id=?', (json.dumps(record, ensure_ascii=False), sid))
        return record


class SubmissionCatalog:
    """The same game-independent runner can use registered submissions or sample bots."""
    def __init__(self, samples, submissions):
        self.samples, self.submissions = samples, submissions

    @property
    def by_id(self):
        entries = self.samples.by_id.copy()
        for row in self.submissions.list(statuses=('READY',)):
            entries[row['id']] = ({'id': row['id'], 'name': row['name'], 'description': 'Bot do đội tự viết và nộp',
                'gameIds': [row['gameId']], 'gameVersion': row['gameVersion'],
                'team': row['team'], 'version': row['version'], 'source': 'submission',
                'artifactSha256': row['artifactSha256']}, self.submissions.directory / row['id'] / 'bot.py')
        return entries

    def path(self, bot_id):
        if bot_id in self.samples.by_id:
            return self.samples.path(bot_id)
        record = self.submissions.get(bot_id)
        if not record or record['status'] != 'READY':
            raise KeyError('Bot submission has not passed sandbox validation')
        return self.submissions.verify(bot_id)

    def catalog(self):
        return [{**entry, 'source': entry.get('source', 'sample')} for entry, _ in self.by_id.values()]
