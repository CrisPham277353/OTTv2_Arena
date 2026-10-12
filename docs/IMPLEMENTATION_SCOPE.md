# Phạm vi OTT v2 Arena local

Đã đọc toàn bộ PDF thiết kế 1.0 (20 trang) trong `codex_ottv2_starter/docs/`.
Ưu tiên PROMPT_CODEX.md khi phạm vi hoặc luật khác PDF.

Giữ: luật 9×9, 9 quân/bên, Đấm–Lá–Kéo, đích, xóa loại, không nước đi,
phân xử không hòa, plugin có phiên bản, JSONL, timeout 500 ms, BO1/BO3,
replay snapshots, bot Python tồn tại suốt game, lịch sử và thống kê.

Thay stack đầy đủ bằng FastAPI + HTML/Jinja/CSS/JS thuần, SQLite stdlib,
file replay JSON, một worker thread tuần tự trong cùng process. Không cần npm.
Bỏ: tài khoản/đội online, upload/build public, giải nhiều vòng, Redis/Celery,
PostgreSQL, S3, Elo, Docker/Kubernetes, sandbox bảo mật, socket.

Core chỉ dùng GamePlugin, GameStatus, StepResult, manifest và envelope bot.
Luật và phân xử thuộc plugin; frontend tải renderer từ manifest. Dummy plugin
trong test chứng minh chạy bằng cùng runner mà không sửa lõi.

Phân xử cuối: UTF-8 của `str(seed) + gameInstanceId + trigger` (không dấu phân cách),
bit cuối SHA256: 0 chọn A, 1 chọn B. Replay ghi input/hash/bit và các tiêu chí.
BO3 game 1/2 đảo bên; game 3 dùng bit cuối SHA256(str(seed)+":side:3").

## Mở rộng theo yêu cầu ngày 12/10/2026

Người dùng yêu cầu đội tự viết/nộp code qua web, tự kiểm tra và chạy trong sandbox,
hiển thị bàn cờ trong trận. Đã mở rộng phạm vi bằng team key, phiên bản source/SDK
bất biến, cú pháp/JSONL smoke check trong bubblewrap+seccomp, ownership API,
/live snapshot polling. Đây thay thế phần lược bỏ upload/sandbox/live ban đầu.
Người dùng xác nhận chưa có VPS/domain, nên chưa publish Internet.
Luật OTT v2 và ranh giới GamePlugin vẫn giữ nguyên; chưa triển khai bracket giải.

## Luật 1.1.0 theo yêu cầu ngày 12/10/2026

Giữ 1.0.0 để tương thích. Thêm 1.1.0 mặc định với ARMY_ELIMINATED; người dùng
chọn giữ cả TYPE_ELIMINATED. Thêm 50 plies không capture phân xử và 15 lượt riêng
không capture/lập khoảng cách đích tốt nhất mới thì thua. Core registry chọn default
từ manifest, không chứa luật game. Bot/replay cũ vẫn ghim version.

## Giải đấu theo yêu cầu tiếp theo ngày 12/10/2026

Người dùng yêu cầu khóa phiên bản bot, lịch tự động và bảng xếp hạng. Đã thêm giải
vòng tròn 2–16 đội, một lượt, BO3/BO1; đăng ký bằng team key hiện có, chủ giải khóa
ID/hash artifact/bộ luật, lịch tự chạy từng trận và tính điểm từ kết quả hoàn tất.
Restart giữ kết quả/lịch; trận lỗi làm PAUSED, chủ giải tiếp tục với đúng bản khóa,
lưu lịch sử attempt cũ. Phần này thay thế việc lược bỏ giải ban đầu; vẫn không thêm
Redis, Kubernetes, tài khoản email/password hay thay đổi luật/plugin contract.
