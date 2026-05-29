import sys
import os
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --- Các hằng số và DISPLAY_NAMES ---
IMMUTABLE_KEYS = {"server", "host"}
IMMUTABLE_VALUE = "0.0.0.0"
BOOLEAN_KEYS = {"autostart", "gui"}

DISPLAY_NAMES = {
    "host": "Địa chỉ IP mà server WebSocket sẽ lắng nghe (0.0.0.0 = mọi địa chỉ)", "port": "Cổng WebSocket chính mà server sử dụng", "health_check_port": "Cổng kiểm tra tình trạng server (health-check)",
    "gui": "Hiển thị cửa sổ Console (Server)",
    "server": "Địa chỉ WebSocket server mà client kết nối", "retry_interval": "Thời gian giữa các lần thử lại nếu mất kết nối (giây)", "refesh_interval": "Tần suất gửi dữ liệu hiệu năng (giây)",
    "update_info_interval": "Chu kỳ gửi lại thông tin đầy đủ (giây)", "max_event_log": "Số lượng log hệ thống lấy tối đa", "history_limit": "Giới hạn số lịch sử trình duyệt mỗi profile",
    "autostart": "Khởi động cùng Windows",
    "clients": "Số client tối đa hiển thị", "records": "Số bản ghi RAM tạm giữ", "database_size": "Dung lượng DB tối đa (MB)", "dashboard_refresh_interval": "Chu kỳ cập nhật dashboard (ms)",
    "server_status_refresh_interval": "Chu kỳ kiểm tra trạng thái server (ms)", "client_realtime_metrics_interval": "Chu kỳ lấy số liệu client (ms)", "limit_items_per_page": "Số mục hiển thị trên mỗi trang (phân trang)",
    "cpu": "CPU", "ram": "Bộ nhớ RAM", "disk": "Ổ đĩa", "gpu": "Card đồ họa", "mainboard": "Bo mạch chủ", "network": "Mạng", "printers": "Máy in", "os": "Hệ điều hành",
    "system_id": "Mã hệ thống", "event_log": "Log hệ thống", "users": "Người dùng", "credentials": "Thông tin đăng nhập", "services": "Dịch vụ đang chạy", "startup": "Chương trình khởi động",
    "software": "Phần mềm đã cài", "processes": "Tiến trình", "web_history": "Lịch sử trình duyệt"
}

class ConfigEditor(ttk.Frame):
    def __init__(self, master, config_path):
        super().__init__(master, padding=(10, 10))
        self.master = master
        self.master.title(f"🛠️ Config Editor - {os.path.basename(config_path)}")
        self.config = configparser.ConfigParser()
        self.tk_vars = {}
        self.config_path = config_path
        self.load_config()
        self.create_widgets()

    def load_config(self):
        try:
            self.config.read(self.config_path, encoding='utf-8')
        except configparser.Error as e:
            messagebox.showerror("Lỗi đọc file Config", f"Không thể đọc file cấu hình:\n{e}")
            self.master.destroy()

    def create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        main_sections = ["server", "client", "webserver"]
        for i, section_name in enumerate(main_sections):
            row = 0; col = i
            group = ttk.LabelFrame(self, text=section_name.capitalize(), padding=(10, 5))
            group.grid(row=row, column=col, padx=5, pady=5, sticky="nsw")
            group.columnconfigure(1, weight=1)
            if self.config.has_section(section_name) and self.config.items(section_name):
                for i, (key, value) in enumerate(self.config[section_name].items()):
                    label = ttk.Label(group, text=DISPLAY_NAMES.get(key, key), wraplength=180)
                    label.grid(row=i, column=0, sticky="w", pady=2, padx=5)
                    
                    # Nhận diện boolean dựa trên key hoặc giá trị
                    is_bool = key in BOOLEAN_KEYS or section_name == "audit_modules" or value.lower() in ["true", "false", "1", "0"]
                    
                    if is_bool:
                        var = tk.BooleanVar(value=self.config.getboolean(section_name, key))
                        widget = ttk.Checkbutton(group, variable=var)
                    else:
                        var = tk.StringVar(value=value)
                        widget = ttk.Entry(group, textvariable=var, width=15)
                        if key in IMMUTABLE_KEYS and value == IMMUTABLE_VALUE: 
                            widget.config(state="disabled")
                    
                    widget.grid(row=i, column=1, sticky="w", padx=5)
                    self.tk_vars[(section_name, key)] = var
            else:
                placeholder = ttk.Label(group, text="(Không có cấu hình)", style="Placeholder.TLabel")
                placeholder.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        audit_group = ttk.LabelFrame(self, text="Audit Modules", padding=(10, 5))
        audit_group.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        if self.config.has_section("audit_modules") and self.config.items("audit_modules"):
            audit_keys = list(self.config["audit_modules"].keys())
            for i, key in enumerate(audit_keys):
                text = DISPLAY_NAMES.get(key, key)
                var = tk.BooleanVar(value=self.config.getboolean("audit_modules", key))
                checkbox = ttk.Checkbutton(audit_group, text=text, variable=var)
                checkbox.grid(row=i // 5, column=i % 5, sticky="w", padx=5, pady=2)
                self.tk_vars[("audit_modules", key)] = var
        else:
            placeholder = ttk.Label(audit_group, text="(Không có cấu hình)", style="Placeholder.TLabel")
            placeholder.pack(padx=10, pady=10, anchor="w")

        save_btn = ttk.Button(self, text="💾 Lưu cấu hình", command=self.save_config, style="Accent.TButton")
        save_btn.grid(row=2, column=1, pady=20, sticky="")

    def save_config(self):
        for (section, key), var in self.tk_vars.items():
            if not self.config.has_section(section): self.config.add_section(section)
            value = var.get()
            # Chuyển đổi boolean sang 0/1 để lưu vào config.ini
            if isinstance(value, bool): 
                value = "1" if value else "0"
            
            if not (key in IMMUTABLE_KEYS and self.config.get(section, key, fallback=None) == IMMUTABLE_VALUE):
                 self.config[section][key] = str(value)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f: self.config.write(f)
            messagebox.showinfo("✅ Thành công", f"Đã lưu file {os.path.basename(self.config_path)} thành công!")
        except Exception as e:
            messagebox.showerror("❌ Lỗi", f"Lỗi khi lưu file: {e}")

def is_valid_config_file(file_path):
    if not os.path.exists(file_path): return False
    config = configparser.ConfigParser()
    try: config.read(file_path, encoding='utf-8')
    except configparser.Error: return False
    expected_sections = ["server", "client", "webserver", "audit_modules"]
    for section in expected_sections:
        if config.has_section(section) and config.items(section): return True
    return False

if __name__ == "__main__":
    config_path = "config.ini"
    root = tk.Tk()
    root.withdraw() 

    if not is_valid_config_file(config_path):
        if os.path.exists(config_path):
            messagebox.showwarning("File không hợp lệ", f"File '{os.path.basename(config_path)}' không có nội dung hợp lệ.\nVui lòng chọn một file config khác.")
        else:
            messagebox.showinfo("Thông báo", "Không tìm thấy file config.ini. Vui lòng chọn file.")
        
        while True:
            selected_file = filedialog.askopenfilename(title="Chọn file config.ini", filetypes=[("INI files", "*.ini"), ("All files", "*.*")])
            if not selected_file:
                messagebox.showwarning("Hủy bỏ", "Không có file nào được chọn. Chương trình sẽ thoát.")
                root.destroy()
                sys.exit()
            
            if is_valid_config_file(selected_file):
                config_path = selected_file
                break
            else:
                messagebox.showerror("File không hợp lệ", f"File '{os.path.basename(selected_file)}' không hợp lệ hoặc rỗng. Vui lòng chọn lại.")
    
    root.deiconify() 
    root.geometry("1025x535")
    root.resizable(False, False)

    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure("Accent.TButton", foreground="white", background="dodgerblue")
    style.configure("Placeholder.TLabel", font=("TkDefaultFont", 9, "italic"), foreground="gray")

    app = ConfigEditor(master=root, config_path=config_path)
    app.pack(fill="both", expand=True)
    root.mainloop()
