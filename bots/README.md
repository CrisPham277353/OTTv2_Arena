# Viết bot Python local

**Chỉ dùng mã đáng tin cậy. Subprocess không phải sandbox bảo mật.** Bot có quyền
của user chạy app, có thể đọc/ghi file, truy cập mạng hoặc sinh process. Không upload
và không dùng bot lạ từ Internet.

1. Copy `starter_bot.py` thành `my_bot.py` trong thư mục này.
2. Sửa `choose(observation, rng)` để trả một action. Bot chỉ được xem observation:
   `side`, `target`, `ply`, `pieces`, `lastMove`, `legalActions`. Không import arena.
3. Thêm vào `manifest.json`:
   ```json
   {"id":"my_bot","name":"My Bot","script":"my_bot.py","description":"Chiến thuật của tôi","gameIds":["ottv2"]}
   ```
4. Restart server. Bot mới xuất hiện trong danh sách.

Mỗi game có hai process riêng, kể cả khi chọn cùng bot cho hai bên. Process giữ
trạng thái giữa các lượt, reset giữa các game. Interpreter dùng `sys.executable`
của server. PRNG seed lấy từ biến môi trường `ARENA_BOT_SEED`; seed cũng có trong
envelope request. Không dùng thời gian thực hoặc random không seed nếu cần tái lập.

Input: mỗi dòng stdin là envelope observation, `protocolVersion: "1.0"`,
`requestId`, `turnId`, `gameId`, `gameVersion`, `playerId`, `deadlineMs: 500`,
`observation`. Output: đúng một dòng JSON action, echo requestId/turnId,
`type: "action"`, `protocolVersion: "1.0"`, `action`.

Action OTT: `{"type":"MOVE","from":"d4","to":"e5"}`.
Thời gian tính cả đọc/ghi và quyết định: 500 ms. Luôn flush stdout. Dùng stderr
cho debug; không in lời chào hoặc log vào stdout. Tối đa 64 KiB/dòng stdout,
1 MiB stderr/game (replay giữ 8 KiB đầu). Timeout, crash, schema envelope sai,
nước đi sai hoặc vượt output bị xử thua, chi tiết ghi trong replay.

`random_bot.py`: PRNG chọn nước hợp lệ.
`capture_greedy.py`: ưu tiên capture, rồi gần đích; tie bằng thứ tự tọa độ.
`goal_rush.py`: khoảng cách + phạt quân địch có thể ăn ở lượt sau; đích ưu tiên tuyệt đối.
Ba bot mẫu đơn giản, không phải AI tìm kiếm tối ưu.
