import sys
import os
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from library import load_config, save_config

# --- Các hằng số và DISPLAY_NAMES ---
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
        self.config = configparser.ConfigParser()
        self.tk_vars = {}
        self.config_path = config_path if is_valid_config_file(config_path) else None
        self.create_base_layout()
        if self.config_path:
            self.load_and_refresh()

    def create_base_layout(self):
        # 1. Header: Browser area
        header_frame = ttk.Frame(self, padding=(0, 0, 0, 10))
        header_frame.pack(fill="x", side="top")
        
        ttk.Label(header_frame, text="Configuration File:").pack(side="left")
        self.path_var = tk.StringVar(value=self.config_path if self.config_path else "No file selected")
        self.path_entry = ttk.Entry(header_frame, textvariable=self.path_var, state="readonly")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Button(header_frame, text="Browse...", command=self.browse_file).pack(side="right")

        # 2. Body: Content area (Notebook or Placeholder)
        self.body_frame = ttk.Frame(self)
        self.body_frame.pack(fill="both", expand=True)
        
        self.placeholder_label = ttk.Label(
            self.body_frame, 
            text="Please select a valid 'config.ini' file to begin editing.",
            font=("Segoe UI", 11, "italic"),
            foreground="gray"
        )
        self.placeholder_label.place(relx=0.5, rely=0.4, anchor="center")

        # 3. Footer: Action buttons
        btn_frame = ttk.Frame(self, padding=(0, 10, 0, 0))
        btn_frame.pack(fill="x", side="bottom")

        self.btn_apply = ttk.Button(btn_frame, text="Apply", command=self.save_config, state="disabled")
        self.btn_apply.pack(side="right", padx=5)

        self.btn_cancel = ttk.Button(btn_frame, text="Cancel", command=self.master.destroy)
        self.btn_cancel.pack(side="right", padx=5)

        self.btn_ok = ttk.Button(btn_frame, text="OK", command=self.ok_action, state="disabled")
        self.btn_ok.pack(side="right", padx=5)

    def browse_file(self):
        selected = filedialog.askopenfilename(
            title="Select config.ini", 
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")]
        )
        if selected:
            if is_valid_config_file(selected):
                self.config_path = selected
                self.load_and_refresh()
            else:
                messagebox.showerror("Invalid File", "The selected file is not a valid configuration file.")

    def load_and_refresh(self):
        """Nạp lại dữ liệu và dựng lại các Tab."""
        try:
            self.is_encrypted = False
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        if f.read().strip().startswith("ENC:"):
                            self.is_encrypted = True
                except Exception:
                    pass
            self.config = load_config(self.config_path)
            self.path_var.set(self.config_path)
            self.master.title(f"System Monitor Properties - {os.path.basename(self.config_path)}")
            
            # Xóa nội dung cũ trong body_frame (nếu có Notebook)
            for widget in self.body_frame.winfo_children():
                widget.destroy()

            # Tạo Notebook mới
            self.notebook = ttk.Notebook(self.body_frame)
            self.notebook.pack(fill="both", expand=True)

            sections_map = {
                "server": "Server Settings",
                "client": "Client Settings",
                "webserver": "Web Dashboard",
                "audit_modules": "Audit Modules"
            }

            self.tk_vars = {} # Reset vars
            for section_name, tab_title in sections_map.items():
                tab = ttk.Frame(self.notebook, padding=10)
                self.notebook.add(tab, text=tab_title)
                if section_name == "audit_modules":
                    self.create_audit_tab(tab)
                else:
                    self.create_standard_tab(tab, section_name)
            
            # Kích hoạt các nút bấm
            self.btn_apply.config(state="normal")
            self.btn_ok.config(state="normal")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config: {e}")

    def create_standard_tab(self, parent, section):
        parent.columnconfigure(1, weight=1)
        if not self.config.has_section(section):
            ttk.Label(parent, text=f"Section [{section}] not found").grid(row=0, column=0)
            return

        for i, (key, value) in enumerate(self.config[section].items()):
            label_text = DISPLAY_NAMES.get(key, key)
            ttk.Label(parent, text=label_text, wraplength=300).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 10))

            is_bool = key in BOOLEAN_KEYS or value.lower() in ["true", "false", "1", "0"]
            if is_bool:
                var = tk.BooleanVar(value=self.config.getboolean(section, key))
                widget = ttk.Checkbutton(parent, variable=var)
            else:
                var = tk.StringVar(value=value)
                widget = ttk.Entry(parent, textvariable=var, width=25)
            
            widget.grid(row=i, column=1, sticky="w")
            self.tk_vars[(section, key)] = var

    def create_audit_tab(self, parent):
        container = ttk.LabelFrame(parent, text="Monitoring Modules", padding=10)
        container.pack(fill="both", expand=True)

        if self.config.has_section("audit_modules"):
            audit_keys = sorted(list(self.config["audit_modules"].keys()))
            for i, key in enumerate(audit_keys):
                text = DISPLAY_NAMES.get(key, key)
                var = tk.BooleanVar(value=self.config.getboolean("audit_modules", key))
                checkbox = ttk.Checkbutton(container, text=text, variable=var)
                checkbox.grid(row=i // 3, column=i % 3, sticky="w", padx=10, pady=3)
                self.tk_vars[("audit_modules", key)] = var
        else:
            ttk.Label(container, text="Audit section missing").pack()

    def ok_action(self):
        if self.save_config(silent=True):
            self.master.destroy()

    def save_config(self, silent=False):
        if not self.config_path: return False
        for (section, key), var in self.tk_vars.items():
            if not self.config.has_section(section): self.config.add_section(section)
            value = var.get()
            if isinstance(value, bool): 
                value = "1" if value else "0"
            
            self.config[section][key] = str(value)
        try:
            success = save_config(self.config_path, self.config, encrypt=getattr(self, 'is_encrypted', False))
            if not success:
                raise RuntimeError("save_config failed")
            if not silent:
                messagebox.showinfo("Success", "Settings applied successfully.")
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
            return False

def is_valid_config_file(file_path):
    if not os.path.exists(file_path): return False
    try:
        config = load_config(file_path)
    except Exception:
        return False
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
            messagebox.showwarning("Invalid File", f"File '{os.path.basename(config_path)}' does not contain valid settings.\nPlease select another file.")
        else:
            messagebox.showinfo("Information", "config.ini not found. Please select a configuration file.")
        
        while True:
            selected_file = filedialog.askopenfilename(title="Open config.ini", filetypes=[("INI files", "*.ini"), ("All files", "*.*")])
            if not selected_file:
                root.destroy()
                sys.exit()
            
            if is_valid_config_file(selected_file):
                config_path = selected_file
                break
            else:
                messagebox.showerror("Invalid File", "Selected file is invalid. Please try again.")
    
    root.deiconify() 
    # Kích thước cố định vừa khít với nội dung (Rộng x Cao)
    root.geometry("550x430")
    root.resizable(False, False)

    style = ttk.Style(root)
    
    # Ưu tiên giao diện Vista/Windows 7 nếu có
    available_themes = style.theme_names()
    if 'vista' in available_themes:
        style.theme_use('vista')
    elif 'xpnative' in available_themes:
        style.theme_use('xpnative')
    else:
        style.theme_use('clam')

    # Cấu hình font chữ chuẩn Windows 7 (Segoe UI)
    default_font = ("Segoe UI", 9)
    root.option_add("*Font", default_font)
    style.configure(".", font=default_font)
    style.configure("TNotebook.Tab", padding=[10, 2])

    app = ConfigEditor(master=root, config_path=config_path)
    app.pack(fill="both", expand=True)
    root.mainloop()
