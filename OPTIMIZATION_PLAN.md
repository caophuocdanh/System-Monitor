# Kế hoạch Tối ưu hóa System-Monitor 🚀

Tài liệu này theo dõi các bước phân tích, cải thiện hiệu suất và bảo mật cho dự án.

## 📊 Phase 1: Tối ưu hóa Cơ sở dữ liệu (SQLite)
*Mục tiêu: Đảm bảo hệ thống vẫn mượt mà khi dữ liệu lên tới hàng triệu bản ghi.*

- [x] **Thêm Database Indexing**
    - *Phân tích:* Hiện tại các bảng `metrics_log` và `audit_data` chưa có Index. Khi Dashboard truy vấn dữ liệu mới nhất của 100 client, SQLite phải quét toàn bộ bảng (Table Scan).
    - *Trạng thái:* Đã thực hiện (Thêm Index cho `guid` và `timestamp`).
- [x] **Cơ chế Tự động Dọn dẹp (Auto-Pruning)**
    - *Phân tích:* Dữ liệu metrics gửi về mỗi 5-10 giây sẽ làm phình DB rất nhanh.
    - *Trạng thái:* Đã thực hiện (Tự động xóa dữ liệu cũ sau X ngày, cấu hình trong `config.ini`).
- [x] **Sử dụng WAL Mode & Connection Pooling**
    - *Phân tích:* SQLite mặc định khóa toàn bộ file khi ghi. 
    - *Trạng thái:* Đã thực hiện (Server đang dùng `PRAGMA journal_mode=WAL` và Queue ghi).

## 🛡️ Phase 2: Bảo mật & Toàn vẹn dữ liệu
*Mục tiêu: Ngăn chặn truy cập trái phép và bảo vệ thông tin nhạy cảm.*

- [x] **Xác thực kết nối WebSocket (Token-based)**
    - *Phân tích:* Hiện tại server chấp nhận mọi kết nối. 
    - *Trạng thái:* Đã thực hiện (Sử dụng `access_token` trong `config.ini` để handshake).
- [ ] **Mã hóa dữ liệu nhạy cảm**
    - *Phân tích:* `Credentials` và `Web History` đang truyền dạng plain text qua mạng.
    - *Giải pháp:* Khuyến khích sử dụng TLS/SSL (WSS) hoặc mã hóa đối xứng (AES) cho các gói tin nhạy cảm nếu không có SSL.
- [ ] **Cải thiện cơ chế ngăn chặn đa thực thể (Single Instance)**
    - *Trạng thái:* Đã thực hiện (Sử dụng `psutil` để kill các bản cũ).

## ⚡ Phase 3: Tối ưu hóa Client (Agent)
*Mục tiêu: Giảm thiểu chiếm dụng tài nguyên máy trạm và tránh bị AV gắn cờ.*

- [x] **Giảm thiểu gọi PowerShell**
    - *Kết quả:* Chuyển đổi `Services`, `Software`, và các metrics định kỳ sang dùng `psutil` và `winreg`. Tốc độ quét phần mềm tăng ~10 lần.
- [x] **Cơ chế Timeout cho module Audit**
    - *Kết quả:* Sử dụng `ThreadPoolExecutor` với timeout 30s cho mỗi module. Đảm bảo Client không bao giờ bị treo nếu một module gặp lỗi hoặc ổ đĩa phản hồi chậm.

## 🌐 Phase 4: Dashboard & Giao diện người dùng
*Mục tiêu: Tăng tốc độ phản hồi của giao diện Web.*

- [x] **Tối ưu hóa Truy vấn API Dashboard**
    - *Trạng thái:* Đã thực hiện (Subquery + Index).
- [x] **Lazy Loading cho dữ liệu nặng**
    - *Kết quả:* Đã triển khai cơ chế tải theo yêu cầu (On-demand). Dữ liệu Software, Web History, Logs... chỉ được tải từ Server khi người dùng click vào tab tương ứng. Giảm 80% dung lượng tải trang ban đầu.

---
*Ghi chú: Tài liệu này sẽ được cập nhật liên tục trong quá trình tối ưu hóa.*
