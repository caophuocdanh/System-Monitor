import sys
import configparser
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QCheckBox, QVBoxLayout,
    QHBoxLayout, QGroupBox, QPushButton, QMessageBox, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt

CONFIG_FILE = "config.ini"
IMMUTABLE_KEYS = {"server", "host"}
IMMUTABLE_VALUE = "0.0.0.0"

DISPLAY_NAMES = {
    # server
    "host": "Địa chỉ IP mà server WebSocket sẽ lắng nghe (0.0.0.0 = mọi địa chỉ)",
    "port": "Cổng WebSocket chính mà server sử dụng",
    "health_check_port": "Cổng kiểm tra tình trạng server (health-check)",

    # client
    "server": "Địa chỉ WebSocket server mà client kết nối",
    "retry_interval": "Thời gian giữa các lần thử lại nếu mất kết nối (giây)",
    "refesh_interval": "Tần suất gửi dữ liệu hiệu năng (giây)",
    "update_info_interval": "Chu kỳ gửi lại thông tin đầy đủ (giây)",
    "max_event_log": "Số lượng log hệ thống lấy tối đa",
    "history_limit": "Giới hạn số lịch sử trình duyệt mỗi profile",

    # webserver
    "clients": "Số client tối đa hiển thị",
    "records": "Số bản ghi RAM tạm giữ",
    "database_size": "Dung lượng DB tối đa (MB)",
    "dashboard_refresh_interval": "Chu kỳ cập nhật dashboard (ms)",
    "server_status_refresh_interval": "Chu kỳ kiểm tra trạng thái server (ms)",
    "client_realtime_metrics_interval": "Chu kỳ lấy số liệu client (ms)",

    # audit_modules
    "cpu": "CPU",
    "ram": "Bộ nhớ RAM",
    "disk": "Ổ đĩa",
    "gpu": "Card đồ họa",
    "mainboard": "Bo mạch chủ",
    "network": "Mạng",
    "printers": "Máy in",
    "os": "Hệ điều hành",
    "system_id": "Mã hệ thống",
    "event_log": "Log hệ thống",
    "users": "Người dùng",
    "credentials": "Thông tin đăng nhập",
    "services": "Dịch vụ đang chạy",
    "startup": "Chương trình khởi động",
    "software": "Phần mềm đã cài",
    "processes": "Tiến trình",
    "web_history": "Lịch sử trình duyệt"
}

class ConfigEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛠️ Config.ini Editor")
        self.setMinimumSize(1000, 700)
        self.config = configparser.ConfigParser()
        self.entries = {}

        self.load_config()
        self.init_ui()

    def load_config(self):
        self.config.read(CONFIG_FILE)

    def init_ui(self):
        main_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_container = QWidget()
        scroll_layout = QGridLayout(scroll_container)

        col = 0
        row = 0
        section_order = list(self.config.sections())

        for section in section_order:
            if section == "audit_modules":
                continue

            group = QGroupBox(section.capitalize())
            group_layout = QVBoxLayout()

            for key, value in self.config[section].items():
                hbox = QHBoxLayout()
                label_text = DISPLAY_NAMES.get(key, key)
                label = QLabel(label_text)
                label.setWordWrap(True)
                label.setFixedWidth(200)

                entry = QLineEdit(value)
                entry.setMaximumWidth(100)

                if key in IMMUTABLE_KEYS and value == IMMUTABLE_VALUE:
                    entry.setEnabled(False)

                self.entries[(section, key)] = entry
                hbox.addWidget(label)
                hbox.addWidget(entry)
                hbox.addStretch()
                group_layout.addLayout(hbox)

            group.setLayout(group_layout)
            scroll_layout.addWidget(group, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        # === AUDIT MODULES CHECKBOX ===
        if "audit_modules" in self.config:
            audit_group = QGroupBox("Audit Modules")
            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(1)  # giảm dòng
            grid.setContentsMargins(0, 5, 0, 5)

            audit_keys = list(self.config["audit_modules"].keys())
            for i, key in enumerate(audit_keys):
                text = DISPLAY_NAMES.get(key, key)
                checkbox = QCheckBox(text)
                checkbox.setChecked(self.config["audit_modules"][key].lower() == "true")
                self.entries[("audit_modules", key)] = checkbox
                grid.addWidget(checkbox, i // 5, i % 5)

            audit_group.setLayout(grid)
            scroll_layout.addWidget(audit_group, row + 1, 0, 1, 3)

        scroll.setWidget(scroll_container)
        main_layout.addWidget(scroll)

        # === Save Button ===
        save_btn = QPushButton("💾 Lưu cấu hình")
        save_btn.clicked.connect(self.save_config)
        main_layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(main_layout)

    def save_config(self):
        for (section, key), widget in self.entries.items():
            if isinstance(widget, QLineEdit):
                if widget.isEnabled():
                    self.config[section][key] = widget.text()
            elif isinstance(widget, QCheckBox):
                self.config[section][key] = str(widget.isChecked()).lower()

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                self.config.write(f)
            QMessageBox.information(self, "✅ Thành công", "Đã lưu file config.ini thành công!")
        except Exception as e:
            QMessageBox.critical(self, "❌ Lỗi", f"Lỗi khi lưu: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConfigEditor()
    window.show()
    sys.exit(app.exec())
