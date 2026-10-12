# Bài nộp của đội và bàn cờ đang đấu

## Luồng sử dụng

1. Mở web Arena, tạo đội. Lưu mã truy cập đội được hiển thị một lần. Thành viên
   dùng mã này để vào đội, nộp bài và tải source; catalog/kết quả/replay công khai.
2. Tải starter_bot.py và bot_sdk.py. Đội tự viết choose(observation, rng) trong
   file .py của mình. Nộp file chiến thuật; server cung cấp SDK đã đóng băng.
3. Mỗi bài nộp tạo phiên bản riêng, giữ source UTF-8, hash source, hash cả artifact,
   game/version, tên đội/bot, thời điểm, trạng thái và thông báo kiểm tra.
4. Hệ thống kiểm tra cú pháp mà không execute, rồi chạy tối đa 6 quyết định của
   cùng bot phía A trong sandbox. Đối thủ kiểm tra chọn nước hợp lệ đầu tiên.
   Trạng thái: PENDING_CHECK → CHECKING → READY hoặc CHECK_FAILED. Syntax sai là
   INVALID. Runtime không hoạt động là SANDBOX_UNAVAILABLE, không có fallback.
5. READY: bấm Đấu thử hoặc chọn hai phiên bản của đội và đối thủ trong form trận.
   Đội tạo trận phải sở hữu ít nhất một bot được nộp trong cặp đấu.
6. Bàn cờ poll `/live` 250 ms khi RUNNING. Runner phát snapshot sau từng nước,
   API không tính luật. Sau trận, toàn bộ replay và điều khiển tua được mở.

## API

- POST /api/teams `{name}` → `{teamId,name,teamKey}`. TeamKey chỉ lưu hash trên server.
- GET /api/team, GET /api/submissions: header X-Team-Key.
- POST /api/submissions: header X-Team-Key, JSON `{botName,filename,source,gameId,gameVersion?}`.
  Giao diện chọn file .py và gửi nội dung UTF-8 qua JSON, không cần multipart.
- GET /api/submissions/{id}, GET /api/submissions/{id}/source: chỉ đội sở hữu.
- GET /api/runtime: readiness sandbox.
- GET /api/bots: bot mẫu và các phiên bản READY của các đội.
- POST /api/matches: schema cũ + X-Team-Key khi chọn bot nộp.
- GET /api/matches/{id}/live: metadata và snapshot mới nhất, 20 frame gần nhất.

File tối đa 256 KiB; JSON request tối đa 512 KiB. Chỉ nhận một file .py, không ZIP,
không pip, không đường dẫn tùy ý. 100 phiên bản/đội, 1000/server, 1000 đội; 20 thao
 tác ghi/phút/IP; hàng đợi trận 8, kiểm tra 16. Chạy một server process.
Mã đội được browser lưu localStorage; dùng HTTPS khi triển khai online và bảo vệ mã
như mật khẩu. Chưa có email/khôi phục mã hay vai trò admin web; đây là mã truy cập
cho giải nhóm nhỏ. Giữ source riêng, chưa có tuyển chọn giải/bracket trong lần này.

## Sandbox Linux

Cần `/usr/bin/python3` 3.11+, `bubblewrap` và `libseccomp2`. Mỗi bot nộp chạy trong
user/PID/mount/network/IPC namespace riêng. Root và /bot chỉ đọc; /tmp 64 MiB.
Chỉ bind runtime /usr, /lib, /lib64, thư mục artifact của đúng bot và bootstrap
trusted. Không bind HOME, database, replay, credential hoặc Docker socket.
Environment sạch, chỉ có PATH/LANG/HOME/seed. Python dùng -I -S.

Bootstrap đặt giới hạn cứng AS 256 MiB, CPU tổng 160s/game, file 1 MiB, 64 FD,
core dump 0; sau đó seccomp cấm network, fork/clone/thread, exec chương trình khác,
ptrace, mount/unshare/setns, io_uring, bpf và nâng resource limits, rồi mới execute bot.
Deadline decision 500 ms, stdout/stderr limits giữ nguyên. Namespace startup có
handshake riêng và timeout 5s, không tính vào 500ms/quyết định. Dọn process group
và die-with-parent khi dừng. Runtime được probe trước khi nhận việc.

Bot mẫu đã có trong repo dùng subprocess cũ; source do đội nộp LUÔN dùng sandbox.
Qua smoke check không bảo đảm mọi tình huống đều hợp lệ, bot lỗi trong trận sẽ thua.
Bubblewrap/seccomp chia sẻ kernel host: dùng kernel được cập nhật và máy worker
riêng trước khi mở cho cộng đồng lớn. Chưa có kiểm toán bảo mật độc lập.

## Khởi động và triển khai

Linux Debian/Ubuntu: người quản trị cài bubblewrap và libseccomp2 bằng package manager.
Không vô hiệu hóa bảo vệ kernel một cách mặc định; nếu user namespaces bị chính
sách máy chặn, cấp runtime đúng theo quản trị máy hoặc chọn host hỗ trợ sandbox.
Chạy app ngoài sandbox của Codex để namespace hoạt động:

```bash
cd /home/crispham/Projects/OTTv2
.venv/bin/python -m arena
```

Mặc định localhost:8000. Bàn cờ có nhịp 120ms/nước để quan sát. Có thể đặt
ARENA_MOVE_DELAY_MS=0 để chạy nhanh hoặc 300 để xem chậm; không ảnh hưởng luật/seed.

Để online: cần VPS Linux/domain và HTTPS reverse proxy trước 127.0.0.1:8000.
Đặt `ARENA_PUBLIC_URL=https://arena.ten-mien-cua-ban` để kiểm tra Host/Origin.
Proxy chỉ forward về loopback, bảo toàn Host; không bật CORS wildcard. Giới hạn
body 512 KiB ở proxy, timeout phù hợp, rate limit đăng ký/nộp bài ở proxy. Chỉ một
Uvicorn worker trong phiên bản này; sao lưu data/ thường xuyên. Chưa triển khai
lên server/domain từ cuộc chat này vì chưa được cung cấp địa chỉ triển khai.

Tests: python -m pytest -q (Linux có sandbox); trên host thiếu sandbox các test
sandbox/integration này sẽ fail để không ngầm xác nhận môi trường không cách ly.
54 test gốc vẫn giữ; test API gốc tắt nhịp quan sát để chạy nhanh.
