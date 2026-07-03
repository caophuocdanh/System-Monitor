import sys
import os
from library import load_config, save_config

def main():
    # Cấu hình encoding cho stdout/stderr để tránh lỗi Unicode trên Windows Console
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    if len(sys.argv) < 2 or sys.argv[1] not in ['encrypt', 'decrypt']:
        print("Cách sử dụng:")
        print("  python encrypt_config.py encrypt [đường_dẫn_file]")
        print("  python encrypt_config.py decrypt [đường_dẫn_file]")
        sys.exit(1)

    action = sys.argv[1]
    file_path = sys.argv[2] if len(sys.argv) > 2 else "config.ini"

    if not os.path.exists(file_path):
        print(f"Lỗi: Không tìm thấy file '{file_path}'")
        sys.exit(1)

    print(f"Đang đọc file '{file_path}'...")
    config = load_config(file_path)

    if not config.sections():
        print("Cảnh báo: File cấu hình trống hoặc định dạng không đúng.")

    encrypt = (action == 'encrypt')
    print(f"Đang thực hiện {'mã hóa' if encrypt else 'giải mã'} và ghi vào '{file_path}'...")
    success = save_config(file_path, config, encrypt=encrypt)

    if success:
        print(f"Thành công! File '{file_path}' đã được {'mã hóa' if encrypt else 'giải mã'}.")
    else:
        print("Thất bại trong việc lưu cấu hình.")

if __name__ == "__main__":
    main()
