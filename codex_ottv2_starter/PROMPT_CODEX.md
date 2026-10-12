# PROMPT CHO CODEX — TRIỂN KHAI OTT v2 ARENA LOCAL DEMO

Bạn là senior full-stack engineer kiêm game-engine engineer. Hãy **thực sự tạo mã nguồn có thể chạy được**, không chỉ viết một bản đề xuất. Xây dựng ứng dụng local tên **OTT v2 Arena** để hai bot Python đấu với nhau trên trò Đấm–Lá–Kéo 9×9 theo tài liệu kiến trúc đính kèm.

## 0. Tài liệu đầu vào & nguyên tắc ưu tiên

- Đọc toàn bộ `docs/OTT_v2_Thiet_ke_demo_he_thong_thi_dau_AI.pdf` trước khi viết code (có thể dùng `pdftotext`, `pypdf` hoặc công cụ sẵn có). Đây là nguồn tham khảo đặc tả OTT v2 1.0 và hợp đồng Game Plugin.
- Nếu PDF chưa có trong workspace, nêu rõ điều đó trong phần tổng kết và triển khai theo **các luật cụ thể ghi trong prompt này**, không dừng công việc để hỏi.
- Khi có xung đột, ưu tiên: **(1) phạm vi MVP đơn giản trong prompt này, (2) các luật bắt buộc bên dưới, (3) phần còn lại của PDF**.
- Không tự ý thêm luật gameplay không được yêu cầu. Để thay game trong tương lai, giữ ranh giới giữa core thi đấu và plugin OTT v2.
- Không hỏi lại để xin duyệt từng bước. Tự chọn cách triển khai gọn, test, sửa lỗi cho đến khi demo chạy được.

## 1. Mục tiêu sản phẩm và phạm vi

Mục tiêu: trên máy local, người dùng mở trình duyệt, chọn hai bot có sẵn, bấm **Bắt đầu trận**, xem bàn cờ 9×9 và diễn biến bot đánh bot, xem kết quả và tua lại replay. Có thể tổ chức **BO1** hoặc **BO3**, thống kê thắng/thua đơn giản và thay hoặc thêm bot Python khác trong thư mục `bots/`.

**Bắt buộc (MVP):**
1. Engine OTT v2 đúng luật, độc lập UI, có unit tests.
2. Hợp đồng `GamePlugin` dùng chung, registry plugin và `MatchRunner` không biết các loại quân Đấm/Lá/Kéo.
3. 3 bot mẫu chạy được: `random`, `capture_greedy`, `goal_rush`.
4. Bot được chạy từ **script Python local** bằng subprocess, giao tiếp JSONL qua stdin/stdout; thời gian tối đa cho mỗi quyết định: 500 ms, lỗi hoặc nước đi sai xử thua.
5. Web UI responsive bằng tiếng Việt: chọn bot/format/seed, bàn cờ, nút bắt đầu, trạng thái/kết quả, lượt đi, lịch sử nước đi, replay play/pause/next/previous/thanh tua/tốc độ.
6. REST API tối thiểu để tạo trận, đọc trạng thái, kết quả, replay, danh sách bot, lịch sử và thống kê đơn giản.
7. Một lệnh chạy local dễ hiểu, README hướng dẫn Windows/Linux/macOS, `requirements.txt`, dữ liệu mặc định, test tự động.

**Lược bỏ hẳn ở bản demo:** đăng nhập/đăng ký, đội thi online, tải file từ internet, thanh toán, Redis/Celery, Kubernetes, phân tán worker, S3, Elo chính thức, upload mã nguồn public, giải nhiều vòng/Swiss, real-time socket, Docker bắt buộc, đa ngôn ngữ bot, cơ chế game mới phức tạp. Không triển khai các phần này chỉ vì chúng có trong PDF.

## 2. Stack kỹ thuật tối giản

- Python **3.11+**.
- FastAPI + Uvicorn cho backend, Jinja2/HTML + CSS + JavaScript thuần cho frontend; **không cần Node/npm build**.
- SQLite bằng Python stdlib `sqlite3` để lưu metadata trận/kết quả; replay JSON ở `data/replays/`. Nếu đơn giản hơn có thể lưu tất cả bằng JSON file, nhưng phải duy trì được lịch sử sau khi restart.
- Pytest cho kiểm thử.
- Monolith module hóa; chỉ một web server local và các bot subprocess riêng. Không cần microservices.
- Giữ dependencies ít nhất có thể, giao diện sạch và dễ dùng.

## 3. Luật game OTT v2 1.0 — phải implement chính xác

### 3.1 Bàn cờ và quân
- Bàn vuông 9×9; tọa độ cột `a..i`, hàng `1..9`; `a1` ở **góc dưới trái** khi hiển thị, `i9` ở góc trên phải.
- Hai bên A và B; mỗi bên **9 quân gồm 3 Đấm (D), 3 Lá (L), 3 Kéo (K)**. Một ô tối đa một quân.
- Bên A bắt đầu: `a1:D, c1:L, e1:K, g1:D, i1:L, b2:K, d2:D, f2:L, h2:K`.
- Bên B bố trí bằng cách **xoay 180° các tọa độ A**, giữ nguyên loại quân. Ban đầu không có ô trùng quân.
- A là bên đi trước. Khi chạy BO3, đổi bot đóng vai A/B ở game thứ hai để giảm lợi thế đi trước; game thứ ba xác định bên bằng seed một cách xác định.

### 3.2 Di chuyển và ăn quân
- Mỗi lượt đúng **một** quân của bên đang đi phải di chuyển đúng **một ô** theo một trong 8 hướng (ngang/dọc/chéo): `max(abs(dx),abs(dy)) == 1`.
- Không đi ra ngoài bàn, không đi vào ô có quân cùng đội, không đứng yên hoặc bỏ lượt.
- Nếu ô đích có quân địch: **D ăn K, K ăn L, L ăn D**. Khi ăn quân, quân tấn công tiến vào ô vừa ăn.
- Hai quân địch **cùng loại không ăn nhau, chỉ chặn nhau**. Không được đi vào ô quân địch khắc chế mình. Không được chồng quân hoặc nhảy xuyên quân (đi một ô nên không cần pathfinding cho hành động đơn).

### 3.3 Thắng/thua — TUYỆT ĐỐI KHÔNG CÓ HÒA
- **Đến đích:** A vừa thực hiện nước hợp lệ vào `i9` thì A thắng; B vừa thực hiện nước hợp lệ vào `a1` thì B thắng. Việc quân đứng sẵn ở `a1`/`i9` khi khởi tạo **không** tạo chiến thắng.
- **Xóa một loại quân:** sau một nước ăn hợp lệ, nếu đối phương còn **0 quân** của bất kỳ loại D/L/K nào thì bên vừa đi thắng ngay.
- Thứ tự kiểm tra sau mỗi move: `GOAL_REACHED`, `TYPE_ELIMINATED`, sau đó đổi lượt và xét hết nước hợp lệ.
- Đến lượt một bên nhưng bên đó không có nước hợp lệ: bên đó thua, lý do `NO_LEGAL_MOVES`.
- Bot timeout/crash/in JSON lỗi/action không hợp lệ: bot đó thua (`BOT_FORFEIT`), phải có log lý do rõ ràng.
- Nếu cùng trạng thái `(board, side_to_move)` xuất hiện **3 lần**, hoặc sau **300 plies** vẫn chưa thắng theo luật gốc, xử thắng bằng adjudication như mục dưới. Không bao giờ trả về DRAW.
- So sánh adjudication lần lượt: (1) số quân còn sống **nhiều hơn thắng**; (2) số quân có khoảng cách Chebyshev tới đích đối phương `<= 2` **nhiều hơn thắng**; (3) khoảng cách nhỏ nhất từ bất kỳ quân nào tới đích **nhỏ hơn thắng**; (4) tổng khoảng cách các quân tới đích **nhỏ hơn thắng**. Nếu vẫn bằng nhau, dùng bit xác định từ `SHA256(seed + game_id + reason)` để chọn duy nhất A hoặc B. Ghi chi tiết tiêu chí trong replay. Thiết kế hàm adjudicate có test cho mọi trường hợp.
- Không thêm quân đặc biệt, ô chướng ngại, skill hoặc điểm thưởng ở MVP.

## 4. Kiến trúc phần mềm bắt buộc: core độc lập game

Có ít nhất các vùng module rõ ràng:

- `arena/core/plugin.py`: `GamePlugin` protocol/ABC dùng chung (create, observe, legal_actions, step, status, serialize_state / render_metadata).
- `arena/core/registry.py`: đăng ký plugin từ manifest, ánh xạ `game_id + version` sang implementation.
- `arena/core/match_runner.py`: điều phối các lượt, gọi bot, nhận kết quả, lưu replay. **Không import** các file luật từ `arena/games/ottv2/` và không viết `if game_id == 'ottv2'` để xử lý luật.
- `arena/core/bot_runner.py`: quản lý bot subprocess và JSONL, timeout/cleanup/error codes.
- `arena/games/ottv2/`: state, engine/rules, manifest, observation/action schema, test data và (nếu cần) serialize riêng.
- `arena/web/`: FastAPI routes, HTML templates và static frontend; renderer bàn cờ OTT v2 đặt tách riêng, còn API/runner không phụ thuộc renderer.
- `bots/`: 3 bot script độc lập, cùng dùng giao thức chuẩn.
- `tests/`: unit, integration, protocol và regression.

**Plugin contract:** có thể đăng ký một `DummyGamePlugin` cực nhỏ trong test và chạy nó qua chính `MatchRunner` mà không sửa core. Đừng triển khai game thứ hai hoàn chỉnh; test này dùng để chứng minh khả năng thay game.

## 5. Giao thức bot local

Mỗi bot là một Python process tồn tại **suốt một game**, nhận mỗi lượt một JSON trên một dòng stdin, trả một JSON trên một dòng stdout; stderr dành cho logs. Dùng Python interpreter từ `sys.executable`, chỉ khởi chạy các script được hệ thống đăng ký trong thư mục `bots/` (không chấp nhận đường dẫn tùy ý từ API).

Envelope quan sát mẫu:

```json
{
  "type": "observation", "protocolVersion": "1.0",
  "requestId": "game-1:turn-18:A", "gameId": "ottv2",
  "gameVersion": "1.0.0", "playerId": "A", "turnId": 18,
  "deadlineMs": 500,
  "observation": {
    "side": "A", "target": "i9", "ply": 18,
    "pieces": [{"at":"d4","side":"A","kind":"D"}],
    "legalActions": [{"type":"MOVE","from":"d4","to":"e5"}]
  }
}
```

Action đáp ứng:

```json
{
  "type": "action", "protocolVersion": "1.0",
  "requestId": "game-1:turn-18:A", "turnId": 18,
  "action": {"type": "MOVE", "from": "d4", "to": "e5"}
}
```

- Match `requestId`/`turnId`; giới hạn kích thước mỗi dòng, báo lỗi JSON hoặc action sai.
- `legalActions` được đưa vào observation cho bot mẫu để giản lược demo (đây là trường hợp lệ vì schema observation là của OTT v2).
- Bot `random` chọn nước hợp lệ bằng PRNG với seed; `capture_greedy` ưu tiên ăn quân, tiếp đó gần đích; `goal_rush` ưu tiên khoảng cách đến đích và tránh nguy cơ bị ăn. Bot không được đọc engine internals.
- Có template `bots/starter_bot.py` cùng README hướng dẫn viết bot mới.
- **An toàn:** subprocess local thuần **không phải sandbox bảo mật**; ghi cảnh báo ngay trong README/UI. Không hỗ trợ upload/chạy mã nguồn không tin cậy từ Internet; app chỉ bind `127.0.0.1`. Cố gắng hạn chế timeout/stdout/stderr, xử lý process group cleanup. Không quảng cáo đây là môi trường an toàn để chạy bot người lạ.

## 6. REST API tối thiểu và UI

API gợi ý (có thể tinh chỉnh nhưng phải ổn định, có Pydantic validation):
- `GET /api/games` — danh sách game được đăng ký.
- `GET /api/bots` — danh sách bot local và mô tả chiến thuật.
- `POST /api/matches` — `{ "gameId":"ottv2", "botA":"random", "botB":"goal_rush", "format":"BO1", "seed":42 }`; tạo và chạy match nền trong chính local process, trả `matchId`. Không chặn UI quá lâu.
- `GET /api/matches/{matchId}` — trạng thái, scores, người thắng, lý do.
- `GET /api/matches/{matchId}/replay` — initial state, snapshots/events từng ply, game results; với BO3 gồm ba game tối đa.
- `GET /api/matches` — lịch sử gần đây.
- `GET /api/stats` — số trận thắng/thua theo bot (không nhất thiết Elo).

UI một trang hoặc tối đa hai trang:
- Tiêu đề OTT v2 Arena, form chọn bot A/B, BO1/BO3, seed (mặc định 42), nút **Bắt đầu**.
- Bàn 9×9 nhìn rõ tọa độ a–i và 1–9; các quân hiển thị chữ `D`, `L`, `K` + biểu tượng/màu team; đánh dấu `a1` và `i9`.
- Nhãn lượt, bot đang đi, quân vừa di chuyển, quân vừa bị ăn, lý do kết thúc, kết quả BO3.
- Replay phát hoạt cảnh **từ dữ liệu engine đã lưu** (không tự tính lại luật trong frontend), cho tua next/prev, autoplay và tốc độ 0.5x/1x/2x.
- Bảng lịch sử trận và bảng thống kê đơn giản.
- Hiển thị thông báo lỗi rõ ràng nếu bot bị forfeit; bố cục tốt trên desktop và dùng được trên mobile.
- Không bắt buộc realtime streaming: engine có thể chạy nhanh rồi UI phát replay theo lượt sau khi trận kết thúc. Giải thích hành vi này trong README.

## 7. Determinism, replay, BO3, dữ liệu

- Mỗi game lưu `seed`, `gameVersion`, `bot names`, `side mapping`, `initialState`, các actions, các state snapshots hoặc event log đủ để replay chính xác, `winner`, `reason`, `plies`.
- Cùng các bot deterministic, seed, side mapping và game_id được cố định => chuỗi trạng thái không đổi. Tránh phụ thuộc thời gian thực để tính thắng hoặc nước đi.
- BO3: game 1 bot đầu vào #1 là A, game 2 đảo side, game 3 (nếu cần) gán side bằng seed xác định; bot nào đạt 2 game thắng thì thắng match.
- Với match/game ID ngẫu nhiên ở production demo, đảm bảo adjudication deterministic theo ID đã ghi; trong tests có thể cố định ID.
- SQLite/JSON persistence phải không mất kết quả đã hoàn tất khi restart server. Replay JSON có thể được trả qua API.
- Đừng dùng logic UI để tính winner; winner phải do plugin/runner quyết định.

## 8. Kiểm thử và Definition of Done

Tạo `pytest` cho 12 case sau:
1. D di chuyển d4 -> e5 khi trống.
2. D ăn K ở e5.
3. D không thể ăn L.
4. D không thể ăn D đối phương.
5. Không đi vào quân cùng bên.
6. Không đi hơn 1 ô/ngoài bản đồ.
7. A vào i9 hoặc B vào a1 thắng.
8. Ăn quân cuối cùng của một loại đối phương thắng.
9. Đến lượt không còn nước hợp lệ => thua.
10. Lặp board + side-to-move 3 lần => adjudication có đúng 1 winner.
11. 300 plies => adjudication có đúng 1 winner.
12. Bot trả sai JSON, action không hợp lệ, crash hoặc timeout => forfeit.

Thêm test:
- Phân phối 9 quân/mỗi đội đúng loại và tọa độ; tính đối xứng của bố trí.
- Không có state nào trùng hai quân; chỉ đúng 1 người thắng ở terminal.
- API smoke test tạo match -> match complete -> replay có dữ liệu.
- Chạy `DummyGamePlugin` qua cùng runner (không sửa core).
- `pytest` chạy xanh, ứng dụng start được. Nếu chưa test browser tự động thì ít nhất dùng HTTP smoke test và chỉ dẫn để kiểm tra thủ công.

## 9. Quy trình Codex phải tự thực hiện

1. Khảo sát thư mục hiện tại. Nếu trống, tạo repo. Nếu có source có sẵn, bảo tồn và tận dụng phần hợp lý.
2. Đọc PDF, viết `docs/IMPLEMENTATION_SCOPE.md` ngắn nêu giữ / lược bỏ khác biệt với đặc tả đầy đủ.
3. Tạo core plugin + OTT v2 rules và chạy unit tests trước.
4. Xây bot protocol/runner và 3 bot mẫu; chạy thử bot-vs-bot ở CLI hoặc qua test.
5. Tạo FastAPI + UI/replay, thêm lưu lịch sử cục bộ.
6. Tạo README với lệnh cài và khởi động chính xác; ví dụ:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn arena.web.app:app --reload --host 127.0.0.1 --port 8000
# Truy cập http://127.0.0.1:8000
```

7. Tự chạy `pytest` và kiểm tra API thực tế bằng lệnh phù hợp. Nếu có lỗi hãy sửa trước khi kết thúc. Không tuyên bố đã chạy/test nếu chưa thực sự thực hiện được.
8. Kết thúc bằng báo cáo ngắn: cây thư mục, công nghệ, tính năng hoàn thành, tính năng cố ý bỏ, lệnh chạy/test, kết quả test, các hạn chế còn lại.

## 10. Tiêu chí ưu tiên khi phải đơn giản hóa

Ưu tiên theo thứ tự: **đúng luật > bot thực sự đấu được > web UI chạy local > replay > khả năng thay game > lịch sử/thống kê > hiệu ứng đẹp**. Không hy sinh test luật và ranh giới plugin để thêm chức năng phụ.

**Bắt đầu triển khai trực tiếp trong workspace bây giờ. Chỉ kết thúc khi đã tạo các file mã nguồn và ít nhất chạy được test engine/bot, thay vì dừng ở bản thiết kế.**
