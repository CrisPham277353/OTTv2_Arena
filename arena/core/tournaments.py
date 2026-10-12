"""Durable round-robin competitions. No dependency on a game implementation."""
from hashlib import sha256
import json
from uuid import uuid4
from arena.core.storage import now, MATCH_QUEUE_LIMIT

MAX_TEAMS = 16


class TournamentError(Exception):
    def __init__(self, message, status=409):
        self.status = status
        super().__init__(message)


def round_robin(team_ids):
    """Circle schedule: one pairing per team/round; an odd field gets a bye."""
    ring = list(team_ids)
    if len(ring) % 2:
        ring.append(None)
    schedule = []
    for round_index in range(len(ring) - 1):
        for index in range(len(ring) // 2):
            left, right = ring[index], ring[-1-index]
            if left is None or right is None:
                continue
            if (round_index + index) % 2:
                left, right = right, left
            schedule.append((round_index + 1, left, right))
        ring = [ring[0], ring[-1], *ring[1:-1]]
    return schedule


class TournamentStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tournaments (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS tournaments_status_idx ON tournaments(json_extract(payload, '$.status'))")

    @staticmethod
    def _load(db, tournament_id):
        row = db.execute('SELECT payload FROM tournaments WHERE id=?', (tournament_id,)).fetchone()
        if not row:
            raise TournamentError('Không tìm thấy giải đấu.', 404)
        return json.loads(row[0])

    @staticmethod
    def _save(db, tournament):
        db.execute('INSERT INTO tournaments VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (tournament['tournamentId'], json.dumps(tournament, ensure_ascii=False)))

    @staticmethod
    def _save_match(db, match):
        db.execute('INSERT INTO matches VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (match['matchId'], json.dumps(match, ensure_ascii=False)))

    @staticmethod
    def _organizer(tournament, team_id):
        if tournament['organizerTeamId'] != team_id:
            raise TournamentError('Chỉ đội tạo giải có quyền thực hiện thao tác này.', 403)

    def create(self, name, organizer, game_id, version, format, seed):
        if not name.strip():
            raise TournamentError('Tên giải không được để trống.', 422)
        tournament = {'tournamentId': uuid4().hex, 'name': name.strip(), 'organizerTeamId': organizer['teamId'],
                      'organizerName': organizer['name'], 'gameId': game_id, 'gameVersion': version,
                      'format': format, 'seed': seed, 'status': 'OPEN', 'createdAt': now(),
                      'maxTeams': MAX_TEAMS, 'entries': [], 'fixtures': [], 'lockedAt': None,
                      'rankingRules': ['MATCH_POINTS', 'GAME_DIFFERENCE', 'GAME_WINS', 'HEAD_TO_HEAD_POINTS'],
                      'pointsPerWin': 3}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM tournaments').fetchone()[0] >= 100:
                raise TournamentError('Đã đạt giới hạn 100 giải trên server này.', 429)
            self._save(db, tournament)
        return tournament

    def get(self, tournament_id):
        with self.store.connect() as db:
            return self._load(db, tournament_id)

    def list(self, *, status=None):
        with self.store.connect() as db:
            rows = db.execute('SELECT payload FROM tournaments' +
                              (" WHERE json_extract(payload, '$.status')=?" if status else '') +
                              ' ORDER BY rowid DESC', (status,) if status else ()).fetchall()
        return [json.loads(row[0]) for row in rows]

    def register(self, tournament_id, team, bot_id, resolve):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            tournament = self._load(db, tournament_id)
            if tournament['status'] != 'OPEN':
                raise TournamentError('Danh sách đã khóa; không thể thay phiên bản bot trong giải.')
            entry = resolve(tournament, team['teamId'], bot_id)
            previous = next((i for i, row in enumerate(tournament['entries']) if row['teamId'] == team['teamId']), None)
            if previous is None:
                if len(tournament['entries']) >= MAX_TEAMS:
                    raise TournamentError(f'Giải tối đa {MAX_TEAMS} đội.')
                tournament['entries'].append(entry)
            else:
                tournament['entries'][previous] = entry
            self._save(db, tournament)
        return tournament

    def withdraw(self, tournament_id, team_id):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            tournament = self._load(db, tournament_id)
            if tournament['status'] != 'OPEN':
                raise TournamentError('Danh sách đã khóa; không thể rút đội.')
            tournament['entries'] = [e for e in tournament['entries'] if e['teamId'] != team_id]
            self._save(db, tournament)
        return tournament

    def start(self, tournament_id, team_id, resolve):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            tournament = self._load(db, tournament_id)
            self._organizer(tournament, team_id)
            if tournament['status'] != 'OPEN':
                raise TournamentError('Giải đã bắt đầu; lịch đấu và phiên bản bot đã khóa.')
            if len(tournament['entries']) < 2:
                raise TournamentError('Cần ít nhất 2 đội với bot đã qua kiểm tra.')
            # Recheck the complete field inside the transaction before freezing it.
            entries = [resolve(tournament, e['teamId'], e['botId']) for e in tournament['entries']]
            tournament.update(entries=entries, status='RUNNING', lockedAt=now())
            lookup = {e['teamId']: e for e in entries}
            for number, (round_number, left, right) in enumerate(round_robin(list(lookup)), 1):
                fixture_id, match_id = uuid4().hex, uuid4().hex
                # JS clients can represent every generated fixture seed exactly.
                seed = int.from_bytes(sha256(f"{tournament['seed']}:fixture:{number}".encode()).digest()[:8], 'big') & (2**53-1)
                fixture = {'fixtureId': fixture_id, 'number': number, 'round': round_number,
                           'teamA': left, 'teamB': right, 'matchId': match_id,
                           'seed': seed, 'status': 'SCHEDULED', 'attempts': []}
                tournament['fixtures'].append(fixture)
                self._save_match(db, self._new_match(tournament, fixture, lookup))
            self._save(db, tournament)
        return tournament

    @staticmethod
    def _new_match(tournament, fixture, lookup=None):
        lookup = lookup or {e['teamId']: e for e in tournament['entries']}
        left, right = lookup[fixture['teamA']], lookup[fixture['teamB']]
        return {'matchId': fixture['matchId'], 'tournamentId': tournament['tournamentId'],
                'fixtureId': fixture['fixtureId'], 'gameId': tournament['gameId'],
                'gameVersion': tournament['gameVersion'], 'format': tournament['format'],
                'seed': fixture['seed'], 'botA': left['botId'], 'botB': right['botId'],
                'botLabels': {left['botId']: left['botLabel'], right['botId']: right['botLabel']},
                'createdAt': now(), 'status': 'SCHEDULED', 'scores': {'botA': 0, 'botB': 0}, 'gameResults': []}

    def claim_next(self):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.store.active_count(db) >= MATCH_QUEUE_LIMIT:
                return None
            rows = db.execute("SELECT payload FROM tournaments WHERE json_extract(payload, '$.status')='RUNNING' ORDER BY rowid").fetchall()
            for row in rows:
                tournament = json.loads(row[0])
                if tournament['status'] != 'RUNNING':
                    continue
                # Never dispatch two fixtures of the same competition simultaneously.
                if any(f['status'] in ('QUEUED', 'RUNNING') for f in tournament['fixtures']):
                    continue
                fixture = next((f for f in tournament['fixtures'] if f['status'] == 'SCHEDULED'), None)
                if not fixture:
                    continue
                saved = db.execute('SELECT payload FROM matches WHERE id=?', (fixture['matchId'],)).fetchone()
                match = json.loads(saved[0]) if saved else self._new_match(tournament, fixture)
                match['status'] = fixture['status'] = 'QUEUED'
                self._save_match(db, match)
                self._save(db, tournament)
                return match
        return None

    def record_result(self, match):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            tournament = self._load(db, match['tournamentId'])
            fixture = next(f for f in tournament['fixtures'] if f['fixtureId'] == match['fixtureId'])
            if fixture['matchId'] != match['matchId'] or fixture['status'] == 'COMPLETED':
                return  # A historical attempt cannot overwrite its replacement.
            fixture['status'] = match['status']
            if match['status'] == 'COMPLETED':
                fixture.update(scores=match['scores'], winnerTeamId=fixture['teamA'] if match['winnerSlot'] == 'botA' else fixture['teamB'])
                fixture.pop('error', None)
                if all(f['status'] == 'COMPLETED' for f in tournament['fixtures']):
                    tournament.update(status='COMPLETED', finishedAt=now())
                    tournament.pop('error', None)
            elif match['status'] in ('FAILED', 'INTERRUPTED'):
                fixture['error'] = match.get('error', 'Trận bị gián đoạn.')
                tournament.update(status='PAUSED', error='Có trận lỗi hoặc bị gián đoạn. Chủ giải cần tiếp tục để chạy lại trận này.')
            self._save(db, tournament)

    def recover(self):
        # Store.recover first restores completed replay or marks an interrupted process.
        for tournament in self.list(status='RUNNING'):
            for fixture in tournament['fixtures']:
                if fixture['status'] in ('QUEUED', 'RUNNING'):
                    match = self.store.get(fixture['matchId'])
                    self.record_result(match)

    def resume(self, tournament_id, team_id, resolve):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            tournament = self._load(db, tournament_id)
            self._organizer(tournament, team_id)
            if tournament['status'] != 'PAUSED':
                raise TournamentError('Chỉ giải đang tạm dừng mới có thể tiếp tục.')
            for entry in tournament['entries']:
                actual = resolve(tournament, entry['teamId'], entry['botId'])
                if any(actual[key] != entry[key] for key in ('botVersion', 'artifactSha256', 'sourceSha256')):
                    raise TournamentError('Bot không khớp bản đã khóa; cần khôi phục đúng file trước khi tiếp tục.')
            for fixture in tournament['fixtures']:
                if fixture['status'] in ('FAILED', 'INTERRUPTED'):
                    fixture['attempts'].append({'matchId': fixture['matchId'], 'status': fixture['status'], 'error': fixture.get('error')})
                    fixture.update(matchId=uuid4().hex, status='SCHEDULED')
                    fixture.pop('error', None)
                    self._save_match(db, self._new_match(tournament, fixture))
            tournament.update(status='RUNNING')
            tournament.pop('error', None)
            self._save(db, tournament)
        return tournament

    def standings(self, tournament_id, *, tournament=None):
        tournament = tournament if tournament is not None else self.get(tournament_id)
        rows = {e['teamId']: {**e, 'played': 0, 'wins': 0, 'losses': 0, 'points': 0,
                              'gameWins': 0, 'gameLosses': 0, 'gameDifference': 0, 'headToHeadPoints': 0}
                for e in tournament['entries']}
        completed = [f for f in tournament['fixtures'] if f['status'] == 'COMPLETED']
        for fixture in completed:
            for own, slot, opponent in ((fixture['teamA'], 'botA', 'botB'), (fixture['teamB'], 'botB', 'botA')):
                row = rows[own]
                won = fixture['winnerTeamId'] == own
                row['played'] += 1
                row['wins'] += int(won)
                row['losses'] += int(not won)
                row['points'] += 3 * int(won)
                row['gameWins'] += fixture['scores'][slot]
                row['gameLosses'] += fixture['scores'][opponent]
                row['gameDifference'] = row['gameWins'] - row['gameLosses']
        def primary(row):
            return row['points'], row['gameDifference'], row['gameWins']
        for fixture in completed:
            left, right = rows[fixture['teamA']], rows[fixture['teamB']]
            if primary(left) == primary(right):
                rows[fixture['winnerTeamId']]['headToHeadPoints'] += 3
        def score(row):
            return (*primary(row), row['headToHeadPoints'])
        ordered = sorted(rows.values(), key=lambda row: (tuple(-n for n in score(row)), row['teamName'].casefold(), row['teamId']))
        previous, rank = None, 0
        for index, row in enumerate(ordered, 1):
            if score(row) != previous:
                rank = index
            row['rank'] = rank
            previous = score(row)
        return {'tournamentId': tournament_id, 'status': tournament['status'], 'rows': ordered,
                'completedMatches': len(completed), 'totalMatches': len(tournament['fixtures']),
                'rankingRules': tournament['rankingRules']}
