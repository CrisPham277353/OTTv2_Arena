# OTT v2 1.1.0 – thắng do hết quân và chống kéo dài trận

Bộ luật mặc định cho trận mới là 1.1.0. Bộ luật 1.0.0 vẫn được đăng ký riêng,
giữ nguyên logic cũ và được chọn trong form tạo trận. Mọi match/replay ghi version.
Bài nộp của đội vẫn ghim gameVersion đã kiểm tra; để dùng 1.1.0, nộp một phiên bản
bot mới với bộ luật kiểm tra 1.1.0. Không đổi source/hash/version cũ một cách ngầm định.

## Điều kiện thắng

Giữ bố trí 9 quân/bên, di chuyển một ô/8 hướng, D ăn K/K ăn L/L ăn D, chặn quân
cùng loại và đích a1/i9 như bản 1.0.

Sau một nước hợp lệ, kiểm tra theo thứ tự:
1. GOAL_REACHED: A vào i9 hoặc B vào a1.
2. ARMY_ELIMINATED: nước ăn khiến đối phương còn 0 quân.
3. TYPE_ELIMINATED: nước ăn khiến đối phương hết một loại D/L/K.
4. NO_LEGAL_MOVES: đổi lượt, đối phương không còn nước hợp lệ.
5. NO_PROGRESS: bên vừa đi có 15 lượt riêng liên tiếp không tạo tiến độ.
6. Phân xử khi lặp board+side 3 lần, 50 plies không ăn quân, hoặc 300 plies.

Người dùng chọn GIỮ CẢ HAI điều kiện hết quân/hết loại. Vì một loại hết thường
xảy ra trước toàn bộ quân hết, trận chuẩn có thể kết thúc ở TYPE_ELIMINATED trước
khi có cơ hội ăn hết quân. ARMY_ELIMINATED là điều kiện riêng, được ưu tiên khi
nước cuối làm cả hai điều kiện đồng thời đúng. Không xóa luật thắng sớm đã chọn.

## Hai luật chống kéo dài mới

**50 lượt liên tiếp không ăn quân (25 vòng A/B):** bộ đếm chung tăng mỗi move,
reset về 0 khi capture. Đạt 50 mà chưa thắng theo điều kiện trước: ADJUDICATED,
trigger NO_CAPTURE_LIMIT. Không tự xóa quân hay tạo chướng ngại.

**15 lượt RIÊNG không tạo tiến độ:** mỗi bên có bộ đếm riêng, chỉ cập nhật khi
bên đó đi. Tiến độ là capture hoặc lập kỷ lục khoảng cách gần đích mới: khoảng
cách Chebyshev nhỏ nhất của bất kỳ quân cùng bên đến đích, nhỏ hơn tốt nhất đã
đạt được trước đó. Khi có tiến độ reset về 0; nếu không tăng 1. Đạt 15: bên đó
thua, NO_PROGRESS. Đi tới rồi lùi lại một ô đã từng đạt không reset bộ đếm.

Ví dụ: kỷ lục A là 4; lùi ra khoảng cách 5, rồi trở về 4 không được tính tiến độ.
Đi tới 3 hoặc ăn quân sẽ reset. Capturing luôn được tính tiến độ dù quân không
đi gần đích hơn. Quân gần đích nhất bị ăn không nâng lại kỷ lục của bên bị ăn.

Luật này chủ động phạt phòng thủ kéo dài và có thể phạt việc tái bố trí chiến thuật
lâu. Đây là thay đổi cân bằng gameplay có chủ đích; chưa benchmark giải lớn.
BO3 tiếp tục đảo bên để giảm lợi thế đi trước. Bot đọc antiStall trong observation
để biết số lượt còn lại và kỷ lục khoảng cách; UI/replay hiển thị cùng counters.

## Phân xử không hòa

Giữ bộ tiêu chí: số quân sống lớn hơn, số quân cách đích ≤2 lớn hơn, khoảng cách
nhỏ nhất thấp hơn, tổng khoảng cách thấp hơn. Nếu bằng tất cả: bit cuối SHA256 của
str(seed)+gameInstanceId+trigger, 0=A/1=B. Replay ghi metrics/hash nếu dùng tie-break
và noCapturePlies/noProgressTurns/bestGoalDistance. Không có kết quả DRAW.

NO_PROGRESS được xét trước các trigger phân xử, sau các thắng tự nhiên/thế bí.
Trong phân xử, trigger ưu tiên THREEFOLD_REPETITION → NO_CAPTURE_LIMIT → PLY_LIMIT.
Một nước vào đích/ăn quân cuối thắng ngay dù cũng chạm giới hạn lượt.

## UI và tương thích

- Form trận chọn bộ luật 1.1.0 (mặc định) hoặc 1.0.0.
- Form nộp code chọn bộ luật kiểm tra. Dropdown bot trận lọc theo version đó.
- Nút Đấu thử của bài nộp tự chọn version đã ghim, kể cả bài nộp 1.0.0 cũ.
- Trận mới 1.1 có thanh áp lực: không ăn quân /50 và không tiến độ A/B /15.
- Trận/replay cũ giữ snapshot cũ; counters được ẩn nếu snapshot không có antiStall.
- Tất cả luật nằm trong plugin OTT v2, core chọn default bằng cờ manifest isDefault.
  Không có xử lý riêng OTT trong MatchRunner.
