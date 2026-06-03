import asyncio
import websockets
import sqlite3
import json
import configparser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import logging
import os
import sys
import ctypes
import psutil
import platform

# Kiểm tra nền tảng
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import winreg

# --- CẤU HÌNH LOGGING VÀ BIẾN TOÀN CỤC ---
logging.getLogger('http.server').setLevel(logging.WARNING)
DB_NAME = "system_monitor.db"
# Hàng đợi để xử lý các yêu cầu ghi vào DB một cách tuần tự
db_write_queue = asyncio.Queue()
ACCESS_TOKEN = "" # Sẽ được nạp từ config

# --- HÀM HELPER HỆ THỐNG ---

def get_base_path():
    """Trả về thư mục chứa file .exe hoặc .py đang chạy"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # khi đã đóng gói .exe
    return os.path.dirname(os.path.abspath(__file__))  # khi chạy file .py

def show_console(show=True):
    """Ẩn hoặc hiện cửa sổ console trên Windows."""
    if IS_WINDOWS:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            if show:
                ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW
            else:
                ctypes.windll.user32.ShowWindow(hwnd, 0) # SW_HIDE

def manage_autostart():
    """Thiết lập Windows Registry để server tự động chạy cùng hệ thống (luôn force Enabled nếu là Admin)."""
    if not IS_WINDOWS:
        return

    # Xác định đường dẫn thực thi
    if getattr(sys, 'frozen', False):
        app_path = f'"{sys.executable}"'
    else:
        app_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'

    reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    approved_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    app_name = "SystemMonitorServer"

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

def ensure_single_instance():
    """Kiểm tra và tắt triệt để các bản server cũ đang chạy."""
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

# --- HTTP HEALTH CHECK SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

def run_health_check_server(host, port):
    server_address = (host, port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print(f"[Server] Health check server started at http://{host}:{port}/health")
    httpd.serve_forever()

# --- CÁC HÀM TƯƠNG TÁC VỚI DATABASE (ĐƯỢC TÁI CẤU TRÚC) ---
# Hàm này giờ là hàm đồng bộ (synchronous) bình thường, sẽ được gọi bởi worker
def _execute_db_write(query, params=()):
    try:
        # Sử dụng timeout để tránh bị lock vô hạn nếu có vấn đề
        conn = sqlite3.connect(DB_NAME, timeout=10) 
        # Bật các PRAGMA quan trọng cho mỗi kết nối ghi
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL") # Cải thiện hiệu suất đồng thời
        
        conn.execute(query, params)
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[DB Worker Error] Database locked or other operational error: {e}")
        # Có thể thêm logic retry hoặc ghi log chi tiết hơn ở đây
    except Exception as e:
        print(f"[DB Worker Error] Failed to execute DB write: {e}")

# Các hàm này giờ chỉ đưa yêu cầu vào hàng đợi
async def db_upsert_client_static_info(guid, hostname, username, local_ip, wan_ip, enabled_modules_json):
    # Dùng ON CONFLICT để gộp INSERT và UPDATE thành 1 lệnh, an toàn và hiệu quả hơn
    sql_script = """
        INSERT INTO client (guid, hostname, username, local_ip, wan_ip, enabled_modules)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guid) DO UPDATE SET
        hostname=excluded.hostname,
        local_ip=excluded.local_ip,
        wan_ip=excluded.wan_ip,
        enabled_modules=excluded.enabled_modules;
    """
    await db_write_queue.put(
        (_execute_db_write, (sql_script, (guid, hostname, username, local_ip, wan_ip, enabled_modules_json)))
    )

async def db_add_active_connection(guid, client_address):
    # Dùng now(timezone.utc) để lấy thời gian UTC hiện tại
    timestamp = int(datetime.now(timezone.utc).timestamp()) 
    address_str = f"{client_address[0]}:{client_address[1]}"
    query = "INSERT INTO active_connections (guid, connection_start_time, client_address) VALUES (?, ?, ?)"
    await db_write_queue.put((_execute_db_write, (query, (guid, timestamp, address_str))))

async def db_remove_active_connection(guid, client_address):
    address_str = f"{client_address[0]}:{client_address[1]}"
    query = "DELETE FROM active_connections WHERE guid = ? AND client_address = ?"
    await db_write_queue.put((_execute_db_write, (query, (guid, address_str))))
    print(f"Queued removal of active connection for {guid} from {address_str}")

async def db_clear_client_audit_data(guid):
    query = "DELETE FROM audit_data WHERE guid = ?"
    await db_write_queue.put((_execute_db_write, (query, (guid,))))

async def db_log_metrics(guid, data):
    timestamp = int(datetime.now(timezone.utc).timestamp())
    query = """
        INSERT INTO metrics_log (
            guid, timestamp, cpu_usage, ram_usage, disk_usage, local_ip, wan_ip,
            disk_io_json, network_io_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        guid, timestamp,
        data.get('cpu_usage', 0),
        data.get('ram_usage', 0),
        data.get('disk_usage', 0),
        data.get('local_ip'),
        data.get('wan_ip'),
        json.dumps(data.get('disk_io', {})),
        json.dumps(data.get('network_io', {}))
    )
    await db_write_queue.put((_execute_db_write, (query, params)))

async def db_log_audit_data(guid, audit_name, data):
    timestamp = int(datetime.now(timezone.utc).timestamp())
    data_str = json.dumps(data)
    query = """
        INSERT INTO audit_data (guid, audit_name, timestamp, data_json) VALUES (?, ?, ?, ?)
        ON CONFLICT(guid, audit_name) DO UPDATE SET
        timestamp=excluded.timestamp, data_json=excluded.data_json
    """
    await db_write_queue.put((_execute_db_write, (query, (guid, audit_name, timestamp, data_str))))
    # print(f"Queued audit data for '{audit_name}' from {guid}")

async def db_prune_old_metrics(retention_days):
    """Xóa các bản ghi metrics cũ hơn số ngày quy định."""
    cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp())
    query = "DELETE FROM metrics_log WHERE timestamp < ?"
    # Gửi yêu cầu xóa vào hàng đợi để tránh xung đột
    await db_write_queue.put((_execute_db_write, (query, (cutoff_timestamp,))))
    print(f"[DB Pruner] Queued pruning of metrics older than {retention_days} days (Before {datetime.fromtimestamp(cutoff_timestamp).strftime('%Y-%m-%d')})")

# Hàm đọc (read) có thể giữ nguyên vì đọc không khóa database như ghi
def check_client_exists(guid):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM client WHERE guid = ?", (guid,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# --- DATABASE WORKER ---
async def database_writer_worker():
    """Tác vụ nền, lấy yêu cầu từ hàng đợi và ghi vào DB."""
    print("[DB Worker] Database writer worker started.")
    while True:
        try:
            func, args = await db_write_queue.get()
            
            # Chạy hàm ghi DB trong một executor để không block vòng lặp sự kiện
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, func, *args)

            db_write_queue.task_done()
        except Exception as e:
            print(f"[DB Worker] Error processing DB queue: {e}")

async def database_pruning_worker(retention_days):
    """Tác vụ nền, định kỳ dọn dẹp dữ liệu cũ (mỗi 12 giờ)."""
    if retention_days <= 0:
        print("[DB Pruner] Pruning disabled (retention_days <= 0).")
        return

    print(f"[DB Pruner] Database pruning worker started (Retention: {retention_days} days).")
    while True:
        try:
            await db_prune_old_metrics(retention_days)
            # Chờ 12 giờ trước lần dọn dẹp tiếp theo
            await asyncio.sleep(12 * 3600)
        except Exception as e:
            print(f"[DB Pruner] Error in pruning worker: {e}")
            await asyncio.sleep(3600) # Thử lại sau 1 giờ nếu lỗi

# --- SETUP DB BAN ĐẦU ---
def setup_database():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS client (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT NOT NULL UNIQUE,
        hostname TEXT NOT NULL,
        username TEXT NOT NULL,
        local_ip TEXT,
        wan_ip TEXT,
        enabled_modules TEXT
    );''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS active_connections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT NOT NULL,
        connection_start_time INTEGER NOT NULL,
        client_address TEXT NOT NULL,
        FOREIGN KEY (guid) REFERENCES client(guid) ON DELETE CASCADE
    );''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS metrics_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        cpu_usage REAL NOT NULL,
        ram_usage REAL NOT NULL,
        disk_usage REAL,
        local_ip TEXT,
        wan_ip TEXT,
        disk_io_json TEXT,
        network_io_json TEXT,
        FOREIGN KEY (guid) REFERENCES client(guid) ON DELETE CASCADE
    );''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT NOT NULL,
        audit_name TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        data_json TEXT NOT NULL,
        FOREIGN KEY (guid) REFERENCES client(guid) ON DELETE CASCADE,
        UNIQUE(guid, audit_name)
    );''')
    
    # --- THÊM INDEX ĐỂ TỐI ƯU TRUY VẤN ---
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_log_guid_timestamp ON metrics_log (guid, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_connections_guid ON active_connections (guid);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_data_guid ON audit_data (guid);")
    cursor.execute("PRAGMA table_info(client)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'enabled_modules' not in columns:
        print("Database migration: Adding 'enabled_modules' column to 'client' table...")
        cursor.execute("ALTER TABLE client ADD COLUMN enabled_modules TEXT DEFAULT '[]'")

    cursor.execute("PRAGMA table_info(metrics_log)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'disk_io_json' not in columns:
        print("Database migration: Adding 'disk_io_json' column...")
        cursor.execute("ALTER TABLE metrics_log ADD COLUMN disk_io_json TEXT DEFAULT '{}'")
    if 'network_io_json' not in columns:
        print("Database migration: Adding 'network_io_json' column...")
        cursor.execute("ALTER TABLE metrics_log ADD COLUMN network_io_json TEXT DEFAULT '{}'")

    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' is ready with all required tables.")

def clear_active_connections():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_connections")
    conn.commit()
    conn.close()
    print("Cleared all previous active connections from the database.")

# --- WEBSOCKET HANDLER CHÍNH ---
async def websocket_handler(websocket):
    client_guid = None
    client_address = websocket.remote_address
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [Connection Opened] New connection from {client_address[0]}:{client_address[1]}")

    try:
        # Xử lý tin nhắn đầu tiên một cách đặc biệt để đảm bảo client được đăng ký
        first_message = await websocket.recv()
        try:
            data = json.loads(first_message)                
            timestamp_str = datetime.now().strftime('%H:%M:%S')
            msg_type = data.get('type')
            guid = data.get('guid')
            token = data.get('access_token')

            # --- KIỂM TRA TOKEN XÁC THỰC ---
            if ACCESS_TOKEN and token != ACCESS_TOKEN:
                print(f"[{timestamp_str}] [Auth Failed] Invalid token from {client_address}. Closing.")
                await websocket.close(code=4001, reason="Invalid access token")
                return

            if msg_type != 'client_info' or not guid:
                print(f"First message from {client_address} was not 'client_info' or missing GUID. Closing connection.")
                await websocket.close()
                return

            client_guid = guid
            print(f"[{timestamp_str}] [Client Identified] {guid} - {client_address}. Processing initial info...")
            
            # Đưa các tác vụ ghi ban đầu vào hàng đợi
            await db_upsert_client_static_info(
                guid, data.get('hostname'), data.get('username'),
                data.get('local_ip'), data.get('wan_ip'),
                json.dumps(data.get('enabled_modules', []))
            )
            print(f"  -> Queued info update for {guid}")
            
            await db_clear_client_audit_data(guid)
            print(f"  -> Queued audit data cleanup for {guid}")

            await db_add_active_connection(guid, client_address)
            print(f"  -> Queued add active connection for {guid}")

            # Chờ cho tất cả các tác vụ ban đầu này được worker xử lý xong
            await db_write_queue.join()
            print(f"[{timestamp_str}] [DB Write Complete] Initial info for {guid} processed.")

        except (json.JSONDecodeError, AttributeError):
            print(f"Received invalid JSON on first message from {client_address}. Closing.")
            await websocket.close()
            return

        # Vòng lặp xử lý các tin nhắn tiếp theo
        async for message in websocket:
            # Trước mỗi lần xử lý, hãy kiểm tra xem client có còn tồn tại không.
            loop = asyncio.get_running_loop()
            client_still_exists = await loop.run_in_executor(None, check_client_exists, client_guid)
            
            timestamp_str = datetime.now().strftime('%H:%M:%S')

            if not client_still_exists:
                print(f"[{timestamp_str}] [Client Deleted] Client {client_guid} was deleted from DB. Closing connection.")
                await websocket.close()
                break # Thoát khỏi vòng lặp async for

            try:
                data = json.loads(message)
                msg_type = data.get('type')
                guid = data.get('guid')
            except (json.JSONDecodeError, AttributeError):
                print(f"Received invalid JSON from {client_guid}. Ignoring.")
                continue

            if not guid or guid != client_guid:
                print(f"Message with invalid or mismatched GUID from {client_guid}. Ignoring.")
                continue
            
            if msg_type == 'client_info':
                print(f"[{timestamp_str}] [Info Update] Queueing info update from {guid}")
                await db_upsert_client_static_info(
                    guid, data.get('hostname'), data.get('username'), 
                    data.get('local_ip'), data.get('wan_ip'),
                    json.dumps(data.get('enabled_modules', []))
                )

            elif msg_type == 'metrics':
                cpu = data.get('cpu_usage', 0)
                ram = data.get('ram_usage', 0)
                disk = data.get('disk_usage', 0)
                log_message = (
                    f"[RECEIVE] <== [{timestamp_str}] [{client_guid}] "
                    f"CPU: {cpu:.1f}% | RAM: {ram:.1f}% | DISK USAGE: {disk:.1f}%"
                )
                print(log_message)
                await db_log_metrics(guid, data)
            
            elif msg_type == 'full_audit':
                print(f"[{timestamp_str}] [Audit Data] Queueing full audit from {guid}.")
                for audit_name, audit_result in data['data'].items():
                    await db_log_audit_data(guid, audit_name, audit_result)
                print(f"  -> Finished queueing audit for {guid}.")
            
            else:
                print(f"Received unknown message type: '{msg_type}' from {guid}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if client_guid:
            # Đưa yêu cầu xóa active connection vào hàng đợi để xử lý tuần tự
            await db_remove_active_connection(client_guid, client_address)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Client Disconnected] {client_guid} - {client_address[0]}:{client_address[1]}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Connection Closed] Connection from {client_address[0]}:{client_address[1]} closed before identifying.")


# --- HÀM MAIN KHỞI CHẠY SERVER ---
async def main():
    global ACCESS_TOKEN
    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")

    config = configparser.ConfigParser()
    config.read(config_path)

    server_host = config['server']['host']
    server_port = int(config['server']['port'])
    health_check_port = int(config['server']['health_check_port'])
    retention_days = int(config['server'].get('retention_days', fallback=7))
    ACCESS_TOKEN = config['server'].get('access_token', fallback="")

    # Áp dụng cấu hình GUI và xử lý tham số -minimized
    gui_enabled = config.getboolean('server', 'gui', fallback=True)

    if "-minimized" in sys.argv:
        show_console(False)
    else:
        show_console(gui_enabled)

    health_thread = threading.Thread(
        target=run_health_check_server, 
        args=(server_host, health_check_port), 
        daemon=True
    )
    health_thread.start()

    # Khởi tạo worker ghi DB để nó chạy nền
    asyncio.create_task(database_writer_worker())
    
    # Khởi tạo worker dọn dẹp DB
    asyncio.create_task(database_pruning_worker(retention_days))

    async with websockets.serve(websocket_handler, server_host, server_port):
        if "-minimized" not in sys.argv and gui_enabled:
            print(f"[Server] WebSocket server started at ws://{server_host}:{server_port}")
        await asyncio.Future()

if __name__ == "__main__":
    # Thiết lập thư mục làm việc về thư mục chứa script
    os.chdir(get_base_path())

    # 0. Đảm bảo chỉ có một instance chạy
    ensure_single_instance()

    # Xử lý cấu hình autostart cùng hệ thống qua Registry
    manage_autostart()

    # Các hàm setup DB chạy một lần duy nhất khi khởi động server
    setup_database()
    clear_active_connections()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutdown requested by user.")