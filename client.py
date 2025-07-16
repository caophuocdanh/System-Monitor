import os
import sys
import asyncio
import websockets
import socket
import json
import configparser
import platform
import hashlib
from library import WindowsAuditor
import time # Import time để đo thời gian

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

# --- Các biến toàn cục ---
CLIENT_GUID = get_machine_id()
HOSTNAME = socket.gethostname()
USERNAME = HOSTNAME

# --- Logic Audit được viết lại ---

def run_full_audit_sync():
    """
    Chạy các module audit được cấu hình trong config.ini.
    Hàm này là synchronous (blocking).
    """
    print("\n[AUDIT] Starting configured system audit...")
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

    auditor = WindowsAuditor(max_events=max_event_log, history_limit_per_profile=history_limit)
    all_results = {}
    
    for name in enabled_modules:
        if name in auditor.auditors:
            try:
                print(f"[AUDIT] Running '{name}' module...")
                result = auditor.auditors[name].get_details()
                all_results[name] = result
            except Exception as e:
                all_results[name] = {"Error": f"Audit module '{name}' failed: {e}"}
    
    end_time = time.time()
    print(f"[AUDIT] Configured system audit completed in {end_time - start_time:.2f} seconds.")
    return all_results

# --- Các tác vụ gửi tin được viết lại ---

# FILE: client.py

async def send_metrics(websocket):
    """Gửi các chỉ số hiệu năng (CPU, RAM, Disk, và I/O chi tiết) định kỳ."""
    config = configparser.ConfigParser()
    config.read('config.ini')
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
            
    except asyncio.CancelledError:
        print("Metrics sending task cancelled.")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Metrics sending task: An unexpected error occurred: {e}")

async def send_updated_audit_and_info(websocket, initial_audit_data):
    """
    Tác vụ chạy nền để gửi lại thông tin và dữ liệu audit định kỳ.
    Nó sẽ gửi dữ liệu ban đầu ngay lập tức, sau đó lặp lại.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    update_interval = int(config['client']['update_info_interval'])
    
    # Sử dụng dữ liệu audit đã có từ trước cho lần gửi đầu tiên
    current_audit_data = initial_audit_data
    
    try:
        while True:
            # 1. Chuẩn bị gói tin info
            local_ip = WindowsAuditor._Ip.get_local_ip()
            wan_ip = WindowsAuditor._Ip.get_wan_ip()
            enabled_modules = get_enabled_modules_from_config()
            info = {
                "type": "client_info", "guid": CLIENT_GUID, "hostname": HOSTNAME,
                "username": USERNAME, "local_ip": local_ip, "wan_ip": wan_ip,
                "enabled_modules": enabled_modules
            }
            
            # 2. Chuẩn bị gói tin audit
            audit_report = {
                "type": "full_audit", "guid": CLIENT_GUID, "data": current_audit_data
            }
            
            # 3. Gửi cả hai gói tin
            await websocket.send(json.dumps(info))
            print(f"\n[SEND] => Sent client info update.")
            if current_audit_data:
                await websocket.send(json.dumps(audit_report))
                print("[SEND] => Sent full audit report.")

            # 4. Chờ cho lần cập nhật tiếp theo
            print(f"       Next info/audit update in {update_interval} seconds.\n")
            await asyncio.sleep(update_interval)

            # 5. Chạy lại audit để lấy dữ liệu mới cho lần lặp tiếp theo
            loop = asyncio.get_running_loop()
            current_audit_data = await loop.run_in_executor(None, run_full_audit_sync)

    except asyncio.CancelledError:
        print("Info/Audit sending task cancelled.")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Info/Audit sending task: An unexpected error occurred: {e}")


# --- Vòng lặp kết nối chính ---
async def connect(initial_audit_data):
    """
    Vòng lặp chính để kết nối và quản lý các tác vụ của client.
    Nhận dữ liệu audit ban đầu làm tham số.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    server_host = config['client']['server']
    server_port = int(config['server']['port'])
    retry_interval = int(config['client']['retry_interval'])
    uri = f"ws://{server_host}:{server_port}"
    
    while True:
        try:
            print(f"Attempting to connect to {uri}...")
            async with websockets.connect(uri) as websocket:
                print(f"Connection successful!")
                
                # Bắt đầu 2 tác vụ chạy song song
                # Tác vụ info/audit sẽ gửi dữ liệu ban đầu ngay lập tức
                info_audit_task = asyncio.create_task(send_updated_audit_and_info(websocket, initial_audit_data))
                metrics_task = asyncio.create_task(send_metrics(websocket))
                
                # Chờ cho đến khi một trong các tác vụ kết thúc
                done, pending = await asyncio.wait(
                    [info_audit_task, metrics_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                
                # Hủy các tác vụ còn lại
                for task in pending:
                    task.cancel()

        except ConnectionRefusedError:
            print(f"Connection refused. Retrying in {retry_interval} seconds...")
        except websockets.exceptions.ConnectionClosed:
            print(f"Connection closed. Retrying in {retry_interval} seconds...")
        except KeyboardInterrupt:
            print("Client disconnected by user.")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}. Retrying in {retry_interval} seconds...")

        await asyncio.sleep(retry_interval)


if __name__ == "__main__":
    if platform.system() != "Windows":
        print("Warning: This client is designed for Windows and may have limited functionality on other OS.")
    
    # 1. Chạy audit trước khi làm bất cứ điều gì khác
    # Đây là một lời gọi blocking, chương trình sẽ chờ ở đây
    initial_audit_results = run_full_audit_sync()

    # 2. Sau khi audit xong, bắt đầu vòng lặp kết nối và truyền dữ liệu audit vào
    try:
        asyncio.run(connect(initial_audit_results))
    except KeyboardInterrupt:
        print("\nClient shutdown.")