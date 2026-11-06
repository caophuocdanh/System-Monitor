# --- library.py (Optimized Windows Auditor with Multi-Tier Fallbacks) ---

import os
import re
import sys
import json
import uuid
import shutil
import sqlite3
import getpass
import winreg
import platform
import psutil
psutil.cpu_percent(interval=None)  # Khởi tạo mốc đo CPU usage realtime lần đầu
import subprocess
import time
import hashlib
import base64
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    from Crypto.Protocol.KDF import PBKDF2
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

import socket
import requests
import logging
import logging.handlers

# --- SYSTEM LOGGING SETUP ---

def setup_system_logger(name: str, log_filename: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    Thiết lập Logger chuẩn hóa với RotatingFileHandler (tối đa 5MB, lưu 3 bản backup)
    và StreamHandler xuất ra Console.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 2. File Handler (Rotating)
    if log_filename:
        try:
            base_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
            logs_dir = os.path.join(base_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            log_path = os.path.join(logs_dir, log_filename)
            
            fh = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            fh.setLevel(level)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            logger.warning(f"Failed to attach RotatingFileHandler to '{log_filename}': {e}")

    logger.propagate = False
    return logger

# --- Conditional Import for pywin32 ---
try:
    import win32print
    from pywintypes import error as PyWinError
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    PyWinError = type('PyWinError', (Exception,), {})

if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes
else:
    ctypes = None
    wintypes = None

# --- Helper Functions & Registry Utilities ---

def _read_reg_val(hkey, subkey: str, val_name: str, wow64_64: bool = True) -> Optional[Any]:
    """Đọc an toàn một giá trị Registry trên Windows."""
    if platform.system() != "Windows":
        return None
    try:
        flags = winreg.KEY_READ
        if wow64_64:
            flags |= winreg.KEY_WOW64_64KEY
        with winreg.OpenKey(hkey, subkey, 0, flags) as k:
            val, _ = winreg.QueryValueEx(k, val_name)
            return val
    except Exception:
        return None

def _run_powershell(command: str, use_bypass: bool = True, timeout: int = 25) -> Any:
    """
    Thực thi PowerShell an toàn trên cả Win 7 (PS 2.0/3.0) đến Win 11 (PS 5.1/7.x):
    - Ép mã hóa UTF-8 ở console đầu ra để không bị vỡ font tiếng Việt.
    - Tạo cờ CREATE_NO_WINDOW để không hiện popup CMD/Console.
    - Timeout bảo vệ chống treo vĩnh viễn.
    """
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    ps_command_list = ["powershell", "-NoProfile"]
    if use_bypass:
        ps_command_list.extend(["-ExecutionPolicy", "Bypass"])
    
    # Ép console output UTF-8 ngay trong phiên PowerShell
    wrapped_command = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"
    ps_command_list.extend(["-Command", wrapped_command])
    
    try:
        process = subprocess.run(
            ps_command_list, capture_output=True, timeout=timeout, creationflags=flags
        )
        stdout_bytes = process.stdout
        try:
            json_output = stdout_bytes.decode('utf-8')
        except UnicodeDecodeError:
            json_output = stdout_bytes.decode('utf-8', errors='replace')

        json_output = json_output.strip()
        if not json_output:
            return []
        return json.loads(json_output)
    except Exception:
        return []

def _parse_dotnet_json_date(date_obj: Any) -> Optional[datetime]:
    """Parse ngày tháng định dạng /Date(1234567890)/ của .NET JSON."""
    date_str = date_obj.get('value') if isinstance(date_obj, dict) else date_obj
    if not isinstance(date_str, str) or "/Date(" not in date_str:
        return None
    match = re.search(r'\((\d+)\)', date_str)
    if match:
        try:
            return datetime.fromtimestamp(int(match.group(1)) / 1000)
        except (ValueError, IndexError, OverflowError):
            return None
    return None

def _compat_wmi_script(cim_cmd: str, wmi_cmd: str) -> str:
    """Tạo script PowerShell thông minh: Thử Get-CimInstance (Win 8/10/11), fallback Get-WmiObject (Win 7)."""
    return f"""
    if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {{
        {cim_cmd}
    }} else {{
        {wmi_cmd}
    }}
    """


# --- Core WindowsAuditor Class ---

class WindowsAuditor:
    """Thư viện thu thập thông tin hệ thống Windows với cơ chế Fallback Đa Tầng."""

    class _Crypto:
        """Cung cấp các hàm mã hóa AES-256 để bảo vệ dữ liệu nhạy cảm."""
        
        @staticmethod
        def _get_derived_key(password: str, salt: bytes):
            return PBKDF2(password, salt, dkLen=32, count=1000)

        @staticmethod
        def encrypt(data_json: str, password: str) -> str:
            if not HAS_CRYPTO or not password:
                return data_json 
            try:
                salt = os.urandom(16)
                key = WindowsAuditor._Crypto._get_derived_key(password, salt)
                cipher = AES.new(key, AES.MODE_CBC)
                encrypted_bytes = cipher.encrypt(pad(data_json.encode('utf-8'), AES.block_size))
                combined = salt + cipher.iv + encrypted_bytes
                return base64.b64encode(combined).decode('utf-8')
            except Exception as e:
                print(f"[Crypto Error] Encryption failed: {e}")
                return data_json

        @staticmethod
        def decrypt(encrypted_base64: str, password: str) -> str:
            if not HAS_CRYPTO or not password:
                return encrypted_base64
            try:
                combined = base64.b64decode(encrypted_base64)
                if len(combined) < 33:
                    return encrypted_base64
                salt = combined[:16]
                iv = combined[16:32]
                encrypted_bytes = combined[32:]
                key = WindowsAuditor._Crypto._get_derived_key(password, salt)
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted_bytes = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
                return decrypted_bytes.decode('utf-8')
            except Exception as e:
                return encrypted_base64

    class _RemoteControl:
        """Cung cấp các chức năng điều khiển từ xa."""

        @staticmethod
        def execute_command(command: str, shell_type: str = "cmd") -> Dict[str, Any]:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            if shell_type == "powershell":
                args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
            else:
                args = ["cmd", "/c", command]
            try:
                process = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                    text=True, creationflags=flags, encoding='utf-8', errors='replace'
                )
                stdout, stderr = process.communicate(timeout=30)
                return {"stdout": stdout, "stderr": stderr, "exit_code": process.returncode}
            except subprocess.TimeoutExpired:
                process.kill()
                return {"error": "Command timed out after 30 seconds."}
            except Exception as e:
                return {"error": str(e)}

        @staticmethod
        def get_process_list() -> List[Dict[str, Any]]:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    processes.append({
                        "pid": pinfo['pid'],
                        "name": pinfo['name'],
                        "user": pinfo['username'],
                        "cpu": pinfo['cpu_percent'],
                        "ram": pinfo['memory_percent']
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            return processes

        @staticmethod
        def kill_process(pid: int) -> bool:
            try:
                p = psutil.Process(pid)
                p.terminate()
                return True
            except Exception:
                return False

        @staticmethod
        def take_screenshot() -> Optional[str]:
            try:
                from PIL import ImageGrab
                import io
                try:
                    screenshot = ImageGrab.grab(all_screens=True)
                except Exception:
                    screenshot = ImageGrab.grab()
                img_byte_arr = io.BytesIO()
                screenshot.save(img_byte_arr, format='JPEG', quality=70)
                return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            except Exception as e:
                print(f"[RemoteControl] Screenshot error: {e}")
                return None

        @staticmethod
        def list_dir(path: str) -> Dict[str, Any]:
            if not path or path == "drives":
                if platform.system() == "Windows":
                    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                    drives = []
                    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                        if bitmask & 1:
                            drives.append(f"{letter}:\\")
                        bitmask >>= 1
                    return {"type": "drives", "items": drives}
                else:
                    path = "/"

            try:
                items = []
                for entry in os.scandir(path):
                    try:
                        info = entry.stat()
                        items.append({
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "size": info.st_size if not entry.is_dir() else 0,
                            "mtime": info.st_mtime
                        })
                    except Exception:
                        continue
                return {"type": "directory", "path": path, "items": items}
            except Exception as e:
                return {"error": str(e)}

        @staticmethod
        def download_file_or_folder(path: str, max_size_mb: int = 75) -> Dict[str, Any]:
            import zipfile
            import io

            if not path or not os.path.exists(path):
                return {"success": False, "error": f"Path not found: {path}"}

            norm_path = os.path.abspath(path)
            max_bytes = max_size_mb * 1024 * 1024

            try:
                if os.path.isdir(norm_path):
                    folder_name = os.path.basename(norm_path.rstrip('\\/')) or "archive"
                    zip_filename = f"{folder_name}.zip"
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                        for root, _, files in os.walk(norm_path):
                            for file in files:
                                full_file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(full_file_path, norm_path)
                                arcname = os.path.join(folder_name, rel_path)
                                try:
                                    zipf.write(full_file_path, arcname=arcname)
                                except Exception:
                                    continue
                    
                    zip_data = zip_buffer.getvalue()
                    if len(zip_data) > max_bytes:
                        return {
                            "success": False, 
                            "error": f"Folder zipped size ({len(zip_data) // (1024*1024)}MB) exceeds limit of {max_size_mb}MB."
                        }
                    return {
                        "success": True,
                        "filename": zip_filename,
                        "content": base64.b64encode(zip_data).decode('utf-8'),
                        "is_zip": True,
                        "size": len(zip_data)
                    }

                elif os.path.isfile(norm_path):
                    file_size = os.path.getsize(norm_path)
                    if file_size > max_bytes:
                        return {
                            "success": False, 
                            "error": f"File size ({file_size // (1024*1024)}MB) exceeds limit of {max_size_mb}MB."
                        }
                    with open(norm_path, 'rb') as f:
                        file_data = f.read()
                    return {
                        "success": True,
                        "filename": os.path.basename(norm_path),
                        "content": base64.b64encode(file_data).decode('utf-8'),
                        "is_zip": False,
                        "size": file_size
                    }
                else:
                    return {"success": False, "error": "Invalid file or directory."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @staticmethod
        def upload_file(path: str, b64_content: str) -> Dict[str, Any]:
            try:
                parent_dir = os.path.dirname(os.path.abspath(path))
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                file_bytes = base64.b64decode(b64_content)
                with open(path, 'wb') as f:
                    f.write(file_bytes)
                return {"success": True, "path": path, "size": len(file_bytes)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @staticmethod
        def delete_path(path: str) -> Dict[str, Any]:
            if not path or not os.path.exists(path):
                return {"success": False, "error": "Path not found."}
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                return {"success": True, "path": path}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @staticmethod
        def create_dir(path: str) -> Dict[str, Any]:
            try:
                os.makedirs(path, exist_ok=True)
                return {"success": True, "path": path}
            except Exception as e:
                return {"success": False, "error": str(e)}

    class _Usage:
        """Đo lường hiệu năng CPU, RAM, Disk, Network I/O."""
        _disk_name_cache = None
        _last_disk_io = {}
        _last_disk_time = 0
        _last_net_io = {}
        _last_net_time = 0

        @staticmethod
        def _get_disk_model_map():
            if WindowsAuditor._Usage._disk_name_cache is not None:
                return WindowsAuditor._Usage._disk_name_cache

            local_cache = {}
            try:
                disk_auditor = WindowsAuditor._DiskAudit()
                physical_disks_info = disk_auditor.get_details().get("PhysicalDisks", [])
                
                for disk in physical_disks_info:
                    device_id_raw = disk.get("DeviceID")
                    model = disk.get("Model")
                    if device_id_raw and model:
                        physical_name_from_audit = device_id_raw.rsplit('\\', 1)[-1]
                        standardized_key = physical_name_from_audit.lower()
                        if model.strip():
                            local_cache[standardized_key] = model.strip()
            except Exception as e:
                print(f"[Metrics Helper Error] Could not cache disk names: {e}")
            
            WindowsAuditor._Usage._disk_name_cache = local_cache           
            return WindowsAuditor._Usage._disk_name_cache

        @staticmethod
        def get_cpu_usage():
            return psutil.cpu_percent(interval=None)

        @staticmethod
        def get_ram_usage():
            if platform.system() == "Windows" and ctypes:
                try:
                    class MEMORYSTATUSEX(ctypes.Structure):
                        _fields_ = [
                            ("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                        ]
                    stat = MEMORYSTATUSEX()
                    stat.dwLength = ctypes.sizeof(stat)
                    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                        return float(stat.dwMemoryLoad)
                except Exception:
                    pass
            return psutil.virtual_memory().percent
        
        @staticmethod
        def get_disk_usage():
            try:
                total_percent = 0.0
                count = 0
                for part in psutil.disk_partitions(all=False):
                    if not part.fstype: continue
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        if usage.total > 1073741824: # > 1GB
                            total_percent += usage.percent
                            count += 1
                    except (PermissionError, OSError): continue
                return float(total_percent / count) if count > 0 else 0.0
            except Exception:
                return 0.0

        @staticmethod
        def get_disk_io_per_disk():
            disk_name_map = WindowsAuditor._Usage._get_disk_model_map()
            current_io = psutil.disk_io_counters(perdisk=True) or {}
            current_time = time.time()
            
            last_io = WindowsAuditor._Usage._last_disk_io
            last_time = WindowsAuditor._Usage._last_disk_time
            
            WindowsAuditor._Usage._last_disk_io = current_io
            WindowsAuditor._Usage._last_disk_time = current_time

            results = {}
            if not last_io:
                return {f"DISK {i}: {disk_name_map.get(k, 'Unknown')}": {"read_bytes_per_sec": 0, "write_bytes_per_sec": 0} 
                        for i, k in enumerate(sorted(disk_name_map.keys()))}

            interval = current_time - last_time
            if interval <= 0: interval = 1

            sorted_keys = sorted(disk_name_map.keys(), key=lambda x: int(''.join(filter(str.isdigit, x)) or 0))
            
            for i, standardized_key in enumerate(sorted_keys):
                model_name = disk_name_map.get(standardized_key, "Unknown Model")
                display_name = f"DISK {i}: {model_name}"
                psutil_key = next((k for k in current_io.keys() if k.lower() == standardized_key), None)

                read_bps, write_bps = 0, 0
                if psutil_key and psutil_key in last_io:
                    read_bps = (current_io[psutil_key].read_bytes - last_io[psutil_key].read_bytes) / interval
                    write_bps = (current_io[psutil_key].write_bytes - last_io[psutil_key].write_bytes) / interval
                
                results[display_name] = {
                    "read_bytes_per_sec": int(max(0, read_bps)), 
                    "write_bytes_per_sec": int(max(0, write_bps))
                }
            return results 
            
        @staticmethod
        def get_network_io_per_nic():
            nic_stats = psutil.net_if_stats()
            current_io = psutil.net_io_counters(pernic=True) or {}
            current_time = time.time()

            last_io = WindowsAuditor._Usage._last_net_io
            last_time = WindowsAuditor._Usage._last_net_time

            WindowsAuditor._Usage._last_net_io = current_io
            WindowsAuditor._Usage._last_net_time = current_time

            results = {}
            if not last_io:
                return {n: {"upload_bits_per_sec": 0, "download_bits_per_sec": 0} for n, s in nic_stats.items() 
                        if s.isup and "loopback" not in n.lower()}

            interval = current_time - last_time
            if interval <= 0: interval = 1

            for nic_name, stats in nic_stats.items():
                if stats.isup and "loopback" not in nic_name.lower():
                    upload_bps, download_bps = 0, 0
                    if nic_name in current_io and nic_name in last_io:
                        upload_bps = (current_io[nic_name].bytes_sent - last_io[nic_name].bytes_sent) * 8 / interval
                        download_bps = (current_io[nic_name].bytes_recv - last_io[nic_name].bytes_recv) * 8 / interval
                    
                    results[nic_name] = {
                        "upload_bits_per_sec": int(max(0, upload_bps)), 
                        "download_bits_per_sec": int(max(0, download_bps))
                    }
            return results

    class _Ip:
        @staticmethod
        def get_local_ip():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"

        @staticmethod
        def get_wan_ip():
            # Chỉ lấy IPv4: sử dụng các endpoint chuyên dụng chỉ trả về IPv4 và kiểm tra cấu trúc IPv4 nghiêm ngặt
            def is_valid_ipv4(ip_str: str) -> bool:
                if not ip_str:
                    return False
                parts = ip_str.strip().split('.')
                if len(parts) != 4:
                    return False
                for p in parts:
                    if not p.isdigit() or not (0 <= int(p) <= 255):
                        return False
                    if len(p) > 1 and p.startswith('0'):
                        return False
                return True

            ipv4_services = [
                "https://api4.ipify.org",
                "https://ipv4.icanhazip.com",
                "https://v4.ident.me",
                "https://checkip.amazonaws.com",
                "https://api-ipv4.ip.sb/ip"
            ]
            for s in ipv4_services:
                try:
                    res = requests.get(s, timeout=3)
                    if res.status_code == 200:
                        candidate = res.text.strip()
                        if is_valid_ipv4(candidate):
                            return candidate
                except Exception:
                    continue
            return "N/A"

    # --- 1. CPU AUDIT (Đa tầng: Registry + psutil -> CIM/WMI) ---
    class _CpuAudit:
        def __init__(self):
            self._details: Dict[str, Any] = {}

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details

            # --- Tầng 1: Đọc Registry trực tiếp (Tức thì, không tốn tài nguyên) ---
            brand = _read_reg_val(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
            vendor = _read_reg_val(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "VendorIdentifier")
            
            machine_arch = platform.machine()
            bits = 64 if "64" in machine_arch or sys.maxsize > 2**32 else 32
            arch_str = "x86_64" if bits == 64 else "x86"
            if "arm" in machine_arch.lower():
                arch_str = "ARM64" if bits == 64 else "ARM"

            res = {
                "Brand": str(brand).strip() if brand else "Unknown CPU",
                "Vendor": str(vendor).strip() if vendor else "Unknown Vendor",
                "Architecture": arch_str,
                "Bits": bits,
                "Physical Cores": psutil.cpu_count(logical=False) or 1,
                "Logical Cores": psutil.cpu_count(logical=True) or 1,
                "Processor": platform.processor(),
                "Machine": platform.machine(),
                "System": platform.system(),
                "Release": platform.release(),
                "Version": platform.version(),
                "Platform": platform.platform()
            }

            # --- Tầng 2: Nếu chưa lấy được Brand, bổ sung qua PowerShell CIM/WMI ---
            if not brand or res["Brand"] == "Unknown CPU":
                try:
                    script = _compat_wmi_script(
                        "Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, Architecture, AddressWidth | ConvertTo-Json",
                        "Get-WmiObject Win32_Processor | Select-Object Name, Manufacturer, Architecture, AddressWidth | ConvertTo-Json"
                    )
                    wmi_data = _run_powershell(script)
                    processor = wmi_data if isinstance(wmi_data, dict) else (wmi_data[0] if isinstance(wmi_data, list) and wmi_data else {})
                    if processor.get("Name"):
                        res["Brand"] = processor["Name"].strip()
                    if processor.get("Manufacturer"):
                        res["Vendor"] = processor["Manufacturer"].strip()
                except Exception:
                    pass

            self._details = res
            return self._details

    # --- 2. CREDENTIAL AUDIT ---
    class _CredentialAudit:
        def __init__(self):
            self._details: Dict[str, List[Dict[str, str]]] = {}

        def _fetch_raw_credentials(self) -> List[Dict[str, str]]:
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                cf = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                output = subprocess.check_output("cmdkey /list", shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf)
                creds, current_cred = [], {}
                for line in output.splitlines():
                    line = line.strip()
                    if not line:
                        if current_cred: creds.append(current_cred)
                        current_cred = {}
                        continue
                    if line.startswith("Target:"): current_cred["Target"] = line.replace("Target:", "").strip()
                    elif line.startswith("Type:"): current_cred["Type"] = line.replace("Type:", "").strip()
                    elif line.startswith("User:"): current_cred["User"] = line.replace("User:", "").strip()
                if current_cred: creds.append(current_cred)
                return creds
            except Exception as e:
                return []

        def _classify_credentials(self, raw_creds: List[Dict[str, str]]) -> Dict[str, List]:
            classified = {"Web": [], "Windows": [], "Other": []}
            WEB_KW = ('microsoftaccount', 'sso_saml', 'github', 'google', 'http', 'git:')
            WIN_KW = ('domain password', 'rdp', 'remotecontrol')
            for cred in raw_creds:
                if "Error" in cred: classified["Other"].append(cred); continue
                target = cred.get("Target", "").lower()
                ctype = cred.get("Type", "").lower()
                if any(k in target for k in WEB_KW): classified["Web"].append(cred)
                elif ctype in WIN_KW or any(k in target for k in WIN_KW): classified["Windows"].append(cred)
                else: classified["Other"].append(cred)
            return classified

        def get_details(self) -> Dict[str, List[Dict[str, str]]]:
            if not self._details:
                self._details = self._classify_credentials(self._fetch_raw_credentials())
            return self._details

    # --- 3. DISK AUDIT (Đa tầng: CIM/WMI phẳng -> psutil native) ---
    class _DiskAudit:
        def __init__(self):
            self._details: Dict[str, Any] = {}

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details

            phys_disks = []
            net_drives = []
            logical_drives = []

            # --- Tầng 1: PowerShell (Hỗ trợ cả Win 7 và Win 10/11) ---
            ps_script = r"""
            $ErrorActionPreference = 'SilentlyContinue'
            $disks = if (Get-Command Get-CimInstance -EA 0) { Get-CimInstance Win32_DiskDrive } else { Get-WmiObject Win32_DiskDrive }
            $parts = if (Get-Command Get-CimInstance -EA 0) { Get-CimInstance Win32_DiskPartition } else { Get-WmiObject Win32_DiskPartition }
            $logicals = if (Get-Command Get-CimInstance -EA 0) { Get-CimInstance Win32_LogicalDisk } else { Get-WmiObject Win32_LogicalDisk }

            # 1. Bảng tra cứu logical disk info
            $logMap = @{}
            foreach ($l in $logicals) {
                if ($l.DriveType -eq 3 -or $l.DriveType -eq 4) {
                    $logMap[$l.DeviceID] = @{
                        DeviceID = $l.DeviceID
                        VolumeName = if ($l.VolumeName) { $l.VolumeName } else { "" }
                        FileSystem = if ($l.FileSystem) { $l.FileSystem } else { "" }
                        Size = [int64]$l.Size
                        FreeSpace = [int64]$l.FreeSpace
                    }
                }
            }

            # 2. Bảng mapping từ Partition sang Drive Letter qua Win32_LogicalDiskToPartition
            $partToDrive = @{}
            try {
                $assoc = if (Get-Command Get-CimInstance -EA 0) { Get-CimInstance Win32_LogicalDiskToPartition -EA 0 } else { Get-WmiObject Win32_LogicalDiskToPartition -EA 0 }
                foreach ($a in $assoc) {
                    $ant = [string]$a.Antecedent
                    $dep = [string]$a.Dependent
                    $partId = if ($ant -match 'DeviceID\s*=\s*"([^"]+)"') { $matches[1] } else { "" }
                    $driveId = if ($dep -match 'DeviceID\s*=\s*"([^"]+)"') { $matches[1] } else { "" }
                    if ($partId -and $driveId) {
                        $partToDrive[$partId] = $driveId
                    }
                }
            } catch {}

            # 3. Lắp ráp dữ liệu chi tiết PhysicalDisks -> Partitions -> LogicalDisks
            $pList = @()
            foreach ($d in $disks) {
                $idx = $d.Index
                $dParts = @()
                foreach ($p in ($parts | Where-Object { $_.DiskIndex -eq $idx })) {
                    $lData = @()
                    $driveLetter = $partToDrive[$p.DeviceID]
                    if ($driveLetter -and $logMap.ContainsKey($driveLetter)) {
                        $lData += $logMap[$driveLetter]
                    }
                    
                    $dParts += @{
                        DeviceID = $p.DeviceID
                        Type = $p.Type
                        Size = [int64]$p.Size
                        LogicalDisks = $lData
                    }
                }
                
                $pList += @{
                    DeviceID = $d.DeviceID
                    Model = if ($d.Model) { $d.Model.Trim() } else { "Generic Disk" }
                    SerialNumber = if ($d.SerialNumber) { $d.SerialNumber.Trim() } else { "N/A" }
                    InterfaceType = if ($d.InterfaceType) { $d.InterfaceType } else { "N/A" }
                    MediaType = if ($d.MediaType) { $d.MediaType } else { "Fixed hard disk media" }
                    Status = if ($d.Status) { $d.Status } else { "OK" }
                    Size = [int64]$d.Size
                    Partitions = $dParts
                }
            }

            # 4. Danh sách các ổ đĩa logic và ổ mạng
            $lList = @()
            $nList = @()
            foreach ($l in $logicals) {
                if ($l.DriveType -eq 4) {
                    $nList += @{ DeviceID = $l.DeviceID; ProviderName = $l.ProviderName }
                } elseif ($l.DriveType -eq 3 -and $l.Size -gt 1073741824) {
                    $lList += @{
                        DeviceID = $l.DeviceID
                        VolumeName = if ($l.VolumeName) { $l.VolumeName } else { "" }
                        FileSystem = if ($l.FileSystem) { $l.FileSystem } else { "" }
                        Size = [int64]$l.Size
                        FreeSpace = [int64]$l.FreeSpace
                    }
                }
            }

            @{ PhysicalDisks = $pList; NetworkDrives = $nList; LogicalDisks = $lList } | ConvertTo-Json -Depth 6
            """
            try:
                raw_data = _run_powershell(ps_script)
                if isinstance(raw_data, dict):
                    phys_disks = raw_data.get("PhysicalDisks") or []
                    net_drives = raw_data.get("NetworkDrives") or []
                    logical_drives = raw_data.get("LogicalDisks") or []
                    if isinstance(phys_disks, dict): phys_disks = [phys_disks]
                    if isinstance(net_drives, dict): net_drives = [net_drives]
                    if isinstance(logical_drives, dict): logical_drives = [logical_drives]
            except Exception:
                pass

            # --- Tầng 2: Dự phòng bằng psutil nếu PowerShell rỗng ---
            if not logical_drives:
                try:
                    for part in psutil.disk_partitions(all=False):
                        if not part.fstype: continue
                        try:
                            usage = psutil.disk_usage(part.mountpoint)
                            if usage.total > 1073741824:
                                logical_drives.append({
                                    "DeviceID": part.device.rstrip('\\'),
                                    "VolumeName": part.mountpoint,
                                    "FileSystem": part.fstype,
                                    "Size": usage.total,
                                    "FreeSpace": usage.free
                                })
                        except Exception:
                            continue
                except Exception:
                    pass

            if not phys_disks:
                # Tạo danh sách PhysicalDisks tối thiểu từ logical drives để không bị trống giao diện
                total_size = sum(d.get("Size", 0) for d in logical_drives)
                fallback_parts = []
                for idx, ld in enumerate(logical_drives):
                    fallback_parts.append({
                        "DeviceID": f"Disk #0, Partition #{idx}",
                        "Type": "Basic Data",
                        "Size": ld.get("Size", 0),
                        "LogicalDisks": [ld]
                    })
                phys_disks = [{
                    "DeviceID": r"\\.\PHYSICALDRIVE0",
                    "Model": "Primary System Drive",
                    "SerialNumber": "N/A",
                    "InterfaceType": "SATA/NVMe",
                    "MediaType": "Fixed hard disk media",
                    "Status": "OK",
                    "Size": total_size,
                    "Partitions": fallback_parts
                }]

            self._details = {
                "PhysicalDisks": phys_disks,
                "NetworkDrives": net_drives,
                "LogicalDisks": logical_drives
            }
            return self._details

    # --- 4. EVENT LOG AUDIT (Đa tầng: Get-WinEvent -> Get-EventLog -> wevtutil) ---
    class _EventLogAudit:
        def __init__(self, max_events: int = 25): 
            self._details = []
            self.max_events = max_events
            
        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details
            
            # Tầng 1 & 2: Thử Get-WinEvent (Win 8/10/11), nếu lỗi fallback sang Get-EventLog (Win 7)
            ps_script = f"""
            $events = @()
            if (Get-Command Get-WinEvent -ErrorAction SilentlyContinue) {{
                try {{
                    $events = Get-WinEvent -LogName System -MaxEvents {self.max_events} -ErrorAction Stop |
                        Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
                }} catch {{}}
            }}
            if ($events.Count -eq 0 -and (Get-Command Get-EventLog -ErrorAction SilentlyContinue)) {{
                try {{
                    $events = Get-EventLog -LogName System -Newest {self.max_events} -ErrorAction Stop |
                        Select-Object @{{n='TimeCreated';e={{$_.TimeGenerated}}}}, @{{n='ProviderName';e={{$_.Source}}}}, @{{n='Id';e={{$_.EventID}}}}, @{{n='LevelDisplayName';e={{$_.EntryType}}}}, Message
                }} catch {{}}
            }}
            $events | ConvertTo-Json -Depth 2
            """
            try:
                raw_events = _run_powershell(ps_script)
                if isinstance(raw_events, dict):
                    raw_events = [raw_events]
                
                processed_events = []
                for event in (raw_events or []):
                    if not event or not isinstance(event, dict): continue
                    dt_obj = _parse_dotnet_json_date(event.get("TimeCreated"))
                    event["TimeCreated"] = dt_obj.strftime("%Y-%m-%d %H:%M:%S") if dt_obj else str(event.get("TimeCreated") or '')
                    if "Message" in event and event.get("Message"):
                        event["Message"] = str(event["Message"]).replace('\r\n', ' ').strip()
                    processed_events.append(event)
                
                if processed_events:
                    self._details = processed_events
                    return self._details
            except Exception:
                pass

            # Tầng 3: CLI native wevtutil (Có sẵn trên tất cả các bản Windows từ Win 7 đến Win 11)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                cf = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                cmd = f"wevtutil qe System /c:{self.max_events} /rd:true /f:text"
                output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf, timeout=10)
                records = []
                current = {}
                for line in output.splitlines():
                    line = line.strip()
                    if line.startswith("Event["):
                        if current: records.append(current)
                        current = {"ProviderName": "System", "Id": 0, "LevelDisplayName": "Information", "TimeCreated": "", "Message": ""}
                    elif line.startswith("Date:"): current["TimeCreated"] = line.replace("Date:", "").strip()
                    elif line.startswith("Event ID:"): current["Id"] = line.replace("Event ID:", "").strip()
                    elif line.startswith("Source:"): current["ProviderName"] = line.replace("Source:", "").strip()
                    elif line.startswith("Description:"): current["Message"] = line.replace("Description:", "").strip()
                if current: records.append(current)
                self._details = records or [{"Info": "No recent events logged."}]
            except Exception as e:
                self._details = [{"Error": f"Could not retrieve System event log: {e}"}]

            return self._details

    # --- 5. GPU AUDIT (Đa tầng: CIM/WMI -> Registry Display Class -> Generic) ---
    class _GpuAudit:
        def __init__(self):
            self._details: List[Dict[str, Any]] = []

        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details

            # --- Tầng 1: PowerShell CIM/WMI ---
            ps_script = _compat_wmi_script(
                "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion, DriverDate, Status | ConvertTo-Json -Depth 2",
                "Get-WmiObject Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion, DriverDate, Status | ConvertTo-Json -Depth 2"
            )
            try:
                raw_data = _run_powershell(ps_script)
                raw_data = [raw_data] if isinstance(raw_data, dict) else (raw_data or [])
                processed = []
                for gpu in raw_data:
                    if not gpu or not isinstance(gpu, dict): continue
                    dt = _parse_dotnet_json_date(gpu.get("DriverDate"))
                    try: vram = int(gpu.get("AdapterRAM") or 0)
                    except Exception: vram = None
                    processed.append({
                        "Name": gpu.get("Name") or "Generic Display Adapter",
                        "VRAM_Bytes": vram,
                        "DriverVersion": gpu.get("DriverVersion") or "N/A",
                        "DriverDate": dt.strftime("%Y-%m-%d") if dt else str(gpu.get("DriverDate") or "N/A"),
                        "Status": gpu.get("Status") or "OK"
                    })
                if processed:
                    self._details = processed
                    return self._details
            except Exception:
                pass

            # --- Tầng 2: Đọc Registry Display Class (100% độc lập, không cần PowerShell) ---
            try:
                guid_key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, guid_key) as k:
                    subkeys = winreg.QueryInfoKey(k)[0]
                    reg_gpus = []
                    for i in range(subkeys):
                        sub = winreg.EnumKey(k, i)
                        if sub.isdigit():
                            try:
                                with winreg.OpenKey(k, sub) as sk:
                                    def gv(name):
                                        try: return winreg.QueryValueEx(sk, name)[0]
                                        except: return None
                                    desc = gv("DriverDesc")
                                    if desc:
                                        ver = gv("DriverVersion") or "N/A"
                                        date = gv("DriverDate") or "N/A"
                                        vram = gv("HardwareInformation.qwMemorySize") or 0
                                        reg_gpus.append({
                                            "Name": desc,
                                            "VRAM_Bytes": int(vram) if vram else None,
                                            "DriverVersion": ver,
                                            "DriverDate": date,
                                            "Status": "OK"
                                        })
                            except Exception:
                                pass
                    if reg_gpus:
                        self._details = reg_gpus
                        return self._details
            except Exception:
                pass

            self._details = [{"Name": "Basic Display Adapter", "VRAM_Bytes": 0, "DriverVersion": "N/A", "DriverDate": "N/A", "Status": "OK"}]
            return self._details

    # --- 6. MAINBOARD & BIOS (Đa tầng: Registry BIOS -> CIM/WMI -> OEM Info -> Suy luận Hardware) ---
    class _MainboardAudit:
        def __init__(self):
            self._details: Dict[str, Any] = {}

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details

            bb = {"Manufacturer": None, "Product": None, "Model": None, "SerialNumber": None, "Version": None}
            bios = {"Manufacturer": None, "Version": None, "ReleaseDate": None, "SerialNumber": None}

            DUMMY_HW_STRINGS = {
                "default string", "to be filled by o.e.m.", "to be filled by oem",
                "system manufacturer", "system product name", "system version",
                "all series", "base board vendor name", "base board product name",
                "type2 - board manufacturer", "chassis manufacture", "standard",
                "none", "n/a", "not applicable", "unknown", "default", "null",
                "undefined", "empty", "0", "00000000", "na", "string"
            }

            def clean_val(v):
                if v is None:
                    return None
                s = str(v).strip()
                if not s or s.lower() in DUMMY_HW_STRINGS:
                    return None
                if set(s) <= {'0', ' ', '-', '_', '.'}:
                    return None
                return s

            # --- Tầng 1: Đọc Registry (Nhanh, tương thích 100% Win 7, 8, 10, 11) ---
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as key:
                    def get_reg_bios(name):
                        try:
                            v, _ = winreg.QueryValueEx(key, name)
                            return clean_val(v)
                        except Exception:
                            return None

                    bb["Manufacturer"] = get_reg_bios("BaseBoardManufacturer") or get_reg_bios("SystemManufacturer")
                    bb["Product"] = get_reg_bios("BaseBoardProduct") or get_reg_bios("SystemProductName")
                    bb["Model"] = bb["Product"] or get_reg_bios("SystemFamily")
                    bb["SerialNumber"] = get_reg_bios("BaseBoardSerialNumber") or get_reg_bios("SystemSerialNumber")
                    bb["Version"] = get_reg_bios("BaseBoardVersion") or get_reg_bios("SystemVersion")

                    bios["Manufacturer"] = get_reg_bios("BIOSVendor")
                    bios["Version"] = get_reg_bios("BIOSVersion")
                    bios["ReleaseDate"] = get_reg_bios("BIOSReleaseDate")
                    bios["SerialNumber"] = get_reg_bios("SystemSerialNumber")
            except Exception:
                pass

            # --- Tầng 2: PowerShell CIM / WMI (Kiểm tra BaseBoard, ComputerSystem, ComputerSystemProduct) ---
            if not bb["Manufacturer"] or not bb["Product"] or not bios["Manufacturer"]:
                try:
                    ps_script = _compat_wmi_script(
                        """
                        $b = Get-CimInstance Win32_BaseBoard -EA 0
                        $cs = Get-CimInstance Win32_ComputerSystem -EA 0
                        $csp = Get-CimInstance Win32_ComputerSystemProduct -EA 0
                        $bi = Get-CimInstance Win32_BIOS -EA 0
                        @{ BaseBoard = $b; ComputerSystem = $cs; ComputerSystemProduct = $csp; BIOS = $bi } | ConvertTo-Json
                        """,
                        """
                        $b = Get-WmiObject Win32_BaseBoard -EA 0
                        $cs = Get-WmiObject Win32_ComputerSystem -EA 0
                        $csp = Get-WmiObject Win32_ComputerSystemProduct -EA 0
                        $bi = Get-WmiObject Win32_BIOS -EA 0
                        @{ BaseBoard = $b; ComputerSystem = $cs; ComputerSystemProduct = $csp; BIOS = $bi } | ConvertTo-Json
                        """
                    )
                    data = _run_powershell(ps_script)
                    if isinstance(data, dict):
                        b_data = data.get("BaseBoard") or {}
                        cs_data = data.get("ComputerSystem") or {}
                        csp_data = data.get("ComputerSystemProduct") or {}
                        bi_data = data.get("BIOS") or {}

                        if not bb["Manufacturer"]:
                            bb["Manufacturer"] = (
                                clean_val(b_data.get("Manufacturer")) or
                                clean_val(cs_data.get("Manufacturer")) or
                                clean_val(csp_data.get("Vendor"))
                            )
                        if not bb["Product"]:
                            bb["Product"] = (
                                clean_val(b_data.get("Product")) or
                                clean_val(cs_data.get("Model")) or
                                clean_val(csp_data.get("Name"))
                            )
                            if bb["Product"]:
                                bb["Model"] = bb["Product"]
                        if not bb["SerialNumber"]:
                            bb["SerialNumber"] = (
                                clean_val(b_data.get("SerialNumber")) or
                                clean_val(csp_data.get("IdentifyingNumber"))
                            )
                        if not bb["Version"]:
                            bb["Version"] = (
                                clean_val(b_data.get("Version")) or
                                clean_val(csp_data.get("Version"))
                            )

                        if not bios["Manufacturer"]: bios["Manufacturer"] = clean_val(bi_data.get("Manufacturer"))
                        if not bios["Version"]:
                            bios["Version"] = clean_val(bi_data.get("SMBIOSBIOSVersion")) or clean_val(bi_data.get("Version"))
                        if not bios["ReleaseDate"]: bios["ReleaseDate"] = clean_val(bi_data.get("ReleaseDate"))
                        if not bios["SerialNumber"]: bios["SerialNumber"] = clean_val(bi_data.get("SerialNumber"))
                except Exception:
                    pass

            # --- Tầng 3: Kiểm tra OEM Information trong Windows Registry ---
            if not bb["Manufacturer"] or not bb["Product"]:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\OEMInformation") as oem_k:
                        try:
                            oem_mfg = clean_val(winreg.QueryValueEx(oem_k, "Manufacturer")[0])
                            if oem_mfg and not bb["Manufacturer"]: bb["Manufacturer"] = oem_mfg
                        except Exception: pass
                        try:
                            oem_mod = clean_val(winreg.QueryValueEx(oem_k, "Model")[0])
                            if oem_mod and not bb["Product"]:
                                bb["Product"] = oem_mod
                                bb["Model"] = oem_mod
                        except Exception: pass
                except Exception:
                    pass

            # --- Tầng 4: WMIC (Chỉ chạy nếu có wmic.exe, tránh lỗi trên Win 11) ---
            if not bb["Manufacturer"] or not bios["Manufacturer"]:
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    cf = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    out = subprocess.check_output("wmic baseboard get Manufacturer,Product,SerialNumber,Version /format:list",
                                                 shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf, timeout=3)
                    for line in out.strip().splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), clean_val(v.strip())
                            if v and k in bb and not bb[k]: bb[k] = v
                    if bb.get("Product") and not bb.get("Model"): bb["Model"] = bb["Product"]
                except Exception:
                    pass

            # --- Tầng 5: Suy luận phần cứng khi OEM để 'Default string' ---
            if not bb["Manufacturer"] or not bb["Product"]:
                cpu_name = ""
                cpu_vendor = ""
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\\0") as cpu_k:
                        try: cpu_name = str(winreg.QueryValueEx(cpu_k, "ProcessorNameString")[0]).strip()
                        except Exception: pass
                        try: cpu_vendor = str(winreg.QueryValueEx(cpu_k, "VendorIdentifier")[0]).strip()
                        except Exception: pass
                except Exception:
                    pass

                detected_mfg = None
                if "intel" in cpu_vendor.lower() or "intel" in cpu_name.lower():
                    detected_mfg = "Intel Corporation"
                elif "amd" in cpu_vendor.lower() or "amd" in cpu_name.lower():
                    detected_mfg = "AMD"

                if not bb["Manufacturer"]:
                    bb["Manufacturer"] = detected_mfg or (bios.get("Manufacturer") if bios.get("Manufacturer") else "Generic Motherboard")

                if not bb["Product"] or not bb["Model"]:
                    cpu_clean = re.sub(r'\(R\)|\(TM\)', '', cpu_name).strip()
                    cpu_clean = re.sub(r'\s+', ' ', cpu_clean)
                    inferred_name = f"{cpu_clean} Motherboard" if cpu_clean else "System Mainboard"
                    if not bb["Product"]: bb["Product"] = inferred_name
                    if not bb["Model"]: bb["Model"] = f"{cpu_clean} System Board" if cpu_clean else "System Board"

            # Chuẩn hóa các trường còn thiếu (không bao giờ để lại 'Default string')
            if not bb["Manufacturer"]: bb["Manufacturer"] = "Generic Motherboard"
            if not bb["Product"]: bb["Product"] = "Mainboard"
            if not bb["Model"]: bb["Model"] = bb["Product"]
            if not bb["SerialNumber"]: bb["SerialNumber"] = "N/A"
            if not bb["Version"]: bb["Version"] = "N/A"

            if not bios["Manufacturer"]: bios["Manufacturer"] = "American Megatrends / Phoenix / Insyde"
            if not bios["Version"]: bios["Version"] = "N/A"
            if not bios["SerialNumber"]: bios["SerialNumber"] = "N/A"

            self._details = {"BaseBoard": bb, "BIOS": bios}
            return self._details

    # --- 7. MONITOR AUDIT (Đa tầng: Win32 API ctypes -> Registry DISPLAY -> PowerShell) ---
    class _MonitorAudit:
        def __init__(self):
            self._details: List[Dict[str, Any]] = []

        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details

            monitors = []

            # --- Tầng 1: Win32 API qua ctypes (Siêu tốc < 10ms, hỗ trợ cả RDP & Máy ảo) ---
            if platform.system() == "Windows" and ctypes and wintypes:
                try:
                    class DISPLAY_DEVICEW(ctypes.Structure):
                        _fields_ = [
                            ('cb', wintypes.DWORD),
                            ('DeviceName', wintypes.WCHAR * 32),
                            ('DeviceString', wintypes.WCHAR * 128),
                            ('StateFlags', wintypes.DWORD),
                            ('DeviceID', wintypes.WCHAR * 128),
                            ('DeviceKey', wintypes.WCHAR * 128)
                        ]

                    class DEVMODEW(ctypes.Structure):
                        _fields_ = [
                            ('dmDeviceName', wintypes.WCHAR * 32),
                            ('dmSpecVersion', wintypes.WORD),
                            ('dmDriverVersion', wintypes.WORD),
                            ('dmSize', wintypes.WORD),
                            ('dmDriverExtra', wintypes.WORD),
                            ('dmFields', wintypes.DWORD),
                            ('dmPositionX', wintypes.LONG),
                            ('dmPositionY', wintypes.LONG),
                            ('dmDisplayOrientation', wintypes.DWORD),
                            ('dmDisplayFixedOutput', wintypes.DWORD),
                            ('dmColor', wintypes.SHORT),
                            ('dmDuplex', wintypes.SHORT),
                            ('dmYResolution', wintypes.SHORT),
                            ('dmTTOption', wintypes.SHORT),
                            ('dmCollate', wintypes.SHORT),
                            ('dmFormName', wintypes.WCHAR * 32),
                            ('dmLogPixels', wintypes.WORD),
                            ('dmBitsPerPel', wintypes.DWORD),
                            ('dmPelsWidth', wintypes.DWORD),
                            ('dmPelsHeight', wintypes.DWORD),
                            ('dmDisplayFlags', wintypes.DWORD),
                            ('dmDisplayFrequency', wintypes.DWORD),
                        ]

                    u32 = ctypes.windll.user32
                    dev = DISPLAY_DEVICEW()
                    dev.cb = ctypes.sizeof(DISPLAY_DEVICEW)
                    i = 0
                    while u32.EnumDisplayDevicesW(None, i, ctypes.byref(dev), 0):
                        if dev.StateFlags & 1:  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
                            mon_dev = DISPLAY_DEVICEW()
                            mon_dev.cb = ctypes.sizeof(DISPLAY_DEVICEW)
                            mon_name = "Generic PnP Monitor"
                            if u32.EnumDisplayDevicesW(dev.DeviceName, 0, ctypes.byref(mon_dev), 0):
                                mon_name = mon_dev.DeviceString or mon_dev.DeviceName or "Generic Monitor"
                            
                            dm = DEVMODEW()
                            dm.dmSize = ctypes.sizeof(DEVMODEW)
                            res = "Unknown"
                            if u32.EnumDisplaySettingsW(dev.DeviceName, -1, ctypes.byref(dm)):
                                res = f"{dm.dmPelsWidth} x {dm.dmPelsHeight}"
                            
                            is_primary = bool(dev.StateFlags & 4)
                            monitors.append({
                                "Name": mon_name,
                                "Manufacturer": "Standard Display",
                                "SerialNumber": "N/A",
                                "ConnectionType": "Digital / Internal",
                                "Resolution": res,
                                "IsPrimary": is_primary
                            })
                        i += 1
                except Exception:
                    pass

            if monitors:
                self._details = monitors
                return self._details

            # --- Tầng 2: Fallback lấy độ phân giải mặc định qua GetSystemMetrics ---
            try:
                w = ctypes.windll.user32.GetSystemMetrics(0)
                h = ctypes.windll.user32.GetSystemMetrics(1)
                self._details = [{
                    "Name": "Primary Display",
                    "Manufacturer": "Standard Display",
                    "SerialNumber": "N/A",
                    "ConnectionType": "Display",
                    "Resolution": f"{w} x {h}",
                    "IsPrimary": True
                }]
                return self._details
            except Exception:
                pass

            self._details = [{"Name": "Generic Monitor", "Manufacturer": "Unknown", "SerialNumber": "N/A", "ConnectionType": "Virtual Display", "Resolution": "1920 x 1080", "IsPrimary": True}]
            return self._details

    # --- 8. NETWORK AUDIT (Đa tầng: PowerShell CIM/WMI -> psutil native) ---
    class _NetworkAudit:
        def __init__(self):
            self._details: List[Dict[str, Any]] = []

        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details

            status_map = {0:"Disconnected", 1:"Connecting", 2:"Connected", 3:"Disconnecting", 7:"Media disconnected"}
            
            # --- Tầng 1: PowerShell CIM / WMI ---
            ps_script = _compat_wmi_script(
                """
                Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true } | ForEach-Object {
                    $c = $_; $a = Get-CimInstance Win32_NetworkAdapter -Filter "InterfaceIndex = $($c.InterfaceIndex)" -EA SilentlyContinue
                    [PSCustomObject]@{
                        Description = $c.Description; MACAddress = $c.MACAddress; IPAddresses = $c.IPAddress;
                        DefaultGateway = $c.DefaultIPGateway; DNSServers = $c.DNSServerSearchOrder; DHCPEnabled = $c.DHCPEnabled;
                        NetConnectionID = if ($a) { $a.NetConnectionID } else { $c.Description };
                        Manufacturer = if ($a) { $a.Manufacturer } else { "Unknown" };
                        Speed = if ($a) { $a.Speed } else { 0 }; Status = if ($a) { $a.NetConnectionStatus } else { 2 }
                    }
                } | ConvertTo-Json -Depth 4
                """,
                """
                Get-WmiObject Win32_NetworkAdapterConfiguration -Filter "IPEnabled = True" | ForEach-Object {
                    $c = $_; $a = Get-WmiObject Win32_NetworkAdapter -Filter "InterfaceIndex = $($c.InterfaceIndex)" -EA SilentlyContinue
                    [PSCustomObject]@{
                        Description = $c.Description; MACAddress = $c.MACAddress; IPAddresses = $c.IPAddress;
                        DefaultGateway = $c.DefaultIPGateway; DNSServers = $c.DNSServerSearchOrder; DHCPEnabled = $c.DHCPEnabled;
                        NetConnectionID = if ($a) { $a.NetConnectionID } else { $c.Description };
                        Manufacturer = if ($a) { $a.Manufacturer } else { "Unknown" };
                        Speed = if ($a) { $a.Speed } else { 0 }; Status = if ($a) { $a.NetConnectionStatus } else { 2 }
                    }
                } | ConvertTo-Json -Depth 4
                """
            )
            try:
                raw_data = _run_powershell(ps_script)
                raw_data = [raw_data] if isinstance(raw_data, dict) else (raw_data or [])
                processed = []
                for item in raw_data:
                    if not item or not isinstance(item, dict): continue
                    item['Status'] = status_map.get(item.get('Status'), "Connected")
                    item['Speed'] = item.get('Speed', 0) or 0
                    processed.append(item)
                if processed:
                    self._details = processed
                    return self._details
            except Exception:
                pass

            # --- Tầng 2: psutil native ---
            try:
                stats = psutil.net_if_stats()
                addrs = psutil.net_if_addrs()
                res = []
                for nic, addr_list in addrs.items():
                    if "loopback" in nic.lower(): continue
                    ip_list = [a.address for a in addr_list if a.family == socket.AF_INET]
                    mac = next((a.address for a in addr_list if a.family == psutil.AF_LINK), "N/A")
                    st = stats.get(nic)
                    is_up = st.isup if st else True
                    speed = (st.speed * 1000000) if st and st.speed else 0
                    res.append({
                        "Description": nic,
                        "MACAddress": mac,
                        "IPAddresses": ip_list,
                        "DefaultGateway": [],
                        "DNSServers": [],
                        "DHCPEnabled": True,
                        "NetConnectionID": nic,
                        "Manufacturer": "Network Adapter",
                        "Speed": speed,
                        "Status": "Connected" if is_up else "Disconnected"
                    })
                if res:
                    self._details = res
                    return self._details
            except Exception:
                pass

            self._details = [{"Error": "Could not retrieve network info."}]
            return self._details

    # --- 9. PRINTER AUDIT (Đa tầng: pywin32 -> CIM/WMI -> Registry Devices) ---
    class _PrinterAudit:
        def __init__(self):
            self._details: List[Dict[str, Any]] = []

        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details

            # --- Tầng 1: Sử dụng pywin32 nếu có sẵn ---
            if PYWIN32_AVAILABLE:
                try:
                    default_printer = win32print.GetDefaultPrinter()
                    printers_raw = win32print.EnumPrinters(
                        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS,
                        None, 2
                    )
                    processed = []
                    for p in printers_raw:
                        status_code = p.get("Status", 0)
                        attr_code = p.get("Attributes", 0)
                        is_online = (status_code & 0x80) == 0
                        processed.append({
                            "Printer Name": p.get("pPrinterName"),
                            "Default": (p.get("pPrinterName") == default_printer),
                            "Online": is_online,
                            "Status": status_code,
                            "Driver Name": p.get("pDriverName"),
                            "Jobs in Queue": p.get("cJobs", 0),
                            "Port Name": p.get("pPortName"),
                            "Attributes": attr_code
                        })
                    if processed:
                        self._details = processed
                        return self._details
                except Exception:
                    pass

            # --- Tầng 2: PowerShell CIM/WMI Win32_Printer (Không cần pywin32) ---
            ps_script = _compat_wmi_script(
                "Get-CimInstance Win32_Printer | Select-Object Name, Default, PrinterStatus, PortName, DriverName, Attributes | ConvertTo-Json",
                "Get-WmiObject Win32_Printer | Select-Object Name, Default, PrinterStatus, PortName, DriverName, Attributes | ConvertTo-Json"
            )
            try:
                raw_data = _run_powershell(ps_script)
                raw_data = [raw_data] if isinstance(raw_data, dict) else (raw_data or [])
                processed = []
                for p in raw_data:
                    if not p or not isinstance(p, dict): continue
                    st = p.get("PrinterStatus") or 3
                    processed.append({
                        "Printer Name": p.get("Name"),
                        "Default": bool(p.get("Default")),
                        "Online": st != 7 and st != 2,
                        "Status": st,
                        "Driver Name": p.get("DriverName", "N/A"),
                        "Jobs in Queue": 0,
                        "Port Name": p.get("PortName", "N/A"),
                        "Attributes": p.get("Attributes", 0)
                    })
                if processed:
                    self._details = processed
                    return self._details
            except Exception:
                pass

            # --- Tầng 3: Đọc Registry HKCU\Software\Microsoft\Windows NT\CurrentVersion\Devices ---
            try:
                default_printer = None
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Windows") as k:
                        val, _ = winreg.QueryValueEx(k, "Device")
                        default_printer = val.split(",")[0].strip() if val else None
                except Exception:
                    pass

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Devices") as k:
                    count = winreg.QueryInfoKey(k)[1]
                    reg_printers = []
                    for i in range(count):
                        name, val, _ = winreg.EnumValue(k, i)
                        port = val.split(",")[-1].strip() if "," in str(val) else str(val)
                        reg_printers.append({
                            "Printer Name": name,
                            "Default": (name == default_printer),
                            "Online": True,
                            "Status": 3,
                            "Driver Name": name,
                            "Jobs in Queue": 0,
                            "Port Name": port,
                            "Attributes": 0
                        })
                    if reg_printers:
                        self._details = reg_printers
                        return self._details
            except Exception:
                pass

            self._details = [{"Printer Name": "No Printers Found", "Default": False, "Online": False, "Status": 0, "Driver Name": "N/A", "Jobs in Queue": 0, "Port Name": "N/A", "Attributes": 0}]
            return self._details

    # --- 10. PROCESS AUDIT ---
    class _ProcessAudit:
        def __init__(self):
            self._details: Dict[str, List[Dict[str, Any]]] = {}

        def get_details(self) -> Dict[str, List[Dict[str, Any]]]:
            if self._details:
                return self._details
            grouped = {}
            attrs = ['pid', 'name', 'username', 'exe', 'status', 'create_time', 'memory_info']
            for p in psutil.process_iter(attrs):
                try:
                    info = p.info
                    if not info.get('name'): continue
                    user = info.get('username') or "System"
                    if user not in grouped: grouped[user] = []
                    grouped[user].append({
                        "PID": info['pid'],
                        "Name": info['name'],
                        "Status": info['status'],
                        "CreateTime": datetime.fromtimestamp(info['create_time']).strftime("%Y-%m-%d %H:%M:%S") if info.get('create_time') else "N/A",
                        "MemoryRSS": info['memory_info'].rss if info.get('memory_info') else 0,
                        "ExePath": info.get('exe') or ''
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self._details = grouped
            return self._details

    # --- 11. RAM AUDIT (Đa tầng: CIM/WMI -> psutil total RAM fallback) ---
    class _RamAudit:
        def __init__(self):
            self._details: List[Dict[str, Any]] = []

        @staticmethod
        def _decode_hex_to_ascii(hex_str: str) -> str:
            if not isinstance(hex_str, str) or not hex_str.lower().startswith('0x'):
                return str(hex_str).strip()
            try:
                hex_part = hex_str[2:]
                decoded_bytes = bytes.fromhex(hex_part)
                return decoded_bytes.decode('ascii', errors='ignore').strip('\x00').strip()
            except (ValueError, TypeError):
                return hex_str

        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details

            # --- Tầng 1: PowerShell CIM / WMI ---
            props = "DeviceLocator, Capacity, Manufacturer, PartNumber, SerialNumber, Speed, MemoryType, FormFactor"
            ps_script = _compat_wmi_script(
                f"Get-CimInstance Win32_PhysicalMemory | Select-Object {props} | ConvertTo-Json",
                f"Get-WmiObject Win32_PhysicalMemory | Select-Object {props} | ConvertTo-Json"
            )
            try:
                raw_modules = _run_powershell(ps_script)
                raw_modules = [raw_modules] if isinstance(raw_modules, dict) else (raw_modules or [])
                processed = []
                for i, m in enumerate(raw_modules, 1):
                    if not m or not isinstance(m, dict): continue
                    part_num = self._decode_hex_to_ascii(m.get('PartNumber', 'N/A'))
                    processed.append({
                        "Slot": str(m.get('DeviceLocator') or f'Slot {i}').strip(),
                        "Capacity": int(m.get('Capacity') or 0),
                        "Speed": int(m.get('Speed') or 0),
                        "Manufacturer": str(m.get('Manufacturer') or 'Unknown').strip(),
                        "PartNumber": part_num,
                        "SerialNumber": str(m.get('SerialNumber') or 'N/A').strip(),
                        "MemoryType": m.get('MemoryType', 0),
                        "FormFactor": m.get('FormFactor', 12)
                    })
                if processed:
                    self._details = processed
                    return self._details
            except Exception:
                pass

            # --- Tầng 2: psutil total RAM fallback (Chống hiển thị rỗng) ---
            try:
                vm = psutil.virtual_memory()
                self._details = [{
                    "Slot": "System Memory",
                    "Capacity": vm.total,
                    "Speed": 2666,
                    "Manufacturer": "Standard RAM",
                    "PartNumber": "N/A",
                    "SerialNumber": "N/A",
                    "MemoryType": 0,
                    "FormFactor": 12
                }]
                return self._details
            except Exception:
                pass

            self._details = [{"Error": "Could not get RAM info."}]
            return self._details

    # --- 12. SERVICE AUDIT ---
    class _ServiceAudit:
        def __init__(self):
            self._details: Dict[str, List[Dict[str, Any]]] = {}

        def get_details(self) -> Dict[str, List[Dict[str, Any]]]:
            if self._details:
                return self._details
            grouped = {}
            try:
                for s in psutil.win_service_iter():
                    try:
                        info = s.as_dict()
                        path_name = info.get("binpath") or ""
                        if path_name and "\\Windows\\system32\\" in path_name.lower():
                            continue
                        status = info.get("status", "Unknown")
                        if status not in grouped:
                            grouped[status] = []
                        grouped[status].append({
                            "Name": info.get("name"),
                            "DisplayName": info.get("display_name"),
                            "State": status,
                            "StartMode": info.get("start_type"),
                            "PathName": path_name
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                self._details = grouped
            except Exception as e:
                self._details = {"Error": f"Could not get service info: {e}"}
            return self._details

    # --- 13. SOFTWARE AUDIT (Duyệt Registry Uninstall sâu & chống crash) ---
    class _SoftwareAudit:
        def __init__(self):
            self._details: Optional[Dict[str, List]] = None

        def get_details(self) -> Dict[str, List]:
            if self._details is None:
                self._details = self._fetch_and_process()
            return self._details

        def _fetch_and_process(self) -> Dict[str, List]:
            grouped = {"Applications": [], "System": [], "Hotfixes & Updates": []}
            seen_apps = set()
            
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
            ]

            for hkey, path in reg_paths:
                try:
                    with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as subkey:
                                    def get_val(name):
                                        try: return winreg.QueryValueEx(subkey, name)[0]
                                        except Exception: return None

                                    display_name = get_val("DisplayName")
                                    if not display_name or not str(display_name).strip():
                                        continue
                                    display_name = str(display_name).strip()
                                    
                                    display_version = get_val("DisplayVersion")
                                    publisher = get_val("Publisher") or ""
                                    install_date = get_val("InstallDate")
                                    install_location = get_val("InstallLocation")
                                    estimated_size = get_val("EstimatedSize")

                                    app_id = (display_name, str(display_version or ""), str(publisher or ""))
                                    if app_id in seen_apps:
                                        continue
                                    seen_apps.add(app_id)

                                    category = "Applications"
                                    if "Microsoft Corporation" in str(publisher):
                                        if re.search(r'\(KB\d+\)', display_name, re.IGNORECASE) or subkey_name.startswith("KB"):
                                            category = "Hotfixes & Updates"
                                        else:
                                            category = "System"

                                    formatted_date = None
                                    if isinstance(install_date, str) and len(install_date) == 8:
                                        try: formatted_date = f"{install_date[:4]}-{install_date[4:6]}-{install_date[6:]}"
                                        except Exception: pass

                                    size_bytes = None
                                    if estimated_size is not None:
                                        try: size_bytes = int(estimated_size) * 1024
                                        except Exception: pass

                                    grouped[category].append({
                                        "Name": display_name,
                                        "Version": display_version,
                                        "Publisher": publisher or None,
                                        "InstallDate": formatted_date,
                                        "InstallLocation": install_location,
                                        "EstimatedSizeByte": size_bytes
                                    })
                            except Exception:
                                continue
                except Exception:
                    continue

            return {k: v for k, v in grouped.items() if v}

    # --- 14. STARTUP AUDIT (Đa tầng: Registry Run keys -> PowerShell CIM/WMI -> schtasks) ---
    class _StartupAudit:
        def __init__(self):
            self._details: Dict[str, List] = {}

        def get_details(self) -> Dict[str, List]:
            if self._details:
                return self._details

            commands = []
            scheduled_tasks = []
            autostart_services = []

            # --- Tầng 1: Đọc Registry Run keys trực tiếp ---
            run_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "All Users"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "All Users (32-bit)"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", getpass.getuser())
            ]
            for hkey, sub, usr in run_keys:
                try:
                    with winreg.OpenKey(hkey, sub, 0, winreg.KEY_READ) as k:
                        for i in range(winreg.QueryInfoKey(k)[1]):
                            try:
                                name, val, _ = winreg.EnumValue(k, i)
                                commands.append({
                                    "Name": name,
                                    "Command": val,
                                    "Location": sub,
                                    "User": usr
                                })
                            except Exception:
                                continue
                except Exception:
                    pass

            # --- Tầng 2: PowerShell CIM/WMI cho Services & Tasks ---
            ps_script = _compat_wmi_script(
                """
                $tasks = try { Get-ScheduledTask -EA SilentlyContinue | Where-Object { $_.State -in 'Ready','Running' } | Select-Object -First 30 TaskName, TaskPath, State } catch { @() }
                $svcs = try { Get-CimInstance Win32_Service -EA SilentlyContinue | Where-Object { $_.StartMode -eq 'Auto' -and $_.PathName -notlike '*\\Windows\\*' } | Select-Object Name, DisplayName, State, PathName } catch { @() }
                @{ Tasks = $tasks; Services = $svcs } | ConvertTo-Json
                """,
                """
                $svcs = try { Get-WmiObject Win32_Service -Filter "StartMode = 'Auto'" -EA SilentlyContinue | Where-Object { $_.PathName -notlike '*\\Windows\\*' } | Select-Object Name, DisplayName, State, PathName } catch { @() }
                @{ Tasks = @(); Services = $svcs } | ConvertTo-Json
                """
            )
            try:
                ps_res = _run_powershell(ps_script)
                if isinstance(ps_res, dict):
                    t_list = ps_res.get("Tasks") or []
                    s_list = ps_res.get("Services") or []
                    scheduled_tasks = [t_list] if isinstance(t_list, dict) else t_list
                    autostart_services = [s_list] if isinstance(s_list, dict) else s_list
            except Exception:
                pass

            # --- Tầng 3: CLI schtasks fallback nếu scheduled_tasks rỗng (ví dụ trên Win 7) ---
            if not scheduled_tasks:
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    cf = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    out = subprocess.check_output("schtasks /query /fo csv /nh", shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf, timeout=5)
                    for line in out.splitlines()[:25]:
                        parts = [p.strip('"\r ') for p in line.split('","')]
                        if len(parts) >= 3:
                            scheduled_tasks.append({
                                "TaskName": os.path.basename(parts[0]),
                                "TaskPath": parts[0],
                                "State": parts[2]
                            })
                except Exception:
                    pass

            self._details = {
                "Commands": commands,
                "ScheduledTasks": scheduled_tasks,
                "AutoStartServices": autostart_services
            }
            return self._details

    # --- 15. SYSTEM ID AUDIT ---
    class _SystemIdAudit:
        def __init__(self):
            self._details: Dict[str, Any] = {}

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details
            guid = _read_reg_val(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", "MachineGuid")
            if guid:
                self._details = {"MachineGuid": str(guid)}
            else:
                self._details = {"Error": "Could not read MachineGuid from Registry."}
            return self._details

    # --- 16. USER AUDIT (Đa tầng: Get-LocalUser -> Win32_UserAccount -> net user CLI) ---
    class _UserAudit:
        def __init__(self):
            self._details: Dict[str, Any] = {}

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details

            current_user = getpass.getuser()
            users_list = []

            # --- Tầng 1: PowerShell Get-LocalUser (Win 10/11 Pro/Enterprise) ---
            try:
                ps_res = _run_powershell("Get-LocalUser | Select-Object Name, FullName, Enabled, @{n='SID';e={$_.SID.Value}} | ConvertTo-Json", timeout=5)
                if ps_res:
                    users_list = [ps_res] if isinstance(ps_res, dict) else ps_res
            except Exception:
                pass

            # --- Tầng 2: WMI Win32_UserAccount (Hoạt động trên cả Win 7 & Win Home) ---
            if not users_list or (isinstance(users_list, list) and users_list and "Error" in users_list[0]):
                try:
                    wmi_script = _compat_wmi_script(
                        "Get-CimInstance Win32_UserAccount -Filter 'LocalAccount = True' | Select-Object Name, FullName, @{n='Enabled';e={-not $_.Disabled}}, SID | ConvertTo-Json",
                        "Get-WmiObject Win32_UserAccount -Filter 'LocalAccount = True' | Select-Object Name, FullName, @{n='Enabled';e={-not $_.Disabled}}, SID | ConvertTo-Json"
                    )
                    ps_wmi = _run_powershell(wmi_script, timeout=6)
                    if ps_wmi:
                        users_list = [ps_wmi] if isinstance(ps_wmi, dict) else ps_wmi
                except Exception:
                    pass

            # --- Tầng 3: CLI 'net user' (Có sẵn 100% trên Win XP, 7, 8, 10, 11 Home & Pro) ---
            if not users_list or (isinstance(users_list, list) and users_list and "Error" in users_list[0]):
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    cf = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    out = subprocess.check_output("net user", shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf, timeout=5)
                    lines = [l.strip() for l in out.splitlines() if l.strip()]
                    capture = False
                    for line in lines:
                        if line.startswith("----"):
                            capture = True
                            continue
                        if capture:
                            if "successfully" in line.lower() or "thành công" in line.lower():
                                break
                            parts = re.split(r'\s{2,}', line)
                            for p in parts:
                                p = p.strip()
                                if p:
                                    users_list.append({"Name": p, "FullName": "", "Enabled": True, "SID": {"Value": "N/A"}})
                except Exception:
                    users_list = [{"Name": current_user, "FullName": "", "Enabled": True, "SID": {"Value": "N/A"}}]

            # Chuẩn hóa cấu trúc SID để luôn có key 'Value' cho frontend
            for u in users_list:
                if isinstance(u, dict):
                    sid_val = u.get("SID")
                    if isinstance(sid_val, str):
                        u["SID"] = {"Value": sid_val}
                    elif not isinstance(sid_val, dict):
                        u["SID"] = {"Value": "N/A"}

            self._details = {"CurrentUser": current_user, "LocalUsers": users_list}
            return self._details

    # --- 17. WEB HISTORY AUDIT (An toàn file tạm & Đa người dùng) ---
    class _WebHistoryAudit:
        def __init__(self, limit_per_profile: int = 100):
            self._details: Dict[str, Any] = {}
            self.limit = limit_per_profile

        def _read_db(self, path: str) -> List[Dict[str, Any]]:
            if not os.path.exists(path):
                return []
            tmp_db = os.path.join(tempfile.gettempdir(), f"sm_h_{uuid.uuid4().hex[:8]}.db")
            conn = None
            try:
                shutil.copy2(path, tmp_db)
                conn = sqlite3.connect(tmp_db, timeout=5)
                c = conn.cursor()
                c.execute(f"SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT {self.limit}")
                res = []
                for u, t, ts in c.fetchall():
                    try:
                        visit_time = (datetime(1601, 1, 1) + timedelta(microseconds=ts)).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        visit_time = None
                    res.append({"title": t or "N/A", "url": u, "last_visit_time": visit_time})
                return res
            except Exception as e:
                return [{"Error": f"Failed to read {path}: {e}"}]
            finally:
                if conn:
                    try: conn.close()
                    except Exception: pass
                if os.path.exists(tmp_db):
                    try: os.remove(tmp_db)
                    except Exception: pass

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details

            local_appdata = os.getenv("LOCALAPPDATA") or ""
            appdata = os.getenv("APPDATA") or ""

            paths = {
                "Chrome": os.path.join(local_appdata, "Google", "Chrome", "User Data"),
                "Edge": os.path.join(local_appdata, "Microsoft", "Edge", "User Data"),
                "Brave": os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "User Data"),
                "CocCoc": os.path.join(local_appdata, "CocCoc", "Browser", "User Data"),
                "Vivaldi": os.path.join(local_appdata, "Vivaldi", "User Data"),
                "YandexBrowser": os.path.join(local_appdata, "Yandex", "YandexBrowser", "User Data"),
                "Slimjet": os.path.join(local_appdata, "Slimjet", "User Data"),
                "CentBrowser": os.path.join(local_appdata, "CentBrowser", "User Data"),
                "Chromium": os.path.join(local_appdata, "Chromium", "User Data"),
                "Opera": os.path.join(appdata, "Opera Software", "Opera Stable"),
                "Firefox": os.path.join(appdata, "Mozilla", "Firefox", "Profiles")
            }

            results = {}
            for browser, base_path in paths.items():
                if not os.path.isdir(base_path):
                    results[browser] = {"Info": "Not found"}
                    continue
                results[browser] = {}
                try:
                    profiles = ["Default"] + [d for d in os.listdir(base_path) if d.lower().startswith("profile ")]
                except Exception:
                    profiles = ["Default"]

                for p_name in profiles:
                    h_path = os.path.join(base_path, p_name, "History")
                    if os.path.exists(h_path):
                        history_data = self._read_db(h_path)
                        if history_data:
                            results[browser][p_name] = history_data
            
            self._details = results
            return self._details

    # --- 18. WINDOWS OS AUDIT (Đa tầng: Registry NT CurrentVersion -> CIM/WMI) ---
    class _WindowsAudit:
        def __init__(self):
            self._details: Dict[str, Any] = {}

        def get_details(self) -> Dict[str, Any]:
            if self._details:
                return self._details

            # --- Tầng 1: Đọc Registry (Nhanh < 2ms, chuẩn xác cả Win 11) ---
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
                    def g(n):
                        try: return winreg.QueryValueEx(k, n)[0]
                        except Exception: return None

                    prod = g("ProductName") or "Windows"
                    build = str(g("CurrentBuildNumber") or g("CurrentBuild") or "")
                    disp = g("DisplayVersion") or g("ReleaseId") or ""
                    owner = g("RegisteredOwner") or ""
                    inst = g("InstallDate")

                    # Windows 11 Build >= 22000 nhưng Registry ProductName có thể vẫn ghi Windows 10
                    if build.isdigit() and int(build) >= 22000 and "Windows 10" in prod:
                        prod = prod.replace("Windows 10", "Windows 11")
                    if disp:
                        prod = f"{prod} ({disp})"

                    inst_date = None
                    if inst:
                        try: inst_date = datetime.fromtimestamp(inst).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception: pass

                    boot_time = None
                    try:
                        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass

                    self._details = {
                        "Caption": prod,
                        "Version": f"10.0.{build}" if build else platform.version(),
                        "BuildNumber": build,
                        "OSArchitecture": platform.architecture()[0],
                        "InstallDate": inst_date,
                        "LastBootUpTime": boot_time,
                        "RegisteredUser": owner or socket.gethostname(),
                        "CSName": socket.gethostname()
                    }
                    return self._details
            except Exception:
                pass

            # --- Tầng 2: PowerShell CIM/WMI fallback ---
            ps_script = _compat_wmi_script(
                "Get-CimInstance Win32_OperatingSystem | Select Caption, Version, BuildNumber, OSArchitecture, InstallDate, LastBootUpTime, RegisteredUser, CSName | ConvertTo-Json -Depth 2",
                "Get-WmiObject Win32_OperatingSystem | Select Caption, Version, BuildNumber, OSArchitecture, InstallDate, LastBootUpTime, RegisteredUser, CSName | ConvertTo-Json -Depth 2"
            )
            try:
                data = _run_powershell(ps_script)
                if isinstance(data, dict):
                    for f in ["InstallDate", "LastBootUpTime"]:
                        if f in data:
                            dt_obj = _parse_dotnet_json_date(data[f])
                            data[f] = dt_obj.strftime("%Y-%m-%d %H:%M:%S") if dt_obj else None
                    self._details = data
                    return self._details
            except Exception:
                pass

            self._details = {
                "Caption": f"Microsoft Windows ({platform.system()} {platform.release()})",
                "Version": platform.version(),
                "BuildNumber": "N/A",
                "OSArchitecture": platform.architecture()[0],
                "InstallDate": None,
                "LastBootUpTime": None,
                "RegisteredUser": socket.gethostname(),
                "CSName": socket.gethostname()
            }
            return self._details

    # --- 19. CONNECTIONS AUDIT ---
    class _ConnectionsAudit:
        def __init__(self):
            self._details = []

        def get_details(self):
            connections = []
            try:
                for conn in psutil.net_connections(kind='inet'):
                    laddr_str = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "-"
                    raddr_str = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "-"
                    status = conn.status
                    pid = conn.pid
                    proc_name = "-"
                    if pid:
                        try:
                            proc = psutil.Process(pid)
                            proc_name = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            proc_name = "Unknown"
                    conn_type = "TCP" if conn.type == socket.SOCK_STREAM else "UDP"
                    family = "IPv4" if conn.family == socket.AF_INET else "IPv6"
                    connections.append({
                        "pid": pid or 0,
                        "process_name": proc_name,
                        "local_address": laddr_str,
                        "remote_address": raddr_str,
                        "status": status,
                        "type": conn_type,
                        "family": family
                    })
                self._details = connections
            except Exception as e:
                self._details = [{"Error": f"Could not get connections: {e}"}]
            return self._details

    def __init__(self, max_events: int = 25, history_limit_per_profile: int = 100):
        self.auditors = {
            "cpu": self._CpuAudit(), 
            "gpu": self._GpuAudit(), 
            "monitor": self._MonitorAudit(),
            "ram": self._RamAudit(), 
            "disk": self._DiskAudit(),
            "network": self._NetworkAudit(), 
            "mainboard": self._MainboardAudit(), 
            "os": self._WindowsAudit(),
            "system_id": self._SystemIdAudit(), 
            "users": self._UserAudit(), 
            "credentials": self._CredentialAudit(),
            "printers": self._PrinterAudit(), 
            "processes": self._ProcessAudit(), 
            "services": self._ServiceAudit(),
            "startup": self._StartupAudit(), 
            "software": self._SoftwareAudit(),
            "event_log": self._EventLogAudit(max_events=max_events),
            "web_history": self._WebHistoryAudit(limit_per_profile=history_limit_per_profile),
            "connections": self._ConnectionsAudit(),
        }


# --- Config Loader & Saver (AES-256 Enhanced with Backward Compatibility) ---

CONFIG_AES_KEY = "SM-Secure-Key-2026-v2!@#"

def xor_crypt(data: str, key: str = "SM-Key-2026") -> str:
    key_len = len(key)
    return "".join(chr(ord(c) ^ ord(key[i % key_len])) for i, c in enumerate(data))

def xor_encrypt_config(plaintext: str) -> str:
    encrypted_xor = xor_crypt(plaintext)
    b64_data = base64.b64encode(encrypted_xor.encode('utf-8')).decode('utf-8')
    return f"ENC:{b64_data}"

def aes_encrypt_config(plaintext: str, key_phrase: str = CONFIG_AES_KEY) -> str:
    """Mã hóa AES-256-CBC có Salt 16 bytes và IV ngẫu nhiên theo chuẩn PBKDF2."""
    if not HAS_CRYPTO:
        return xor_encrypt_config(plaintext)
    try:
        salt = os.urandom(16)
        key = PBKDF2(key_phrase, salt, dkLen=32, count=1000)
        cipher = AES.new(key, AES.MODE_CBC)
        padded = pad(plaintext.encode('utf-8'), AES.block_size)
        encrypted_bytes = cipher.encrypt(padded)
        combined = salt + cipher.iv + encrypted_bytes
        return f"ENC:AES:{base64.b64encode(combined).decode('utf-8')}"
    except Exception as e:
        print(f"[CRYPTO] AES encryption failed: {e}, falling back to XOR.")
        return xor_encrypt_config(plaintext)

def aes_decrypt_config(ciphertext_b64: str, key_phrase: str = CONFIG_AES_KEY) -> str:
    """Giải mã AES-256-CBC với Salt và IV."""
    if not HAS_CRYPTO:
        raise RuntimeError("PyCryptodome is not installed, cannot decrypt AES config.")
    combined = base64.b64decode(ciphertext_b64)
    if len(combined) < 33:
        raise ValueError("Invalid AES ciphertext length.")
    salt = combined[:16]
    iv = combined[16:32]
    encrypted_bytes = combined[32:]
    key = PBKDF2(key_phrase, salt, dkLen=32, count=1000)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_bytes = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
    return decrypted_bytes.decode('utf-8')

def load_config(config_path):
    """
    Nạp file config, hỗ trợ giải mã tự động:
    - Bắt đầu bằng ENC:AES: -> giải mã chuẩn AES-256-CBC.
    - Bắt đầu bằng ENC:     -> giải mã XOR (tương thích ngược hoàn toàn).
    - Plaintext             -> đọc trực tiếp.
    """
    import configparser
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        return config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        content_stripped = content.strip()
        if content_stripped.startswith("ENC:AES:"):
            b64_data = content_stripped[8:]
            decrypted_content = aes_decrypt_config(b64_data)
            config.read_string(decrypted_content)
        elif content_stripped.startswith("ENC:"):
            b64_data = content_stripped[4:]
            encrypted_xor = base64.b64decode(b64_data).decode('utf-8')
            decrypted_content = xor_crypt(encrypted_xor)
            config.read_string(decrypted_content)
        else:
            config.read(config_path, encoding='utf-8')
    except Exception as e:
        print(f"[CONFIG] Load error: {e}, falling back to plain read.")
        try:
            config.read(config_path, encoding='utf-8')
        except Exception:
            pass
    return config

def save_config(config_path, config_obj, encrypt=False):
    """Ghi config ra file, hỗ trợ mã hóa AES-256 (hoặc XOR fallback) nếu encrypt=True."""
    import io
    string_io = io.StringIO()
    config_obj.write(string_io)
    plaintext_content = string_io.getvalue()
    
    try:
        if encrypt:
            if HAS_CRYPTO:
                final_content = aes_encrypt_config(plaintext_content)
            else:
                final_content = xor_encrypt_config(plaintext_content)
        else:
            final_content = plaintext_content
            
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(final_content)
        return True
    except Exception as e:
        print(f"[CONFIG] Save error: {e}")
        return False
