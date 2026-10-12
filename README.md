# OTT v2 Arena

Demo local hoàn chỉnh: chọn hai bot Python, chạy BO1/BO3, xem bàn cờ 9×9 đang đấu và phát lại
snapshot từng nước; lưu lịch sử/thống kê qua restart. Python 3.11+, FastAPI/Uvicorn,
Jinja2 + HTML/CSS/JS thuần, SQLite stdlib. Không cần Node, Docker hay dịch vụ ngoài.
Có giải vòng tròn cho bot đội nộp: khóa phiên bản, lịch đấu tự động, bảng xếp hạng
và xem bàn cờ/replay từng trận.

## Cài và chạy

Chạy từ thư mục **OTTv2** (thư mục chứa README này, không phải thư mục starter).

Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m arena
```

Windows PowerShell:
```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m arena
```

Windows CMD có thể dùng cùng hai lệnh `.venv\Scripts\python.exe`.
Khởi động các lần sau chỉ cần **`python -m arena`** khi venv được kích hoạt;
hoặc `.venv/bin/python -m arena` trên Linux/macOS. Windows dùng lệnh ở trên.

Truy cập **http://127.0.0.1:8000**. Swagger: http://127.0.0.1:8000/docs.
Server mặc định chỉ bind loopback. Dừng bằng Ctrl+C.
Nếu muốn hot reload khi phát triển:
```bash
python -m uvicorn arena.web.app:app --reload --host 127.0.0.1 --port 8000
```
Chỉ chạy một server process (không dùng `--workers`); worker nội bộ xử lý từng trận
tuần tự. Khởi tạo tự động SQLite/thư mục replay, không cần migrate/seed database.
Seed UI mặc định 42; Random, Capture Greedy, Goal Rush dùng để đấu thử.
Các đội có thể tự nộp source Python qua web; bài đạt kiểm tra sandbox xuất hiện
trong danh sách bot. Hướng dẫn đầy đủ: [Bài nộp và live board](docs/SUBMISSIONS_AND_LIVE.md).

Dependency đã kiểm thử được pin đầy đủ trong `requirements-lock.txt`; có thể cài
bằng `python -m pip install -r requirements-lock.txt` để tái lập môi trường.

## Sử dụng

1. Chọn hai bot, BO1 hoặc BO3 và seed. Bấm **Bắt đầu trận**.
2. Bot chạy trong nền; UI poll snapshot 250 ms và cập nhật bàn cờ trong trận.
   Mặc định nhịp 120 ms/nước để quan sát; kết thúc mở điều khiển replay đầy đủ.
3. Dùng phát/tạm dừng, trước/sau, thanh tua và tốc độ 0.5×/1×/2×. BO3 chọn game
   ở menu; mỗi game có side mapping riêng. Điểm giữa bàn theo Bot #1/#2, màu quân
   theo bên A/B. Chọn nước trong nhật ký để tua trực tiếp.
4. Xem kết quả, lý do thắng/lỗi bot, tiêu chí phân xử, tải replay JSON; mở trận cũ
   bằng nút **Xem** trong lịch sử. Lịch sử hiển thị tối đa 50 trận gần nhất mặc định,
   thống kê tính toàn bộ trận hoàn tất.

**Bài nộp:** tạo đội, lưu mã truy cập, tải template, tự viết chiến thuật rồi nộp một
file .py UTF-8 (256 KiB). Server tự kiểm tra cú pháp và JSONL/nước hợp lệ trong
sandbox; READY mới được thi đấu. Mỗi lần nộp tạo phiên bản mới gồm source/SDK/hash.
Đội chỉ đọc được source của mình. Trận chọn bài nộp cần mã đội sở hữu ít nhất một bot.

**Giải đấu:** mở **Tạo giải mới**, chọn bộ luật và BO3/BO1, chia sẻ liên kết cho
các đội đăng ký một bot READY. Chủ giải bấm **Khóa bot & bắt đầu giải** để khóa
ID phiên bản/hash source + SDK và tạo lịch vòng tròn (2–16 đội). Lịch tự chạy,
thắng trận được 3 điểm; bảng xếp hạng cập nhật sau mỗi trận hoàn tất. Bấm
**Xem bàn cờ** / **Xem replay** trong lịch. Trận lỗi làm giải tạm dừng; chủ giải
có thể tiếp tục với đúng bản bot đã khóa. [Hướng dẫn giải đấu](docs/TOURNAMENTS.md).

**Runtime:** bot đội nộp luôn dùng Linux Bubblewrap + seccomp: cách ly namespace,
filesystem chỉ đọc, môi trường sạch, chặn network/fork/exec, giới hạn RAM và file.
Runtime lỗi sẽ chặn bài nộp, không chuyển sang subprocess thường. Cần Linux,
`bubblewrap`, `libseccomp2`, `/usr/bin/python3` 3.11+ và user namespaces hoạt động.
Windows/macOS vẫn chạy bot mẫu, nhưng cần worker Linux để chạy mã của đội.
Bot mẫu trong repo dùng subprocess cũ và phải là mã đáng tin cậy. 500 ms/quyết định,
64 KiB/dòng stdout, 1 MiB stderr/game; replay giữ 8 KiB log/bot.
Sandbox chia sẻ kernel host, chưa được kiểm toán bảo mật độc lập; mở online cần
HTTPS, host Linux được cập nhật và cấu hình proxy theo tài liệu triển khai.

## Luật, determinism và plugin

**Mặc định trận mới: 1.1.0.** Chọn 1.0.0 trong form để dùng luật gốc/bot cũ.
Bản 1.1 thêm thắng khi hết toàn bộ quân, phân xử sau 50 lượt không capture và
xử thua sau 15 lượt riêng không tạo tiến độ. Giữ thắng khi xóa một loại theo lựa
chọn của người dùng. Chi tiết và thứ tự ưu tiên: [Luật 1.1](docs/RULES_1_1.md).
Các đoạn dưới mô tả luật gốc 1.0 và các phần dùng chung.

Mỗi bên 9 quân (3 D, 3 L, 3 K), A theo bố trí đặc tả, B xoay 180°. a1 ở dưới trái,
i9 ở trên phải. A đi trước. Mỗi lượt một quân đi một ô trong 8 hướng. D ăn K,
K ăn L, L ăn D; cùng loại hoặc quân đồng đội chặn ô.
A vào i9 / B vào a1 thắng. Sau capture, xóa hết một loại địch cũng thắng.
Kiểm tra đích → xóa loại → đổi lượt/thế bí → phân xử. Đứng sẵn tại góc lúc khởi tạo
không tạo chiến thắng. Không có pass/hòa.

Lặp cùng `(board, side_to_move)` 3 lần hoặc đạt 300 plies: so số quân sống,
số quân cách đích Chebyshev ≤2, khoảng cách nhỏ nhất, tổng khoảng cách.
Bằng tất cả: SHA256 UTF-8 của `str(seed) + gameInstanceId + trigger` không dấu
phân cách, bit cuối 0=A/1=B. `trigger` là `THREEFOLD_REPETITION` hoặc `PLY_LIMIT`.
Replay ghi đầy đủ metrics, criterion và nếu cần hashInput/hash/bit. ID ngẫu nhiên
của trận được ghi để tái hiện; cùng seed nhưng khác ID có thể khác kết quả phân xử
hash. Tests dùng ID cố định để kiểm tra tái lập toàn bộ chuỗi snapshot.

BO3: game 1 Bot #1=A, game 2 đảo bên. Game 3 nếu cần: bit cuối
SHA256(`str(seed) + ":side:3"`), 0 giữ #1=A, 1 đảo bên. Mỗi game dùng seed của
match, PRNG reset; bot nào đạt 2 game thắng kết thúc match. Chọn cùng bot hai bên
vẫn hợp lệ, hai slot/process độc lập; thống kê tính cả hai lần tham gia.

`arena/core/` không import OTT v2 và không kiểm tra gameId để xử lý luật.
`GamePlugin` API 1.0 dành cho hai bên A/B đi luân phiên, trả một winner duy nhất.
Create nhận config chứa `gameInstanceId`; step trả `StepResult(state, events)`.
`status` trả turn/ply/winner/reason/details, `serialize_state` xuất snapshot JSON,
`render_metadata` xuất dữ liệu renderer. Forfeit runtime nằm trong runner.

Thêm game: tạo package trong `arena/games/`, triển khai contract, thêm manifest
`implementation: "python.module:PluginClass"`, version, schemas và renderer JS.
Bootstrap tự khám phá manifests, registry/API/runner/storage dùng chung. Thêm bot
với `gameIds` tương thích. UI hiện phục vụ OTT v2; game mới cần form/renderer riêng
hoặc mở rộng selector game. Test `DummyGamePlugin` chạy qua cùng MatchRunner với
hai process JSONL thật mà không sửa core. Hướng dẫn bot: [bots/README.md](bots/README.md).

## API

- `GET /api/games`, `GET /api/bots`
- `POST /api/matches` → HTTP 202 `{matchId,status}`
- `GET /api/matches/{id}` → trạng thái, score slot, winnerBot/winnerSlot, gameResults
- `GET /api/matches/{id}/replay` → initialState, frames (action/events/state/stateHash),
  seed, sideMapping, gameVersion, botNames/digests/logs, kết quả từng game
- `GET /api/matches?limit=50` (giới hạn 200), `GET /api/stats`
- `POST /api/tournaments`, `GET /api/tournaments`, `GET /api/tournaments/{id}`
- `POST /api/tournaments/{id}/entries` → đăng ký `{botId}`; `/withdraw` → rút đội
- `POST /api/tournaments/{id}/start`, `/resume` → chủ giải bắt đầu/tiếp tục
- `GET /api/tournaments/{id}/standings` → bảng xếp hạng; chi tiết giải cũng trả
  standings từ cùng snapshot với lịch đấu. Các POST giải cần `X-Team-Key`.

Ví dụ payload POST:
```json
{"gameId":"ottv2","botA":"random","botB":"goal_rush","format":"BO3","seed":42}
```
`gameVersion` tùy chọn; mặc định `1.1.0`, hỗ trợ chọn `1.0.0`. Chọn bot lạ, đường dẫn, game/version lạ,
format sai, seed sai hoặc field dư trả 422. Hàng đợi tối đa 8 trận trả 429 khi đầy.
Replay chưa có game hoàn tất trả 409, ID không tồn tại trả 404.

## Kiểm thử

```bash
python -m pytest -q
python scripts/smoke_local.py
python scripts/smoke_submissions.py
python scripts/smoke_tournaments.py
```
Smoke script yêu cầu server đang chạy và tạo một trận BO3 thật qua HTTP.
Pytest gồm luật, playout invariants, mọi tiêu chí phân xử/hash,
JSONL/process lifetime/cleanup/lỗi, ba cặp bot/determinism, BO3/Dummy plugin,
API/validation/replay/history/stats và persistence/restart.
Test không đòi thư viện pytest-asyncio, không dùng internet.
Kết quả bộ test hiện tại: **126 test Python pass**, thêm **4 test JavaScript pass**;
một cảnh báo deprecation của Starlette TestClient
(httpx) không ảnh hưởng runtime. Báo cáo HTTP/browser/restart: [docs/VALIDATION.md](docs/VALIDATION.md).

Kiểm tra polling và benchmark (Node chỉ dùng để chạy test JS, không cần cho ứng dụng):
```bash
node tests/poller.test.mjs
python scripts/benchmark_core.py
```
Benchmark tạo SQLite/replay mẫu trong thư mục tạm và không sửa dữ liệu Arena.
Chi tiết sửa lỗi, số đo và giới hạn: [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md).

## Cấu trúc

```text
arena/
  __main__.py, bootstrap.py
  core/       plugin, registry, bot_runner, match_runner, storage, submissions, sandbox, tournaments
  games/ottv2/ state, engine, manifest, schemas/, test-data/
  web/        app.py, templates/, static/ (renderers/ottv2.js)
bots/         manifest, bot_sdk, 3 bot mẫu, starter_bot, README
tests/       engine, runner, API, submissions, sandbox, tournaments, storage, review, polling JS
scripts/      smoke_local.py, smoke_submissions.py, smoke_tournaments.py, benchmark_core.py
data/        arena.sqlite3, replays/*.json, submissions/ (tự tạo, gitignored)
docs/         IMPLEMENTATION_SCOPE.md
codex_ottv2_starter/  PROMPT_CODEX.md và PDF gốc được giữ nguyên
requirements.txt
```

## Lưu trữ và giới hạn

SQLite lưu metadata; replay JSON ghi atomic (tmp + replace), hash mỗi snapshot.
SQLite dùng WAL; khi sao lưu, dùng SQLite backup hoặc dừng server trước khi chép
thư mục data. Kết nối được đóng sau mỗi transaction. Hàng đợi dùng chung giới hạn
8 trận giữa đấu thử và giải; API live dùng cache tối đa 32 snapshot trận, mỗi
snapshot giữ 20 frame gần nhất và tự đọc replay khi cache không có dữ liệu.
Kết quả đã hoàn tất còn sau restart. Trận QUEUED/RUNNING bị dừng sẽ được đánh dấu
INTERRUPTED nếu chưa có replay hoàn tất; không tự chạy lại bot. Khi server dừng
bình thường có thể chờ worker kết thúc game/trận hiện tại.
Có thể đặt `ARENA_DATA_DIR` sang thư mục khác để tách dữ liệu test/demo.

Có mã truy cập đội và nộp một file .py, sandbox Linux và bàn cờ trong trận.
Chưa có tài khoản email/password, ZIP/pip, playoff/loại trực tiếp, Elo, Redis,
Kubernetes, S3 hoặc realtime socket. Chưa triển khai lên Internet vì chưa có VPS/domain. Bot mẫu chỉ dùng heuristic,
chưa đo cân bằng bằng hàng nghìn trận. Nâng cấp luật phải dùng gameVersion mới;
không thay luật khi đang chạy trận. Replay là dữ liệu thực đã lưu, không tính lại
winner hay nước đi trong trình duyệt.

Phiên bản 1.1 bổ sung nộp code của đội và live board. Báo cáo kiểm tra: [docs/VALIDATION_SUBMISSIONS.md](docs/VALIDATION_SUBMISSIONS.md).

Bản luật 1.1 và kết quả kiểm tra: [docs/VALIDATION_RULES_1_1.md](docs/VALIDATION_RULES_1_1.md).

Giải đấu vòng tròn và kết quả kiểm tra: [docs/TOURNAMENTS.md](docs/TOURNAMENTS.md),
[docs/VALIDATION_TOURNAMENTS.md](docs/VALIDATION_TOURNAMENTS.md).
