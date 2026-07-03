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
from library import WindowsAuditor, load_config

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

# Lưu trữ các kết nối WebSocket đang hoạt động
# { guid: websocket }
agent_connections = {}
# { guid: set(websocket) }
dashboard_connections = {}
# Lưu trữ kết nối Dashboard nhận sự kiện toàn hệ thống
global_dashboards = set()
# Trạng thái cảnh báo của từng client
client_alert_status = {} # { guid: { "cpu": 0, "ram": 0, "disk": 0 } }
# Cache thông tin client
client_info_cache = {} # { guid: { "hostname": hostname, "username": username } }

async def broadcast_to_global_dashboards(message):
    message_str = json.dumps(message)
    for ws in list(global_dashboards):
        try:
            await ws.send(message_str)
        except Exception:
            global_dashboards.discard(ws)

async def db_log_system_event(guid, event_type, message):
    import time
    timestamp = int(time.time())
    query = "INSERT INTO system_logs (guid, event_type, message, timestamp) VALUES (?, ?, ?, ?)"
    await db_write_queue.put((query, (guid, event_type, message, timestamp)))

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
    try:
        server_address = (host, port)
        httpd = HTTPServer(server_address, HealthCheckHandler)
        print(f"[Server] Health check server started at http://{host}:{port}/health")
        httpd.serve_forever()
    except Exception as e:
        print(f"[Server] Health check server failed to start: {e}")

# --- CÁC HÀM TƯƠNG TÁC VỚI DATABASE (ĐƯỢC TÁI CẤU TRÚC) ---

# Các hàm này giờ chỉ đưa yêu cầu vào hàng đợi dưới dạng (query, params)
async def db_upsert_client_static_info(guid, hostname, username, local_ip, wan_ip, enabled_modules_json):
    sql_script = """
        INSERT INTO client (guid, hostname, username, local_ip, wan_ip, enabled_modules)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guid) DO UPDATE SET
        hostname=excluded.hostname,
        local_ip=excluded.local_ip,
        wan_ip=excluded.wan_ip,
        enabled_modules=excluded.enabled_modules;
    """
    await db_write_queue.put((sql_script, (guid, hostname, username, local_ip, wan_ip, enabled_modules_json)))

async def db_add_active_connection(guid, client_address):
    timestamp = int(datetime.now(timezone.utc).timestamp()) 
    address_str = f"{client_address[0]}:{client_address[1]}"
    query = "INSERT INTO active_connections (guid, connection_start_time, client_address) VALUES (?, ?, ?)"
    await db_write_queue.put((query, (guid, timestamp, address_str)))

async def db_remove_active_connection(guid, client_address):
    address_str = f"{client_address[0]}:{client_address[1]}"
    query = "DELETE FROM active_connections WHERE guid = ? AND client_address = ?"
    await db_write_queue.put((query, (guid, address_str)))
    print(f"Queued removal of active connection for {guid} from {address_str}")

async def db_clear_client_audit_data(guid):
    query = "DELETE FROM audit_data WHERE guid = ?"
    await db_write_queue.put((query, (guid,)))

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
    await db_write_queue.put((query, params))

async def db_log_audit_data(guid, audit_name, data):
    timestamp = int(datetime.now(timezone.utc).timestamp())
    data_str = json.dumps(data)
    query = """
        INSERT INTO audit_data (guid, audit_name, timestamp, data_json) VALUES (?, ?, ?, ?)
        ON CONFLICT(guid, audit_name) DO UPDATE SET
        timestamp=excluded.timestamp, data_json=excluded.data_json
    """
    await db_write_queue.put((query, (guid, audit_name, timestamp, data_str)))

async def db_prune_old_metrics(retention_days):
    """Xóa các bản ghi metrics cũ hơn số ngày quy định."""
    from datetime import timedelta
    cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp())
    query = "DELETE FROM metrics_log WHERE timestamp < ?"
    await db_write_queue.put((query, (cutoff_timestamp,)))
    print(f"[DB Pruner] Queued pruning of metrics older than {retention_days} days.")

# Hàm đọc (read) có thể giữ nguyên vì đọc không khóa database như ghi
def check_client_exists(guid):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM client WHERE guid = ?", (guid,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception: return False

# --- DATABASE WORKER ---
async def database_writer_worker():
    """Tác vụ nền, duy trì một kết nối duy nhất để ghi vào DB hiệu quả hơn."""
    print("[DB Worker] Database writer worker started with persistent connection.")
    
    try:
        # Mở kết nối duy nhất cho toàn bộ vòng đời của worker
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        
        while True:
            query, params = await db_write_queue.get()
            try:
                conn.execute(query, params)
                conn.commit()
            except sqlite3.OperationalError as e:
                print(f"[DB Worker Error] Operational error: {e}")
                if "locked" in str(e).lower():
                    await asyncio.sleep(0.2)
                    # Retry once for locked db
                    try: conn.execute(query, params); conn.commit()
                    except: pass
            except Exception as e:
                print(f"[DB Worker Error] Write failed: {e}")
            finally:
                db_write_queue.task_done()
    except Exception as e:
        print(f"[DB Worker] Fatal error: {e}")

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

def downsample_metrics_data(retention_hours=24):
    """Gộp dữ liệu metrics cũ hơn retention_hours thành dữ liệu trung bình theo giờ."""
    import sqlite3
    import time
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Mốc thời gian: cũ hơn retention_hours trước
        cutoff = int(time.time()) - retention_hours * 3600
        
        cursor = conn.cursor()
        
        # Bắt đầu transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. Tìm các nhóm (guid, hour) cũ hơn cutoff mà có nhiều hơn 1 bản ghi
        cursor.execute("""
            SELECT guid, (timestamp / 3600) * 3600 AS hour_ts, COUNT(*)
            FROM metrics_log
            WHERE timestamp < ?
            GROUP BY guid, (timestamp / 3600) * 3600
            HAVING COUNT(*) > 1
        """, (cutoff,))
        groups = cursor.fetchall()
        
        if not groups:
            cursor.execute("COMMIT")
            return 0
            
        downsampled_count = 0
        for guid, hour_ts, count in groups:
            # 2. Tính trung bình cộng của các cột cho nhóm này
            cursor.execute("""
                SELECT 
                    AVG(cpu_usage), AVG(ram_usage), AVG(disk_usage),
                    MAX(local_ip), MAX(wan_ip)
                FROM metrics_log
                WHERE guid = ? AND (timestamp / 3600) * 3600 = ?
            """, (guid, hour_ts))
            avg_cpu, avg_ram, avg_disk, local_ip, wan_ip = cursor.fetchone()
            
            # Lấy disk_io_json và network_io_json của bản ghi cuối cùng trong giờ đó
            cursor.execute("""
                SELECT disk_io_json, network_io_json
                FROM metrics_log
                WHERE guid = ? AND (timestamp / 3600) * 3600 = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (guid, hour_ts))
            row = cursor.fetchone()
            disk_io = row[0] if row else '{}'
            net_io = row[1] if row else '{}'
            
            # 3. Xóa tất cả bản ghi chi tiết của nhóm này
            cursor.execute("""
                DELETE FROM metrics_log
                WHERE guid = ? AND (timestamp / 3600) * 3600 = ?
            """, (guid, hour_ts))
            
            # 4. Chèn bản ghi đã được downsample vào
            cursor.execute("""
                INSERT INTO metrics_log 
                (guid, timestamp, cpu_usage, ram_usage, disk_usage, local_ip, wan_ip, disk_io_json, network_io_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (guid, hour_ts, avg_cpu, avg_ram, avg_disk, local_ip, wan_ip, disk_io, net_io))
            
            downsampled_count += count
            
        cursor.execute("COMMIT")
        print(f"[DB Downsampler] Compressed {downsampled_count} rows into {len(groups)} hourly averages.")
        return len(groups)
        
    except Exception as e:
        if conn:
            try: conn.execute("ROLLBACK")
            except: pass
        print(f"[DB Downsampler Error] Downsampling failed: {e}")
        return 0
    finally:
        if conn:
            conn.close()

async def database_downsampling_worker():
    """Tác vụ nền, định kỳ gộp dữ liệu metrics cũ (mỗi 1 giờ)."""
    print("[DB Downsampler] Database downsampling worker started (Interval: 1 hour).")
    while True:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, downsample_metrics_data, 24)
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"[DB Downsampler] Error in downsampling worker: {e}")
            await asyncio.sleep(300)

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
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guid TEXT,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    );''')
    
    # --- THÊM INDEX ĐỂ TỐI ƯU TRUY VẤN ---
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_log_guid_timestamp ON metrics_log (guid, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_connections_guid ON active_connections (guid);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_data_guid ON audit_data (guid);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs (timestamp);")
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
    conn_type = None # 'agent' hoặc 'dashboard'
    client_guid = None
    client_address = websocket.remote_address
    timestamp_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp_str}] [Connection Opened] New connection from {client_address[0]}:{client_address[1]}")

    try:
        # Đọc tin nhắn đầu tiên để phân loại kết nối
        first_message = await websocket.recv()
        data = json.loads(first_message)
        msg_type = data.get('type')
        guid = data.get('guid')
        token = data.get('access_token')

        # --- KIỂM TRA TOKEN XÁC THỰC ---
        if ACCESS_TOKEN and token != ACCESS_TOKEN:
            print(f"[{timestamp_str}] [Auth Failed] Invalid token from {client_address}. Closing.")
            await websocket.close(code=4001, reason="Invalid access token")
            return

        if msg_type == 'client_info' and guid:
            # --- KẾT NỐI TỪ AGENT ---
            conn_type = 'agent'
            client_guid = guid
            agent_connections[guid] = websocket
            
            print(f"[{timestamp_str}] [Agent Identified] {guid} from {client_address}")
            
            hostname = data.get('hostname', 'Unknown')
            username = data.get('username', 'Unknown')
            client_info_cache[guid] = {"hostname": hostname, "username": username}
            
            # Xử lý thông tin ban đầu (giống logic cũ)
            await db_upsert_client_static_info(
                guid, hostname, username,
                data.get('local_ip'), data.get('wan_ip'),
                json.dumps(data.get('enabled_modules', []))
            )
            await db_clear_client_audit_data(guid)
            await db_add_active_connection(guid, client_address)
            await db_write_queue.join()
            
            # Broadcast cảnh báo kết nối
            alert_msg = f"Máy trạm {username} ({hostname}) đã kết nối."
            await db_log_system_event(guid, "connect", alert_msg)
            await broadcast_to_global_dashboards({
                "type": "event_alert",
                "event": "connect",
                "guid": guid,
                "hostname": hostname,
                "username": username,
                "message": alert_msg
            })

        elif msg_type == 'dashboard_login' and guid:
            # --- KẾT NỐI TỪ DASHBOARD ---
            conn_type = 'dashboard'
            client_guid = guid
            if guid not in dashboard_connections:
                dashboard_connections[guid] = set()
            dashboard_connections[guid].add(websocket)
            print(f"[{timestamp_str}] [Dashboard Connected] Monitoring Agent {guid}")
            await websocket.send(json.dumps({"type": "login_success", "message": f"Connected to server, monitoring {guid}"}))
            
        elif msg_type == 'dashboard_global_login':
            # --- KẾT NỐI LẮNG NGHE TOÀN CỤC TỪ DASHBOARD ---
            conn_type = 'dashboard_global'
            global_dashboards.add(websocket)
            print(f"[{timestamp_str}] [Global Dashboard Connected] Lắng nghe sự kiện hệ thống")
            await websocket.send(json.dumps({"type": "login_success", "message": "Connected to global alerts stream"}))
        else:
            print(f"[{timestamp_str}] [Invalid Connection] Missing type or GUID. Closing.")
            await websocket.close()
            return

        # Vòng lặp xử lý các tin nhắn tiếp theo
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get('type')
            timestamp_str = datetime.now().strftime('%H:%M:%S')

            if conn_type == 'agent':
                # --- XỬ LÝ TIN NHẮN TỪ AGENT ---
                if msg_type == 'metrics':
                    await db_log_metrics(client_guid, data)
                    # (Tùy chọn) Forward metrics tới Dashboard nếu đang xem realtime
                    if client_guid in dashboard_connections:
                        for ws in list(dashboard_connections[client_guid]):
                            try: await ws.send(message)
                            except: dashboard_connections[client_guid].remove(ws)
                    
                    # --- KIỂM TRA SỰ CỐ HIỆU NĂNG ---
                    cpu_usage = data.get('cpu_usage', 0)
                    ram_usage = data.get('ram_usage', 0)
                    
                    import time
                    current_time = time.time()
                    if client_guid not in client_alert_status:
                        client_alert_status[client_guid] = {"cpu": 0, "ram": 0}
                    
                    info = client_info_cache.get(client_guid, {"hostname": "Unknown", "username": "Unknown"})
                    hostname = info["hostname"]
                    username = info["username"]
                    
                    if cpu_usage > 90 and current_time - client_alert_status[client_guid]["cpu"] > 300:
                        alert_msg = f"Máy trạm {username} ({hostname}) có mức sử dụng CPU quá cao ({cpu_usage:.1f}%)."
                        await db_log_system_event(client_guid, "cpu_alert", alert_msg)
                        await broadcast_to_global_dashboards({
                            "type": "event_alert",
                            "event": "performance",
                            "subtype": "cpu",
                            "guid": client_guid,
                            "hostname": hostname,
                            "username": username,
                            "message": alert_msg
                        })
                        client_alert_status[client_guid]["cpu"] = current_time
                        
                    if ram_usage > 95 and current_time - client_alert_status[client_guid]["ram"] > 300:
                        alert_msg = f"Máy trạm {username} ({hostname}) có mức sử dụng RAM quá cao ({ram_usage:.1f}%)."
                        await db_log_system_event(client_guid, "ram_alert", alert_msg)
                        await broadcast_to_global_dashboards({
                            "type": "event_alert",
                            "event": "performance",
                            "subtype": "ram",
                            "guid": client_guid,
                            "hostname": hostname,
                            "username": username,
                            "message": alert_msg
                        })
                        client_alert_status[client_guid]["ram"] = current_time

                elif msg_type == 'full_audit':
                    print(f"[{timestamp_str}] [Audit Data] {client_guid}")
                    audit_results = data.get('data', {})
                    for audit_name, audit_result in audit_results.items():
                        if isinstance(audit_result, dict) and audit_result.get('encrypted'):
                            decrypted_json = WindowsAuditor._Crypto.decrypt(audit_result.get('payload'), ACCESS_TOKEN)
                            try: audit_result = json.loads(decrypted_json)
                            except: pass
                        await db_log_audit_data(client_guid, audit_name, audit_result)

                elif msg_type == 'remote_response':
                    # Chuyển tiếp phản hồi Remote Control tới Dashboard
                    if client_guid in dashboard_connections:
                        print(f"[{timestamp_str}] [Remote Response] Forwarding from Agent {client_guid} to Dashboards")
                        for ws in list(dashboard_connections[client_guid]):
                            try: await ws.send(message)
                            except: dashboard_connections[client_guid].remove(ws)

                elif msg_type == 'client_info':
                    hostname = data.get('hostname', 'Unknown')
                    username = data.get('username', 'Unknown')
                    client_info_cache[client_guid] = {"hostname": hostname, "username": username}
                    await db_upsert_client_static_info(
                        client_guid, hostname, username,
                        data.get('local_ip'), data.get('wan_ip'),
                        json.dumps(data.get('enabled_modules', []))
                    )

            elif conn_type == 'dashboard':
                # --- XỬ LÝ TIN NHẮN TỪ DASHBOARD ---
                if msg_type == 'remote_command':
                    # Chuyển tiếp lệnh tới đúng Agent
                    target_guid = data.get('target_guid')
                    if target_guid in agent_connections:
                        print(f"[{timestamp_str}] [Remote Command] Routing to Agent {target_guid}: {data.get('command')}")
                        try:
                            await agent_connections[target_guid].send(message)
                        except:
                            print(f"[{timestamp_str}] [Error] Failed to send command to Agent {target_guid}")
                            await websocket.send(json.dumps({"type": "remote_response", "error": "Agent disconnected"}))
                    else:
                        await websocket.send(json.dumps({"type": "remote_response", "error": "Agent is offline"}))

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[{timestamp_str}] [WS Error] {e}")
    finally:
        if conn_type == 'agent' and client_guid:
            if agent_connections.get(client_guid) == websocket:
                del agent_connections[client_guid]
            await db_remove_active_connection(client_guid, client_address)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Agent Disconnected] {client_guid}")
            
            info = client_info_cache.get(client_guid, {"hostname": "Unknown", "username": "Unknown"})
            hostname = info["hostname"]
            username = info["username"]
            alert_msg = f"Máy trạm {username} ({hostname}) đã ngắt kết nối."
            await db_log_system_event(client_guid, "disconnect", alert_msg)
            await broadcast_to_global_dashboards({
                "type": "event_alert",
                "event": "disconnect",
                "guid": client_guid,
                "hostname": hostname,
                "username": username,
                "message": alert_msg
            })
        elif conn_type == 'dashboard' and client_guid:
            if client_guid in dashboard_connections:
                dashboard_connections[client_guid].discard(websocket)
                if not dashboard_connections[client_guid]:
                    del dashboard_connections[client_guid]
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Dashboard Disconnected] Stopped monitoring {client_guid}")
        elif conn_type == 'dashboard_global':
            global_dashboards.discard(websocket)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Global Dashboard Disconnected]")


# --- HÀM MAIN KHỞI CHẠY SERVER ---
async def main():
    global ACCESS_TOKEN
    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")

    config = load_config(config_path)

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

    # Khởi tạo worker gộp dữ liệu cũ (Downsampling)
    asyncio.create_task(database_downsampling_worker())

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