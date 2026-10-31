# 🗂️ Thư mục Phân phối `source/` - System Monitor

Thư mục này chứa toàn bộ các tệp thực thi độc lập (.exe), cấu hình và tài nguyên giao diện đã được đóng gói sẵn sàng để triển khai thực tế.

---

## 📦 Cấu trúc và Thành phần

### 1. Thư mục gốc `source/`
- ⚙️ **Config Editor.exe**: Công cụ giao diện đồ họa (GUI) để xem và chỉnh sửa an toàn tệp cấu hình mã hóa `config.ini`.
- ❌ **kill_all.bat**: Kịch bản tắt nhanh toàn bộ các tiến trình liên quan đến System Monitor trên máy (`SM Server`, `SM Dashboard`, `smchost`, `Config Editor`...).
- ▶️ **run_server.bat**: Kịch bản một click khởi động nhanh cả **SM Server** và **SM Dashboard**.

### 2. Thư mục Máy chủ `source/server/`
- 🖥️ **SM Server.exe**: WebSocket Server lõi (cổng `9630`, health check cổng `7410`). Tiếp nhận metrics, xử lý kiểm toán và điều khiển máy trạm.
- 🌐 **SM Dashboard.exe**: Web Dashboard nền Flask (cổng `43210`). Cung cấp cổng quản trị đồ họa, biểu đồ thời gian thực, File Manager và Remote Terminal.
- ⚙️ **config.ini**: Tệp cấu hình của máy chủ.
- 🗄️ **system_monitor.db**: Cơ sở dữ liệu SQLite lưu trữ dữ liệu tập trung.
- 📁 **templates/** & **static/**: Tài nguyên giao diện Web Dashboard và thư mục chứa gói cập nhật `static/updates/client_setup.exe`.

### 3. Thư mục Máy trạm `source/client/`
- 🚀 **client_setup.exe**: Bộ cài đặt tự động ngầm (Silent Installer) tích hợp sẵn `smchost.exe` và `config.ini`. Nhấp đúp chạy để tự động cài đặt vào `C:\Users\Public\SystemMonitor`, cấu hình Registry Startup và khởi chạy ngầm.
- ⚙️ **smchost.exe**: Tệp thực thi Agent máy trạm độc lập.
- 📄 **config.ini**: Tệp cấu hình trỏ về địa chỉ IP của máy chủ.

---

## 🚀 Hướng dẫn Vận hành Nhanh

### Vận hành Máy chủ:
1. Đảm bảo cấu hình đúng IP và Port trong `server/config.ini`.
2. Chạy `run_server.bat` (hoặc mở `server/SM Server.exe` rồi mở `server/SM Dashboard.exe`).
3. Mở trình duyệt web truy cập: `http://<IP_MAY_CHU>:43210`.

### Vận hành Máy trạm:
- Sao chép tệp `client/client_setup.exe` sang máy trạm cần giám sát và nhấp đúp chạy.
- Máy trạm sẽ tự động kết nối về máy chủ và xuất hiện tức thì trên Dashboard.

---
<p align="center"><i>System Monitor - Giải pháp giám sát Windows tập trung từ xa.</i></p>
