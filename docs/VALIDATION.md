# Kết quả kiểm tra – 11/10/2026

Môi trường thực chạy: Linux, Python 3.14.4, dependency trong requirements-lock.txt.

- Engine trước tích hợp: `python3 -m pytest tests/test_engine.py -q`: 27 pass.
- Engine + runner trước UI: 42 pass.
- Bản cuối: `.venv/bin/python -m pytest -q`: **54 passed, 1 warning in 1.51s**.
  Warning là StarletteDeprecationWarning của TestClient đang dùng httpx 0.28.1;
  không phải lỗi runtime ứng dụng. Không có test fail/skip trong Linux lần chạy này.
- `.venv/bin/python -m compileall -q arena bots tests scripts`: pass.
- `.venv/bin/python -m pip check`: No broken requirements found.
- HTTP thật: `.venv/bin/python scripts/smoke_local.py`: PASS. Capture Greedy thắng
  Goal Rush 2–0, hai game 23 và 26 plies; không forfeit. Tạo trận 202, đọc trạng thái,
  replay, history và stats 200. Chạy lại sau restart cũng PASS.
- Restart server thật: các trận cũ còn trong lịch sử, có thể mở replay; pytest cũng
  kiểm tra metadata/replay giữ nguyên, khôi phục commit dang dở và INTERRUPTED.
- Browser: tạo BO1/BO3, chọn bot, đổi game BO3, xác nhận side mapping, trước/sau,
  slider Home/End, tốc độ 0.5×/2×, tự phát và tạm dừng, kết quả và lịch sử.
  Board có 81 ô; a1 dưới trái/i9 trên phải. Desktop 1280 và mobile 390 được kiểm
  tra không tràn ngang. Console kiểm tra không có error/warn.
- Ảnh minh họa giao diện được lưu tại `arena-preview.jpg`, `arena-full.jpg`,
  `arena-mobile.jpg`. Ảnh full-page dùng kích thước panel thực lúc chụp.

Bộ test bao gồm toàn bộ 12 case bắt buộc; cả hai bên phân xử, đúng hash cuối,
300 plies/lặp board+turn, bot JSON sai, requestId/turnId sai, crash/timeout,
stdout quá dài/spam, stderr spam, cleanup process group Linux, bot giữ process
nhiều quyết định, ba cặp bot thực và determinism, BO3 hai/ba game, DummyGamePlugin
qua cùng runner với subprocess thật, API validation/queue và persistence.

Giới hạn kiểm tra: chưa chạy hệ điều hành Windows/macOS thực; cảnh báo resource
subprocess không phải sandbox được hiển thị trong UI/README. Browser kiểm tra qua
Codex, không có dependency browser automation trong test suite của dự án.

Trong môi trường Codex, cài dependency và socket local cần quyền ngoài sandbox;
đã cài thành công .venv và chạy server chỉ bind 127.0.0.1:8000. Không cần quyền này
khi chạy ứng dụng trong terminal local thông thường.
