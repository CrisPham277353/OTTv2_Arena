# Đội tự viết bot OTT v2

1. Tải `starter_bot.py` và `bot_sdk.py`, đặt cùng thư mục trên máy của đội.
2. Đổi tên file chiến thuật và viết hàm `choose(observation, rng)`.
3. Tạo đội trên website, lưu mã truy cập. Thành viên dùng cùng mã để nộp bài.
4. Nộp **file chiến thuật .py**; hệ thống tự đặt bot_sdk.py vào phiên bản đã lưu.
5. Chờ trạng thái Sẵn sàng thi đấu, bấm Đấu thử hoặc chọn bot đội khác để đấu.

Mỗi lần nộp tạo phiên bản mới, giữ nguyên source/hash phiên bản cũ. Đội chỉ xem
và tải được source của mình; catalog/replay/kết quả trận công khai.

Observation OTT: side, target, ply, pieces, lastMove, legalActions. Action:
`{"type":"MOVE","from":"d4","to":"e5"}`. Chọn action từ legalActions sẽ đúng luật.
Quân: D ăn K, K ăn L, L ăn D. Mỗi lượt một ô trong 8 hướng, A tới i9, B tới a1.

Nếu tự viết loop không dùng SDK: stdin/stdout JSONL. Trả type=action,
protocolVersion=1.0, echo requestId/turnId và action. Flush stdout.
Giới hạn 500 ms/quyết định, 64 KiB/dòng stdout, 1 MiB stderr/game.

Runtime Linux: namespace riêng và seccomp; cấm network, tạo process/thread,
chạy chương trình khác, đọc file riêng của host, sửa source hoặc nâng giới hạn.
RAM address-space 256 MiB, CPU tổng 160 s, file 1 MiB, /tmp 64 MiB, 64 FD.
Sử dụng Python stdlib và code trong một file .py. Chưa hỗ trợ ZIP, pip hoặc file phụ
của đội. Bot lưu trạng thái trong process, nhận nhiều lượt, khởi động lại mỗi game.

Kiểm tra tự động gồm cú pháp và tối đa 6 quyết định hợp lệ trong sandbox. Qua kiểm
tra không bảo đảm bot sẽ không lỗi ở một thế cờ khác; lỗi trong trận vẫn xử thua.
Website hiện bàn cờ trong trận, sau đó cho tua replay từ snapshot engine đã lưu.

## Bộ luật 1.1.0

Bài nộp và trận mới chọn bộ luật 1.1.0 hoặc 1.0.0. Phiên bản code đã ghim 1.0.0
vẫn đấu theo 1.0.0; hãy nộp lại khi muốn dùng luật mới. Cả hai giữ điều kiện thắng
xóa một loại; 1.1 ghi thêm thắng ăn hết toàn bộ quân.

Observation 1.1 có antiStall: noCapturePlies (giới hạn 50), noProgressTurns[A/B]
(giới hạn 15 lượt riêng) và bestGoalDistance[A/B]. Capture hoặc lập khoảng cách
gần đích tốt hơn kỷ lục cũ reset tiến độ của mình. Lùi rồi quay lại không reset.
15 lượt riêng không tiến độ thì thua. 50 lượt không capture thì phân xử; lặp ba
lần/300 lượt vẫn phân xử. Không có DRAW.
