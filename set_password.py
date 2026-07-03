import os
import sys
from werkzeug.security import generate_password_hash
from library import load_config, save_config

def set_admin_password():
    # Cấu hình encoding cho stdout/stderr để tránh lỗi Unicode trên Windows Console
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    print("--- System Monitor: Dashboard Password Setup ---")
    password = input("Nhập mật khẩu mới cho Dashboard: ").strip()
    
    if not password:
        print("Lỗi: Mật khẩu không được để trống.")
        return

    confirm_password = input("Xác nhận lại mật khẩu: ").strip()
    if password != confirm_password:
        print("Lỗi: Mật khẩu xác nhận không khớp.")
        return

    # Tạo bản băm bảo mật (Sử dụng pbkdf2:sha256 mặc định của Werkzeug)
    hashed_password = generate_password_hash(password)

    config_path = 'config.ini'
    
    is_encrypted = False
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if f.read().strip().startswith("ENC:"):
                    is_encrypted = True
        except Exception:
            pass

    config = load_config(config_path)

    if 'webserver' not in config:
        config['webserver'] = {}

    # Lưu bản băm vào config thay vì plain text
    config['webserver']['admin_password'] = hashed_password

    success = save_config(config_path, config, encrypt=is_encrypted)

    if success:
        print("\n[Thành công] Mật khẩu đã được băm và lưu vào config.ini.")
        print("Bản băm hiện tại: " + hashed_password)
    else:
        print("\nLỗi: Không thể lưu mật khẩu vào file cấu hình.")

if __name__ == "__main__":
    try:
        set_admin_password()
    except KeyboardInterrupt:
        print("\nĐã hủy.")
    except Exception as e:
        print(f"\nLỗi: {e}")
