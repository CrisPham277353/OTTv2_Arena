# Nghiệm thu luật OTT v2 1.1.0 – 12/10/2026

- Engine 1.0 + 1.1 + runner: 69 test pass.
- Bộ đầy đủ: **88 passed, 1 warning in 11.33s**. Warning deprecation của
  Starlette TestClient/httpx như các bản trước; không có test fail.
- Python compileall và JavaScript syntax check: pass.
- Các ca mới: ăn quân cuối A/B, thứ tự goal/army/type, reset capture/tiến gần đích,
  không tính lùi/quay lại là tiến độ, ranh giới 14/15 lượt riêng, 49/50 lượt chung,
  thế bí ưu tiên, repetition ưu tiên, giới hạn 300 sau capture, action sai không
  đổi counters, snapshot/observation không alias counters, fixture và playouts.
- Registry: chọn default từ manifest, 1.0 vẫn truy cập được qua version explicit.
  API: trận mặc định 1.1 và trận legacy 1.0; bot đã ghim 1.0 không bị chạy ngầm
  bằng 1.1, vẫn thi đấu được khi chọn 1.0.
- Browser: mặc định 1.1, hiện counters 0/50 và A/B 0/15; chọn 1.0 lọc được bot cũ
  và ẩn pressure. Trận Random vs Random seed42 kết thúc 37 plies, A chạm 15 lượt
  riêng không tiến bộ, B thắng NO_PROGRESS; replay/nhãn kết quả/counters đồng nhất.
- Smoke HTTP thật BO3 với luật mặc định 1.1: PASS, Capture Greedy thắng 2–0,
  hai game 23 và 26 plies; trạng thái/replay/history/stats đều đọc được.
- Console browser kiểm tra không có error/warn. Ảnh: rules-1.1-proof.jpg.
- Renderer 1.1 có URL gắn version để tránh browser giữ renderer cũ thiếu counters.

Chọn giữ cả điều kiện xóa loại và hết quân theo trả lời của người dùng. Trong bàn
chuẩn, xóa một loại có thể kết thúc trận trước khi ăn hết toàn bộ quân. Điều kiện
army có ưu tiên khi cả hai đồng thời đúng. Không có DRAW ở bản cũ hoặc bản mới.

Ngưỡng 15 lượt riêng phạt cả tái bố trí kéo dài; cần benchmark nhiều chiến thuật
trước giải chính thức. Không thay gameplay của replay/match/bot version cũ.
