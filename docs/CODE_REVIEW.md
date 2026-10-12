# Rà soát và tối ưu OTT v2 Arena — 12/10/2026

Đã kiểm tra engine, registry/plugin, JSONL runner, sandbox, source submissions,
SQLite/replay, giải đấu, API và polling giao diện. Sửa trực tiếp mã nguồn, thêm
kiểm thử hồi quy, chạy API/browser và đo các thao tác có chi phí rõ ràng.
Không thêm dependency runtime, không đổi điều kiện thắng hoặc luật di chuyển,
không thêm hạ tầng, không thay phiên bản bot/bộ luật đã khóa trong dữ liệu cũ.

## Các vấn đề đã sửa

| Vấn đề / tác động | Sửa đổi | Kiểm chứng |
| --- | --- | --- |
| `with sqlite3.connect()` chỉ commit/rollback, không đóng connection; fd tích lũy đến lúc GC | Store.connect dùng contextmanager đóng connection trong finally; WAL và index trạng thái | Transaction rollback/connection closed; trước tối ưu 200 lần đọc làm fd 5→205 khi tắt GC; sau tối ưu 4→4 |
| Kiểm tra hàng đợi giải mã toàn bộ lịch sử, scheduler đọc lại các giải đã xong | SQL COUNT/filter/index; chỉ đọc trạng thái cần thiết | Benchmark 10.000 trận và 100 giải hoàn tất |
| Đấu thử kiểm tra capacity riêng với scheduler giải; nhận đồng thời có thể vượt 8 trận | COUNT + INSERT/claim trong cùng BEGIN IMMEDIATE, dùng chung capacity | 24 yêu cầu cạnh tranh: chỉ 8 được nhận; giải chờ khi đầy |
| Quota đội/bài nộp kiểm tra ngoài transaction | Kiểm tra quota và cấp version trong transaction; index tra key/status/team | 8 thread cạnh tranh với quota fixture 2: chỉ 2 được nhận, version 1/2, không tạo folder thừa |
| Đọc/parse toàn bộ replay trên mỗi poll live 250 ms | Cache snapshot giới hạn 32 trận × 20 frame, deep copy và lock; cache miss đọc disk | Client không sửa được snapshot cache; eviction/restart đọc đúng disk; disk read cũ không ghi đè frame mới |
| Exception lặp lại khi commit kết quả làm scheduler dừng | Giữ matchId chưa commit; thử ghi lại kết quả đã lưu; recover completed replay nếu cần | Inject hai lỗi commit: giải vẫn xong, một matchId, một kết quả, không chạy bot lại |
| Callback trạng thái cũ có thể hạ COMPLETED về RUNNING | Bỏ qua cập nhật fixture đã hoàn tất hoặc attempt cũ | Standings không đổi sau callback cũ |
| Claim fixture tạo lại metadata, thay createdAt | Đọc metadata trận đã lưu trước khi đổi trạng thái | Timestamp lập lịch được giữ nguyên |
| Poll trận cũ tiếp tục sau khi đổi viewer; response/import cũ có thể ghi đè board | Poller một session, abort fetch/timer cũ, kiểm tra session sau mỗi await | 4 test JS với response/renderer/error trễ; thử đổi nhanh hai replay trên browser |
| Poll giải cùng selection có thể chồng nhiều timer/response | Request sequence và chỉ lịch poll của request mới nhất còn hiệu lực | Luồng browser tạo/theo dõi/mở replay và console sạch |
| Renderer preview có thể vẫn là luật trước đó hoặc response khởi tạo ghi đè lựa chọn mới | Import renderer từ manifest đang chọn; kiểm tra version/viewer sau await | Chuyển 1.0 ẩn anti-stall, trở lại 1.1 hiện đúng bộ đếm |
| Bài nộp/đăng nhập đội cũ trả về sau khi đổi đội | Session/request guard; chỉ xóa key đã lưu khi xác thực trả 401 | Giữ ownership API và không xóa key do lỗi tải dữ liệu tạm thời |
| Observation/snapshot/status/event chứa tham chiếu nested dictionary của engine | Deep copy lastMove/details/event; copy metadata targets | Sửa dữ liệu xuất ra không làm thay đổi state; kiểm tra cả 1.0 và 1.1 |
| Validator bot mặc định A đi trước, ràng buộc lõi vào OTT | Lấy bên đi trước từ plugin.status | Plugin test B đi trước nhận bot READY và thi đấu trong sandbox qua cùng API/runner |
| Lỗi Pydantic chỉ báo số lỗi, không nêu field; cần tránh echo source/secret | Trả field + lỗi, tối đa 3, bỏ input/context | API 422 nêu seed/field dư, không echo giá trị bí mật |

Danh sách/query bài nộp cũng được lọc trong SQL; MatchRunner lấy catalog một lần
mỗi game thay vì tạo lại cho từng slot. Tác vụ scheduler claim và tiếp nhận source
được đưa ra khỏi event loop. Bỏ import thừa; snapshot/replay cũ vẫn đọc được.

## Kết quả kiểm thử

- `.venv/bin/python -m pytest -q`: **126 passed, 1 warning in 20.22s**.
- `node tests/poller.test.mjs`: **4 passed**.
- Python compileall, node --check app.js/tournaments.js và pip check thành công.
- Warning test là Starlette/httpx deprecation; pip check không có dependency conflict.
- Ba smoke HTTP chạy tuần tự trên localhost đều **PASS**:
  - Trận BO3: `ba958af1ba68435e8ef8e78d01af6c19`, Capture Greedy thắng 2–0, 23/26 plies.
  - Bot tự nộp: READY, liveSeen=true, trận `80e0ee1e75b94baf8983eeb0bdc7c8a1`, 26 plies.
  - Giải `7342716140314c029ae618a7247ae5cc`: 3 đội, 3 fixture BO3 hoàn tất;
    nộp v2 sau khóa vẫn dùng v1 trong mọi replay, liveSeen=true, tất cả bot đội
    nộp dùng bubblewrap+seccomp.
- Browser: đổi luật 1.0/1.1, đổi nhanh hai replay, tên bot/seed/score đúng;
  console không có error/warn. Ảnh xác minh: [review-proof.jpg](review-proof.jpg).

## Số đo hiệu năng

Lệnh `.venv/bin/python scripts/benchmark_core.py`; tạo dữ liệu tổng hợp trong thư
mục tạm: 10.000 trận, 100 giải hoàn tất với 120 fixture/giải, replay 300 frame.
Trung bình 30 lần gọi/thao tác, đo cùng một lượt chạy trên máy hiện tại:

| Thao tác | Đọc/giải mã toàn bộ | Sau tối ưu |
| --- | ---: | ---: |
| Đếm hàng đợi | 11,488 ms | 0,193 ms |
| Tìm công việc giải | 3,829 ms | 0,217 ms |
| Đọc dữ liệu phục vụ live | Replay disk 1,708 ms | Snapshot cache 0,047 ms |

Đọc SQLite 200 lần khi GC tắt: fd trước/sau đều 4. Số đo thay đổi theo tải máy,
cache và kích thước dữ liệu; đây là benchmark từng thao tác, không phải tuyên bố
toàn bộ website hoặc engine nhanh hơn theo cùng tỷ lệ.

## Lệnh chạy / kiểm tra lại

Tại thư mục dự án:

```bash
.venv/bin/python -m arena
.venv/bin/python -m pytest -q
node tests/poller.test.mjs
.venv/bin/python scripts/benchmark_core.py
```

Ứng dụng: http://127.0.0.1:8000/. Smoke cần server đang chạy, Linux sandbox hoạt
động và nhịp frame mặc định. Node chỉ dùng cho test JS, không cần để chạy Arena.

## Giới hạn còn lại

Một server process/worker; thống kê bot vẫn tổng hợp toàn bộ trận hoàn tất và
replay đầy đủ vẫn ghi atomic sau mỗi frame. Cache live giới hạn bộ nhớ nhưng không
thay cơ chế replay bền vững. Chưa đo tải nhiều người dùng online, chưa triển khai
VPS/HTTPS hoặc kiểm toán sandbox độc lập. Sandbox vẫn chia sẻ kernel host.
Không có cam kết rằng mọi lỗi hoặc rủi ro đều đã bị loại bỏ; các tình huống nêu
trên có kiểm thử và kết quả thực tế đi kèm.
