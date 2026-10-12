# Kiểm tra phần giải đấu — 12/10/2026

## Automated tests

Lệnh `.venv/bin/python -m pytest -q`: **115 passed, 1 warning in 17.56s**.
Cảnh báo là Starlette TestClient deprecation về httpx, không phải lỗi runtime.
`node --check` cả app.js/tournaments.js và Python compileall đều thành công.

Bao gồm kiểm tra lịch cho 2–16 đội: mỗi cặp đúng một lần, một trận/đội/vòng,
lượt nghỉ khi lẻ; claim atomic giữa nhiều thread; quyền chủ giải; chỉ đăng ký
bot của đội có READY và đúng gameVersion; thay/rút trước khóa và cấm sau khóa;
start rollback toàn bộ nếu artifact lỗi; max 16 đội/120 fixtures; snapshot hash
và phiên bản bất biến; bảng điểm/hiệu số/đối đầu/đồng hạng; khôi phục metadata
từ replay hoàn tất; gián đoạn thành PAUSED và retry giữ seed/attempts;
file sửa sau khóa không được chạy/tính điểm; khôi phục file rồi retry thành công;
seed lịch không vượt 53 bit và replay seed lớn có chuỗi hiển thị chính xác.

Một lần kiểm tra phát hiện test cleanup process cũ đọc `/proc/<pid>/stat` đúng lúc
process đã được reaped, Linux trả ProcessLookupError. Test đã xử lý trường hợp này
cùng FileNotFoundError; không nới kiểm tra process còn sống hoặc sửa hành vi runner.

## HTTP thật

`.venv/bin/python scripts/smoke_tournaments.py`: **PASS** trên bản cuối.
Giải `f5a944a298824a508edcd2e7c0059f01`:

- 3 đội QA nộp 3 file Python qua HTTP, đạt READY qua sandbox.
- 3 fixture BO3 hoàn tất; quan sát được snapshot khi trận RUNNING.
- Nộp v2 sau khi khóa: toàn bộ replay vẫn dùng artifact v1.
- Tất cả process đội nộp có runtime bubblewrap+seccomp, không BOT_FORFEIT.
- Bảng điểm: Capture Greedy 6; Random 3; Goal Rush 0. Mỗi đội đấu 2 trận.

Giải HTTP trước đó `9d603809f3b94ede80b5aeb07f62e894` cũng PASS.
Đã restart server và đọc lại giải đó cùng giải kiểm thử web: cả hai COMPLETED,
6 fixture tổng cộng, không tạo trận trùng, entries vẫn v1.

## Trình duyệt

Tạo đội QA riêng, nộp goal_rush.py qua file chooser, chờ READY, tạo giải BO3 1.1.0,
đăng ký v1, thêm hai đội QA khác rồi bấm khóa/bắt đầu trên web.
Giải `d827d495c9274c35b88faeaba702e11a` hoàn tất 3/3 fixture.
Đã mở **Xem bàn cờ** khi game 2 đang chạy; board cập nhật lượt và bộ đếm anti-stall.
Đã mở replay sau restart, tên hai bot hiển thị đúng, seed cũ 63-bit hiển thị
`4016794438153450723` chính xác qua seedText. Console không có error/warn.

Ảnh xác minh: [tournament-proof.jpg](tournament-proof.jpg).

## Phạm vi còn lại

Chạy local một process/worker; một lượt vòng tròn, khóa thủ công khi bắt đầu.
Chưa có deadline tự động, playoff, loại trực tiếp, Elo hoặc hủy/xóa giải trên UI.
Chưa publish Internet. Giữ nguyên giới hạn/an toàn sandbox hiện có và ranh giới
plugin; không thêm dependency, Redis hay Kubernetes.
