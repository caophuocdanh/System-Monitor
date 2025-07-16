import asyncio
import websockets
import sqlite3
import json
import configparser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import logging
import os
import sys

# --- CẤU HÌNH LOGGING VÀ BIẾN TOÀN CỤC ---
logging.getLogger('http.server').setLevel(logging.WARNING)
DB_NAME = "system_monitor.db"
# Hàng đợi để xử lý các yêu cầu ghi vào DB một cách tuần tự
db_write_queue = asyncio.Queue()

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
    timestamp = int(datetime.now().timestamp())
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
    timestamp = int(datetime.now().timestamp())
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
    timestamp = int(datetime.now().timestamp())
    data_str = json.dumps(data)
    query = """
        INSERT INTO audit_data (guid, audit_name, timestamp, data_json) VALUES (?, ?, ?, ?)
        ON CONFLICT(guid, audit_name) DO UPDATE SET
        timestamp=excluded.timestamp, data_json=excluded.data_json
    """
    await db_write_queue.put((_execute_db_write, (query, (guid, audit_name, timestamp, data_str))))
    # print(f"Queued audit data for '{audit_name}' from {guid}")

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

def get_base_path():
    """Trả về thư mục chứa file .exe hoặc .py đang chạy"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # khi đã đóng gói .exe
    return os.path.dirname(os.path.abspath(__file__))  # khi chạy file .py

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
            
            cpu = data.get('cpu_usage', 0)
            ram = data.get('ram_usage', 0)
            disk = data.get('disk_usage', 0)
            client_ip = websocket.remote_address[0]

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
                log_message = (
                    f"[RECEIVE] <== [{timestamp_str}] [{client_guid}] "
                    f"CPU: {cpu:.1f}% | RAM: {ram:.1f}% | DISK USAGE: {disk:.1f}%"
                )
                # print(json.dumps(data, indent=4))
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
    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")

    config = configparser.ConfigParser()
    config.read(config_path)
    
    server_host = config['server']['host']
    server_port = int(config['server']['port'])
    health_check_port = int(config['server']['health_check_port'])

    health_thread = threading.Thread(
        target=run_health_check_server, 
        args=(server_host, health_check_port), 
        daemon=True
    )
    health_thread.start()

    # Khởi tạo worker ghi DB để nó chạy nền
    asyncio.create_task(database_writer_worker())

    async with websockets.serve(websocket_handler, server_host, server_port):
        print(f"[Server] WebSocket server started at ws://{server_host}:{server_port}")
        await asyncio.Future()

if __name__ == "__main__":
    # Các hàm setup DB chạy một lần duy nhất khi khởi động server
    setup_database()
    clear_active_connections()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutdown requested by user.")