# Nghiệm thu bài nộp và live board – 12/10/2026

Môi trường: Linux, Python 3.14.4, bubblewrap, libseccomp2. Chạy ngoài sandbox Codex
để user namespaces hoạt động; app vẫn bind 127.0.0.1:8000.

- Bộ pytest: **67 passed, 1 warning in 7.23s**.
  Giữ 54 test gốc và thêm bài nộp, auth/ownership, phiên bản, hash/tamper,
  fail-closed, live snapshot, sandbox isolation/RAM và hai đội nộp bot đấu BO3.
- Sau hardening seccomp bổ sung keyring/IPC, test sandbox riêng: **3 passed**.
- Sau giới hạn body cho mọi POST/OpenAPI, test API + submissions + live: **14 passed**.
- Warning deprecation của Starlette TestClient/httpx, không có lỗi runtime.
- Smoke HTTP thật scripts/smoke_submissions.py: PASS; bài nộp READY, liveSeen=true,
  trận hoàn tất sau 26 plies, ADJUDICATED; bot nộp chạy bubblewrap+seccomp.
- Browser: tạo đội, chọn file .py, nộp code, trạng thái READY, phiên bản v1/v2 cùng
  tồn tại, bấm Đấu thử, bàn cờ ở trạng thái ĐANG THI ĐẤU cập nhật theo từng nước.
  Console kiểm tra không có error/warn. Ảnh: submitted-bot-live.jpg.
- Restart server thật: mã đội đã lưu đăng nhập lại được; hai phiên bản vẫn READY,
  sandbox probe xanh và source/history còn. Pytest kiểm tra cả persistence/replay.
- Syntax sai, JSON sai, crash/timeout không vào catalog thi đấu; runtime không có
  không fallback sang subprocess thường. X-Team-Key sai hoặc đội khác không đọc
  được source. Source/hash/SDK bất biến; sửa file host làm verify thất bại.
- Sandbox thật chặn đọc file riêng host, ghi root/source, tạo socket, fork,
  nâng resource limits; bộ nhớ 400 MiB bị MemoryError với ceiling 256 MiB.

Chưa publish Internet: người dùng xác nhận chưa có VPS và domain. Chưa kiểm toán
bảo mật độc lập. Online cần HTTPS reverse proxy và host Linux được cập nhật.
Hiện chỉ nhận một file .py + SDK supplied, không ZIP/pip/file phụ đội.
Kiểm tra protocol là smoke check một số thế cờ, không chứng minh bot đúng mọi lượt.

Test cleanup cũ có race khi child biến mất giữa exists/read /proc; đã sửa test
coi FileNotFoundError là dấu hiệu child được reap thành công.
