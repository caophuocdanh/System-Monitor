import sqlite3
import uuid
import random
import time
from faker import Faker
from datetime import datetime, timedelta
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import threading
import json

DB_NAME = "system_monitor.db"

def get_db_conn():
    if not os.path.exists(DB_NAME):
        raise FileNotFoundError(f"Lỗi: Không tìm thấy file database '{DB_NAME}'.\n"
                                "Vui lòng chạy server.py và dashboard.py trước.")
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL") # Bật chế độ WAL để giảm lock
    return conn

def create_sample_clients(num_clients, log_callback):
    fake = Faker()
    clients = []
    log_callback(f"\nBắt đầu tạo {num_clients} client mẫu...")
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    success_count = 0
    for i in range(num_clients):
        hostname_base = fake.word().capitalize()
        client = {
            "guid": str(uuid.uuid4()),
            "hostname": f"{hostname_base}-{random.randint(100,999)}",
            "username": f"{hostname_base.lower()}{random.randint(1,20)}",
            "local_ip": fake.ipv4_private(), "wan_ip": fake.ipv4(),
            "enabled_modules": '["cpu", "ram", "disk", "network", "os", "gpu", "mainboard", "printers", "processes", "software", "startup", "users", "credentials", "event_log", "web_history"]'
        }
        
        try:
            cursor.execute("INSERT INTO client (guid, hostname, username, local_ip, wan_ip, enabled_modules) VALUES (:guid, :hostname, :username, :local_ip, :wan_ip, :enabled_modules)", client)
            conn.commit()
            clients.append(client)
            success_count += 1
            log_callback(f"  [Client {i+1}/{num_clients}] Đã chèn: {client['hostname']}")
            time.sleep(0.3) # Delay 0.5s theo yêu cầu
        except Exception as e:
            log_callback(f"  ❌ Lỗi khi chèn client {i+1}: {e}")
            conn.rollback()

    conn.close()
    log_callback(f"-> Đã tạo thành công {success_count} client vào DB.")
    return clients

def create_sample_audit_data(clients, template_data, log_callback):
    if not clients:
        return
    log_callback("\nBắt đầu tạo dữ liệu audit chi tiết...")
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    success_count = 0
    total_records = len(clients) * len(template_data)
    
    current_idx = 0
    for client in clients:
        log_callback(f"  Đang xử lý audit cho client {client['hostname']}...")
        for audit_name, audit_content in template_data.items():
            current_idx += 1
            personalized_data = json.loads(json.dumps(audit_content['data']))

            if audit_name == 'system_id':
                personalized_data['MachineGuid'] = client['guid']
            elif audit_name == 'os':
                personalized_data['CSName'] = client['hostname']
                personalized_data['RegisteredUser'] = client['username']
            elif audit_name == 'users':
                personalized_data['CurrentUser'] = client['username']
            
            record = {
                "guid": client['guid'],
                "audit_name": audit_name,
                "timestamp": int(datetime.now().timestamp()),
                "data_json": json.dumps(personalized_data)
            }
            
            try:
                cursor.execute("""
                    INSERT INTO audit_data (guid, audit_name, timestamp, data_json)
                    VALUES (:guid, :audit_name, :timestamp, :data_json)
                """, record)
                conn.commit()
                success_count += 1
                if current_idx % 5 == 0 or current_idx == total_records:
                     log_callback(f"    - Đã chèn {current_idx}/{total_records} bản ghi audit...")
                time.sleep(0.5) # Delay 0.5s theo yêu cầu
            except Exception as e:
                log_callback(f"    ❌ Lỗi khi chèn audit {audit_name}: {e}")
                conn.rollback()

    conn.close()
    log_callback(f"-> Đã tạo thành công {success_count} bản ghi audit.")

def create_sample_records(client_guids, num_records_per_client, log_callback):
    if not client_guids:
        log_callback("Không có client nào để tạo record.")
        return

    log_callback(f"\nBắt đầu tạo {num_records_per_client} record metrics cho mỗi trong số {len(client_guids)} client...")
    
    end_time = datetime.now()
    total_clients = len(client_guids)
    total_needed = total_clients * num_records_per_client
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    success_count = 0
    current_idx = 0
    
    for idx, guid in enumerate(client_guids):
        for i in range(num_records_per_client):
            current_idx += 1
            timestamp = end_time - timedelta(seconds=i * 5)
            record = {
                "guid": guid,
                "timestamp": int(timestamp.timestamp()),
                "cpu_usage": round(random.uniform(1.0, 95.0), 2),
                "ram_usage": round(random.uniform(20.0, 98.0), 2),
                "disk_usage": round(random.uniform(10.0, 90.0), 2),
                "local_ip": None,
                "wan_ip": None
            }
            
            try:
                cursor.execute("""
                    INSERT INTO metrics_log (guid, timestamp, cpu_usage, ram_usage, disk_usage, local_ip, wan_ip)
                    VALUES (:guid, :timestamp, :cpu_usage, :ram_usage, :disk_usage, :local_ip, :wan_ip)
                """, record)
                conn.commit()
                success_count += 1
                if current_idx % 20 == 0 or current_idx == total_needed:
                    log_callback(f"  Đã chèn {current_idx}/{total_needed} records...")
                time.sleep(0.5) # Delay 0.5s theo yêu cầu
            except Exception as e:
                log_callback(f"  ❌ Lỗi khi chèn record tại {current_idx}: {e}")
                conn.rollback()
        
    conn.close()
    log_callback(f"-> Đã tạo thành công {success_count} record metrics vào DB.")

# --- GUI ---
class SampleDataGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Công cụ tạo dữ liệu mẫu")
        self.root.geometry("500x470")

        style = ttk.Style()
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"))

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=5)
        ttk.Label(input_frame, text="Số lượng Clients:").pack(side=tk.LEFT, padx=(0, 5))
        self.num_clients_entry = ttk.Entry(input_frame, width=10)
        self.num_clients_entry.pack(side=tk.LEFT, padx=5)
        self.num_clients_entry.insert(0, "1")
        ttk.Label(input_frame, text="Records/Client:").pack(side=tk.LEFT, padx=(10, 5))
        self.num_records_entry = ttk.Entry(input_frame, width=10)
        self.num_records_entry.pack(side=tk.LEFT, padx=5)
        self.num_records_entry.insert(0, "10")

        # Check & Browse JSON
        self.create_audit_var = tk.BooleanVar(value=False)
        self.audit_check = ttk.Checkbutton(
            main_frame,
            text="Tạo dữ liệu Audit chi tiết",
            variable=self.create_audit_var,
            command=self.on_audit_toggle
        )
        self.audit_check.pack(anchor='w', pady=(5, 0))

        template_frame = ttk.Frame(main_frame)
        template_frame.pack(fill=tk.X, pady=2)
        self.template_path = tk.StringVar()
        ttk.Label(template_frame, text="File mẫu JSON:").pack(side=tk.LEFT)
        self.template_entry = ttk.Entry(template_frame, textvariable=self.template_path, width=40)
        self.template_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.template_entry.configure(state='disabled')
        self.browse_button = ttk.Button(template_frame, text="Browse...", command=self.browse_template_file)
        self.browse_button.pack(side=tk.LEFT)
        self.browse_button.configure(state='disabled')

        self.generate_button = ttk.Button(main_frame, text="Bắt đầu tạo", command=self.start_generation_thread)
        self.generate_button.pack(fill=tk.X, pady=10)

        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state='disabled')

    def browse_template_file(self):
        file_path = filedialog.askopenfilename(
            title="Chọn file JSON mẫu",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.template_path.set(file_path)

    def on_audit_toggle(self):
        is_enabled = self.create_audit_var.get()
        state = 'normal' if is_enabled else 'disabled'
        self.template_entry.configure(state=state)
        self.browse_button.configure(state=state)

    def log(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def generation_task(self):
        try:
            num_clients = int(self.num_clients_entry.get())
            num_records = int(self.num_records_entry.get())
            should_create_audit = self.create_audit_var.get()
            template_data = None
            template_file = self.template_path.get().strip()

            if num_clients <= 0:
                self.log("Lỗi: Số lượng client phải lớn hơn 0.")
                return

            self.log("--- BẮT ĐẦU QUÁ TRÌNH ---")

            if should_create_audit:
                if not template_file:
                    self.log("⚠️ Không chọn file mẫu → Bỏ qua tạo dữ liệu audit.")
                    should_create_audit = False
                elif not os.path.exists(template_file):
                    self.log(f"❌ File không tồn tại: {template_file}")
                    return
                else:
                    self.log(f"Đang đọc file template từ: {template_file}")
                    with open(template_file, 'r', encoding='utf-8') as f:
                        template_data = json.load(f)

            new_clients = create_sample_clients(num_clients, self.log)
            client_guids = [c['guid'] for c in new_clients]

            if new_clients and should_create_audit and template_data:
                create_sample_audit_data(new_clients, template_data, self.log)

            if client_guids and num_records > 0:
                create_sample_records(client_guids, num_records, self.log)

            self.log("\n--- HOÀN THÀNH! ---")
        except FileNotFoundError as e:
            self.log(str(e))
        except ValueError:
            self.log("Lỗi: Vui lòng nhập số hợp lệ cho các trường.")
        except Exception as e:
            self.log(f"Đã xảy ra lỗi không mong muốn: {e}")
        finally:
            self.generate_button.config(state=tk.NORMAL)

    def start_generation_thread(self):
        self.generate_button.config(state=tk.DISABLED)
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        thread = threading.Thread(target=self.generation_task, daemon=True)
        thread.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = SampleDataGeneratorApp(root)
    root.mainloop()
