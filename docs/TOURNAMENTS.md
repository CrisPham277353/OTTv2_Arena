# Giải đấu vòng tròn

Chạy cùng ứng dụng Arena hiện có, không thêm dependency hay dịch vụ. SQLite tự tạo
bảng `tournaments`; dữ liệu đội, bot, trận và replay cũ được giữ nguyên. Lõi giải
trong `arena/core/tournaments.py` không import engine OTT và dùng đúng plugin/version
được chọn khi tạo giải.

## Tổ chức giải trên web

1. Tạo/vào đội bằng mã truy cập đội ở đầu trang. Đội tạo giải là chủ giải;
   chỉ chủ giải được bắt đầu hoặc tiếp tục giải bị tạm dừng.
2. Mở **Tạo giải mới**, nhập tên, game/bộ luật, BO3 (mặc định) hoặc BO1 và seed.
3. Gửi **Liên kết đăng ký giải** cho các đội. Website hiện chỉ chạy localhost;
   liên kết dùng cùng máy cho tới khi có triển khai Internet.
4. Mỗi đội nộp bot cho đúng bộ luật của giải, chờ trạng thái **READY**, rồi chọn
   phiên bản và bấm **Đăng ký / đổi bot**. Một suất/đội, tối đa 16 đội. Các đội
   được đổi phiên bản hoặc rút khỏi giải khi trạng thái còn OPEN. Chủ giải có thể
   tham gia hoặc chỉ tổ chức. Không đăng ký bot mẫu thay cho một đội.
5. Khi có ít nhất hai đội, chủ giải bấm **Khóa bot & bắt đầu giải**. Server kiểm tra
   lại toàn bộ artifact trước khi khóa và tạo lịch trong một transaction.
6. Lịch tự chạy; bấm **Xem bàn cờ** để theo dõi snapshot trận đang đấu. Kết thúc
   có **Xem replay** và kết quả được tính vào bảng xếp hạng.

Không tự chọn bài nộp mới nhất: ID bot được chọn là một phiên bản cụ thể. Sau khóa,
đội vẫn được nộp code để đấu thử hoặc dùng cho giải khác, nhưng không đổi bot của
giải này. Tạo giải khác nếu cần đổi bộ luật/thể thức/seed.

## Phiên bản khóa và lịch

Mỗi entry khóa teamId, botId, botVersion, gameVersion, sourceSha256 và artifactSha256
(source + SDK). File được kiểm tra lại trước khi bắt đầu từng trận. Bản bot nộp
luôn chạy bằng sandbox Linux hiện có; thiếu runtime không được bắt đầu/tiếp tục.
Source chỉ được đọc bởi đội sở hữu, không xuất source/mã truy cập trong API giải.

Lịch dùng thuật toán vòng tròn, một cặp gặp nhau đúng một lần:
`n(n−1)/2` trận, tối đa 120 trận. Số đội chẵn có `n−1` vòng, số đội lẻ có `n` vòng
và mỗi đội nghỉ một vòng. Mỗi đội tối đa một trận trong cùng vòng. Các trận chạy
tuần tự trên worker hiện có; không cấp phát 120 subprocess hay xếp 120 job vào
executor. Trận được lên lịch có trạng thái SCHEDULED, chỉ trận kế tiếp chuyển
sang QUEUED/RUNNING. Worker còn dùng cho kiểm tra bài nộp và trận đấu thử.
Đấu thử và giải dùng chung giới hạn 8 trận QUEUED/RUNNING, kiểm tra và nhận trận
trong transaction để các yêu cầu đồng thời không vượt giới hạn.

Seed từng fixture được lấy từ 8 byte đầu SHA256(`str(seedGiải) + ':fixture:' + str(sốTrận)`)
và AND `(2**53−1)` để JavaScript biểu diễn chính xác; seed ghi trong lịch và replay.
API replay còn có `seedText` để hiển thị chính xác seed 63-bit của dữ liệu cũ.
BO3 đảo A/B ở game 2, game 3
dùng quy tắc MatchRunner hiện có. ID trận và seed được lưu để truy vết, không hứa
rằng hai giải khác ID có cùng kết quả phân xử hash.

## Bảng xếp hạng

Chỉ tính fixture COMPLETED, mỗi trận BO1/BO3 thắng được 3 điểm, thua 0:

1. Điểm trận cao hơn.
2. Hiệu số game thắng − game thua cao hơn.
3. Tổng game thắng cao hơn.
4. Điểm thắng đối đầu trong nhóm đội bằng **cả ba** tiêu chí trước.
5. Bằng tất cả: đồng hạng (1, 1, 3...). Tên/ID chỉ sắp thứ tự hiển thị các đội đồng hạng.

Bot bị xử thua theo protocol/timeout/nước sai vẫn là kết quả game hợp lệ và tính
điểm trận. Lỗi hệ thống, thiếu sandbox hoặc sai hash artifact không tự xử một đội
thua, không cộng điểm và tạm dừng giải. API chi tiết trả lịch và standings tính
từ cùng một snapshot để tránh bảng điểm và số trận lệch nhau khi trận vừa xong.

## Khởi động lại và chạy lại trận lỗi

`OPEN → RUNNING → COMPLETED`; trận lỗi/gián đoạn làm `RUNNING → PAUSED`.
Các fixture chưa chạy và kết quả hoàn tất được lưu SQLite. Dừng server bình thường
chờ trận đang chạy hoàn tất rồi giữ lịch chưa chạy; restart tự chạy tiếp giải RUNNING.
Nếu server bị kill giữa trận, Store khôi phục replay hoàn tất nếu có; nếu chưa có,
trận thành INTERRUPTED và giải PAUSED. Không âm thầm chạy lại một trận bị gián đoạn.
Nếu trận đã hoàn tất nhưng cập nhật fixture gặp lỗi tạm thời, scheduler thử ghi
lại kết quả đã lưu. Bot không chạy lại và điểm không được tính hai lần.

Chủ giải bấm **Tiếp tục / chạy lại trận lỗi**: kiểm tra lại **đúng** artifact đã khóa,
tạo matchId mới cho trận lỗi, giữ fixture/seed và lưu matchId/status/error cũ trong
`attempts`. Trận đã hoàn tất không chạy lại và không tính điểm hai lần. File bị sửa
cần khôi phục đúng nội dung đã khóa; nộp phiên bản mới không thay được bản khóa.

## API

Các endpoint GET là công khai; POST cần header `X-Team-Key`, cùng-origin và hạn
mức thao tác ghi hiện có. Không gửi mã đội trong URL.

| Endpoint | Chức năng |
| --- | --- |
| POST /api/tournaments | Tạo giải: name, gameId, gameVersion, format, seed |
| GET /api/tournaments | Danh sách giải, số đội/trận/tiến độ |
| GET /api/tournaments/{id} | Entries, phiên bản/hash đã khóa, fixtures, attempts và standings |
| GET /api/tournaments/{id}/standings | Bảng xếp hạng |
| POST /api/tournaments/{id}/entries | Đăng ký/đổi bot của đội: `{ "botId": "submitted-…" }` |
| POST /api/tournaments/{id}/withdraw | Đội rút trước khi khóa |
| POST /api/tournaments/{id}/start | Chủ giải khóa và tạo lịch |
| POST /api/tournaments/{id}/resume | Chủ giải tiếp tục/chạy lại trận lỗi |

Trận/replay có thêm tournamentId/fixtureId; vẫn dùng endpoint `/api/matches/{id}/live`
và `/replay` cũ. Tối đa 100 giải/server. UI poll giải 1 giây khi RUNNING, 3 giây
các trạng thái khác; bàn cờ vẫn poll 250 ms. Chỉ chạy một server process.

## Kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_tournaments.py
```

Smoke cần localhost:8000 đang chạy, sandbox hoạt động và nhịp frame mặc định để
quan sát live. Script tạo 3 đội QA, nộp 3 file Python thật, chạy 3 cặp BO3, nộp v2
sau khóa và xác nhận mọi replay vẫn dùng v1. Không in mã truy cập đội.

Phạm vi hiện tại: một lượt vòng tròn, khóa thủ công lúc bắt đầu, đồng hạng khi
bằng tất cả tiêu chí; chưa có deadline tự động, loại trực tiếp, playoff, giải thưởng,
Elo, nhiều worker hay giao diện hủy/xóa giải. Mở Internet vẫn cần VPS/HTTPS và
đánh giá an toàn sandbox như tài liệu bài nộp đã nêu.
