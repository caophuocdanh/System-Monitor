import configparser
import os
import sys
from werkzeug.security import generate_password_hash

def set_admin_password():
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

    config = configparser.ConfigParser()
    config_path = 'config.ini'
    
    if os.path.exists(config_path):
        config.read(config_path)
    else:
        print(f"Cảnh báo: Không tìm thấy file {config_path}. Sẽ tạo file mới.")
        if 'webserver' not in config:
            config['webserver'] = {}

    if 'webserver' not in config:
        config['webserver'] = {}

    # Lưu bản băm vào config thay vì plain text
    config['webserver']['admin_password'] = hashed_password

    with open(config_path, 'w', encoding='utf-8') as configfile:
        config.write(configfile)

    print("\n[Thành công] Mật khẩu đã được băm và lưu vào config.ini.")
    print("Bản băm hiện tại: " + hashed_password)

if __name__ == "__main__":
    try:
        set_admin_password()
    except KeyboardInterrupt:
        print("\nĐã hủy.")
    except Exception as e:
        print(f"\nLỗi: {e}")
