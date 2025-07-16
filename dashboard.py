import sqlite3
import json
import os
import sys
from datetime import datetime
import configparser
import requests
import threading
import time
import webbrowser
from flask import Flask, render_template, jsonify, abort, request

# --- CẤU HÌNH ỨNG DỤNG ---
DB_NAME = "system_monitor.db"

def get_base_path():
    """Trả về thư mục chứa file .exe hoặc .py đang chạy"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # khi đã đóng gói .exe
    return os.path.dirname(os.path.abspath(__file__))  # khi chạy file .py

base_path = get_base_path()
app = Flask(
    __name__,
    template_folder=os.path.join(base_path, 'templates'),
    static_folder=os.path.join(base_path, 'static')
)

# --- CÁC HÀM TIỆN ÍCH ---

def get_db_conn():
    """Tạo kết nối đến database. Sử dụng row_factory và BẬT KHÓA NGOẠI."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON") # <<< DÒNG QUAN TRỌNG CẦN THÊM
    return conn

def check_server_status(host, port, timeout=1):
    """Kiểm tra trạng thái của server WebSocket thông qua endpoint health check."""
    try:
        response = requests.get(f"http://{host}:{port}/health", timeout=timeout)
        return response.status_code == 200 and response.text == "OK"
    except requests.RequestException:
        return False
    
def get_webserver_intervals():
    """Đọc các giá trị interval từ config để truyền vào template."""
    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.ini")

    config = configparser.ConfigParser()
    config.read(config_path)

    intervals = {
        'dashboard': config.getint('webserver', 'DASHBOARD_REFRESH_INTERVAL', fallback=5000),
        'server_status': config.getint('webserver', 'SERVER_STATUS_REFRESH_INTERVAL', fallback=100000),
        'client_metrics': config.getint('webserver', 'CLIENT_REALTIME_METRICS_INTERVAL', fallback=2000),
    }
    return intervals

# --- CÁC ROUTE RENDER TEMPLATE (TRANG WEB) ---

@app.route('/')
def index():
    """Render trang dashboard chính."""
    # Truyền các giá trị interval vào template
    return render_template('dashboard.html', intervals=get_webserver_intervals())

@app.route('/client/<string:guid>')
def client_detail(guid):
    """Render trang chi tiết cho một client cụ thể."""
    conn = get_db_conn()
    client = conn.execute('SELECT * FROM client WHERE guid = ?', (guid,)).fetchone()
    conn.close()
    if client is None:
        abort(404, description="Client not found")
    # Truyền dữ liệu client và các giá trị interval vào template
    return render_template('client_detail.html', 
                           client=dict(client), 
                           intervals=get_webserver_intervals())

# --- CÁC API ENDPOINT (CUNG CẤP DỮ LIỆU JSON) ---

@app.route('/api/dashboard_data')
def get_dashboard_data():
    """
    API endpoint chính, cung cấp tất cả dữ liệu cần thiết cho trang dashboard.
    Bao gồm trạng thái server, các số liệu thống kê, và danh sách client.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    server_check_host = "127.0.0.1"
    server_health_check_port = int(config['server']['health_check_port'])
    is_server_online = check_server_status(server_check_host, server_health_check_port)
    thresholds = {
            'clients': int(config['webserver'].get('CLIENTS', 100)),
            'records': int(config['webserver'].get('RECORDS', 100000)),
            'db_size': int(config['webserver'].get('DATABASE_SIZE', 100)) # in MB
        }
    conn = get_db_conn()
    
    # 1. Lấy thông tin thống kê
     # 1. Lấy thông tin thống kê
    total_clients = conn.execute("SELECT COUNT(id) FROM client").fetchone()[0]
    active_guids_set = {row['guid'] for row in conn.execute("SELECT guid FROM active_connections").fetchall()}
    clients_online = len(active_guids_set)
    record_count = conn.execute("SELECT COUNT(id) FROM metrics_log").fetchone()[0]
    
    try:
        db_size_bytes = os.path.getsize(DB_NAME)
        db_size_mb = db_size_bytes / (1024 * 1024)
        db_size_str = f"{db_size_mb:.2f} MB"
    except FileNotFoundError:
        db_size_mb = 0
        db_size_str = "N/A"

    # 2. Lấy thông tin chi tiết từng client (với metrics mới nhất)
    all_clients_raw = conn.execute("""
        SELECT 
            c.*, 
            ml.cpu_usage, 
            ml.ram_usage, 
            ml.disk_usage,
            ml.timestamp as metrics_timestamp
        FROM client c
        LEFT JOIN (
            SELECT 
                guid, cpu_usage, ram_usage, disk_usage, timestamp,
                ROW_NUMBER() OVER(PARTITION BY guid ORDER BY timestamp DESC) as rn
            FROM metrics_log
        ) ml ON c.guid = ml.guid AND ml.rn = 1
    """).fetchall()

    all_clients = []
    for row in all_clients_raw:
        client_dict = dict(row)
        client_dict['status'] = "Online" if client_dict['guid'] in active_guids_set else "Offline"
        all_clients.append(client_dict)
    all_clients.sort(key=lambda c: (0 if c['status'] == 'Online' else 1, c['hostname'].lower()))
    conn.close()
    
    # 3. Lấy thời gian cập nhật cuối cùng của file DB
    try:
        last_db_update_timestamp = os.path.getmtime(DB_NAME)
        last_db_update_time = datetime.fromtimestamp(last_db_update_timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except (FileNotFoundError, TypeError):
        last_db_update_time = "N/A"

    # 4. Trả về dữ liệu dưới dạng JSON
    return jsonify({
        'server_status': {
            'is_online': is_server_online,
            'last_data_update': last_db_update_time
        },
        'stats': {
            'total_clients': total_clients,
            'clients_online': clients_online,
            'record_count': record_count,
            'db_size': db_size_str,
            'db_size_mb': db_size_mb # Truyền giá trị số để JS tính toán
        },
        'clients': all_clients,
        'thresholds': thresholds # --- TRUYỀN NGƯỠNG VÀO API ---
    })

@app.route('/api/client_audit_data/<string:guid>')
def get_client_audit_data(guid):
    """API endpoint để lấy tất cả dữ liệu audit của một client."""
    conn = get_db_conn()
    audit_rows = conn.execute(
        'SELECT audit_name, data_json, timestamp FROM audit_data WHERE guid = ? ORDER BY audit_name',
        (guid,)
    ).fetchall()
    conn.close()

    audits = {}
    for row in audit_rows:
        audits[row['audit_name']] = {
            'data': json.loads(row['data_json']),
            'timestamp': datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        }
    return jsonify(audits)

# --- CÁC API CHO HÀNH ĐỘNG (CẬP NHẬT/XÓA) ---

@app.route('/api/client/delete', methods=['POST'])
def delete_client():
    """API để xóa một client và tất cả dữ liệu liên quan."""
    data = request.get_json()
    guid = data.get('guid')
    if not guid:
        return jsonify({'status': 'error', 'message': 'GUID is required'}), 400
    
    conn = get_db_conn()
    try:
        # Nhờ có 'ON DELETE CASCADE' trong DB, chỉ cần xóa từ bảng client
        cursor = conn.cursor()
        cursor.execute("DELETE FROM client WHERE guid = ?", (guid,))
        conn.commit()
        if cursor.rowcount > 0:
            return jsonify({'status': 'success', 'message': f'Client {guid} deleted.'})
        else:
            return jsonify({'status': 'error', 'message': 'Client not found.'}), 404
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/client/update_username', methods=['POST'])
def update_username():
    """API để cập nhật username (biệt danh) cho client."""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400
        
    guid = data.get('guid')
    new_username = data.get('username')

    if not guid or new_username is None:
        return jsonify({'status': 'error', 'message': 'GUID and username are required'}), 400

    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE client SET username = ? WHERE guid = ?", (new_username, guid))
        
        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Client with given GUID not found'}), 404
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()
        
    return jsonify({'status': 'success', 'message': f'Username for {guid} updated.'})

@app.route('/api/client_metrics_history/<string:guid>')
def get_client_metrics_history(guid):
    """Lấy lịch sử metrics chi tiết của client để vẽ nhiều biểu đồ."""
    conn = get_db_conn()
    history_rows = conn.execute(
        """
        SELECT 
            timestamp, cpu_usage, ram_usage, disk_usage,
            disk_io_json, network_io_json
        FROM metrics_log 
        WHERE guid = ? 
        ORDER BY timestamp DESC 
        LIMIT 100
        """,
        (guid,)
    ).fetchall()
    conn.close()

    if not history_rows:
        return jsonify({'labels': [], 'cpu': [], 'ram': [], 'disk': [], 'disk_io': {}, 'network_io': {}})

    history_rows.reverse()

    labels, cpu_data, ram_data, disk_data = [], [], [], []
    disk_io_history = {}
    network_io_history = {}
    
    # Bước 1: Khởi tạo tất cả các keys (tên thiết bị) có thể có từ toàn bộ lịch sử
    all_disk_keys = set()
    all_nic_keys = set()
    for row in history_rows:
        try:
            all_disk_keys.update(json.loads(row['disk_io_json'] or '{}').keys())
            all_nic_keys.update(json.loads(row['network_io_json'] or '{}').keys())
        except (json.JSONDecodeError, TypeError):
            continue
            
    # Sắp xếp các key để đảm bảo thứ tự trên biểu đồ luôn nhất quán
    sorted_disk_keys = sorted(list(all_disk_keys))
    sorted_nic_keys = sorted(list(all_nic_keys))
    
    for key in sorted_disk_keys:
        disk_io_history[key] = {'read_bytes_per_sec': [], 'write_bytes_per_sec': []}
    for key in sorted_nic_keys:
        network_io_history[key] = {'upload_bits_per_sec': [], 'download_bits_per_sec': []}


    # Bước 2: Lặp lại và điền dữ liệu, đảm bảo mọi mảng có cùng độ dài
    for row in history_rows:
        labels.append(datetime.fromtimestamp(row['timestamp']).strftime('%H:%M:%S'))
        cpu_data.append(row['cpu_usage'] or 0)
        ram_data.append(row['ram_usage'] or 0)
        disk_data.append(row['disk_usage'] or 0)
        
        try:
            disk_io_now = json.loads(row['disk_io_json'] or '{}')
        except (json.JSONDecodeError, TypeError):
            disk_io_now = {}
            
        try:
            net_io_now = json.loads(row['network_io_json'] or '{}')
        except (json.JSONDecodeError, TypeError):
            net_io_now = {}

        # Điền dữ liệu cho disk I/O
        for key in sorted_disk_keys:
            values = disk_io_now.get(key, {})
            disk_io_history[key]['read_bytes_per_sec'].append(values.get('read_bytes_per_sec', 0))
            disk_io_history[key]['write_bytes_per_sec'].append(values.get('write_bytes_per_sec', 0))

        # Điền dữ liệu cho network I/O
        for key in sorted_nic_keys:
            values = net_io_now.get(key, {})
            network_io_history[key]['upload_bits_per_sec'].append(values.get('upload_bits_per_sec', 0))
            network_io_history[key]['download_bits_per_sec'].append(values.get('download_bits_per_sec', 0))


    return jsonify({
        'labels': labels,
        'cpu': cpu_data,
        'ram': ram_data,
        'disk': disk_data,
        'disk_io': disk_io_history,
        'network_io': network_io_history
    })

@app.route('/api/client_realtime_metrics/<string:guid>')
def get_client_realtime_metrics(guid):
    conn = get_db_conn()
    metrics_row = conn.execute("""
        SELECT 
            cpu_usage, ram_usage, disk_usage,
            disk_io_json, network_io_json
        FROM metrics_log
        WHERE guid = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (guid,)).fetchone()
    is_online = conn.execute("SELECT 1 FROM active_connections WHERE guid = ?", (guid,)).fetchone() is not None
    conn.close()

    if metrics_row:
        metrics_dict = dict(metrics_row)
        try:
            metrics_dict['disk_io'] = json.loads(metrics_dict.pop('disk_io_json') or '{}')
            metrics_dict['network_io'] = json.loads(metrics_dict.pop('network_io_json') or '{}')
        except (json.JSONDecodeError, TypeError):
            metrics_dict['disk_io'] = {}
            metrics_dict['network_io'] = {}
        return jsonify({'status': 'success', 'is_online': is_online, 'metrics': metrics_dict})
    else:
        return jsonify({'status': 'not_found', 'is_online': is_online, 'message': 'No metrics data found.'}), 404
    
@app.route('/api/clear_records', methods=['POST'])
def clear_records():
    """API để xóa tất cả các bản ghi trong bảng metrics_log và thu nhỏ DB."""
    # Bước 1: Xóa dữ liệu trong một kết nối/giao dịch riêng
    try:
        conn_delete = get_db_conn()
        cursor_delete = conn_delete.cursor()
        
        cursor_delete.execute("DELETE FROM metrics_log")
        print("All metric records deleted.")
        
        conn_delete.commit()
        conn_delete.close()
    except Exception as e:
        app.logger.error(f"Error during DELETE phase of clearing records: {e}")
        return jsonify({'status': 'error', 'message': f"Failed to delete records: {e}"}), 500

    # Bước 2: Thực hiện VACUUM trong một kết nối hoàn toàn mới
    # VACUUM không thể chạy trong một giao dịch đang mở.
    try:
        print("Connecting to VACUUM database...")
        # Kết nối ở chế độ autocommit
        conn_vacuum = sqlite3.connect(DB_NAME, isolation_level=None)
        conn_vacuum.execute("VACUUM")
        conn_vacuum.close()
        print("Database vacuumed successfully.")
        
        return jsonify({'status': 'success', 'message': 'All metric records have been deleted and database has been compacted.'})
    except Exception as e:
        app.logger.error(f"Error during VACUUM phase: {e}")
        return jsonify({'status': 'error', 'message': f"Records deleted, but failed to compact database: {e}"}), 500

@app.route('/api/prune_offline_clients', methods=['POST'])
def prune_offline_clients():
    """API để xóa tất cả các client đang offline và dữ liệu liên quan."""
    conn = get_db_conn()
    try:
        # Lấy danh sách GUID của các client đang online
        active_guids_rows = conn.execute("SELECT DISTINCT guid FROM active_connections").fetchall()
        active_guids = {row['guid'] for row in active_guids_rows}
        
        # Lấy danh sách GUID của tất cả client
        all_guids_rows = conn.execute("SELECT guid FROM client").fetchall()
        all_guids = {row['guid'] for row in all_guids_rows}
        
        # Xác định các client offline
        offline_guids = all_guids - active_guids
        
        if not offline_guids:
            return jsonify({'status': 'success', 'message': 'No offline clients to prune.'})
        
        # Xóa các client offline. Nhờ có `ON DELETE CASCADE`,
        # dữ liệu trong `metrics_log` và `audit_data` sẽ tự động bị xóa.
        cursor = conn.cursor()
        # Chuyển set thành list/tuple để dùng trong câu lệnh SQL
        guids_to_delete = list(offline_guids)
        placeholders = ','.join('?' for _ in guids_to_delete)
        query = f"DELETE FROM client WHERE guid IN ({placeholders})"
        
        cursor.execute(query, guids_to_delete)
        deleted_count = cursor.rowcount
        conn.commit()

        # Thu nhỏ database sau khi xóa
        print(f"Pruned {deleted_count} offline clients. Compacting database...")
        conn.execute("VACUUM")

        return jsonify({'status': 'success', 'message': f'Successfully pruned {deleted_count} offline clients and compacted the database.'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error pruning offline clients: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()
        
# --- KHỞI CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('config.ini')
    webserver_host = config['webserver']['server']
    webserver_port = int(config['webserver']['port'])

    # Tự động mở trình duyệt sau 1 giây
    def open_browser():
        time.sleep(5)
        webbrowser.open(f"http://127.0.01:{webserver_port}")

    threading.Thread(target=open_browser).start()

    # debug=True #hữu ích khi phát triển
    app.run(debug=True, host=webserver_host, port=webserver_port, use_reloader=False)