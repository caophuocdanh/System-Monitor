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
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union

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
    class _Usage:

        _disk_name_cache = None

        @staticmethod
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
                        # Điều này loại bỏ các vấn đề về case-sensitivity
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
            return psutil.disk_usage('/').percent

        @staticmethod
        def get_disk_io_per_disk():
            """
            Trả về tốc độ đọc/ghi (bytes/s) cho TẤT CẢ các ổ đĩa vật lý,
            sử dụng tên hiển thị dạng [index] Model Name.
            """
            # Lấy map từ key chuẩn hóa sang tên model
            # Ví dụ: {'physicaldrive0': 'Model A', 'physicaldrive1': 'Model B'}
            disk_name_map = WindowsAuditor._Usage._get_disk_model_map()
            
            disk_io_start = psutil.disk_io_counters(perdisk=True)
            time.sleep(2)
            disk_io_end = psutil.disk_io_counters(perdisk=True)

            results = {}
            
            # Sắp xếp các key từ cache để đảm bảo thứ tự [0], [1], [2]... là nhất quán
            # Ví dụ: ['physicaldrive0', 'physicaldrive1', 'physicaldrive10']
            sorted_standardized_keys = sorted(disk_name_map.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))))
            
            # Lặp qua danh sách các key đã được sắp xếp
            for i, standardized_key in enumerate(sorted_standardized_keys):
                
                # Lấy tên model từ map
                model_name = disk_name_map.get(standardized_key, "Unknown Model")
                
                # --- LOGIC MỚI: TẠO TÊN HIỂN THỊ THEO ĐỊNH DẠNG MỚI ---
                display_name = f"[{i}] {model_name}"

                # Tra cứu thông tin I/O từ psutil bằng key không phân biệt chữ hoa/thường
                physical_name_from_psutil = None
                for psutil_key in disk_io_end.keys():
                    if psutil_key.lower() == standardized_key:
                        physical_name_from_psutil = psutil_key
                        break

                read_bps = 0
                write_bps = 0
                
                if physical_name_from_psutil:
                    start_io = disk_io_start.get(physical_name_from_psutil)
                    end_io = disk_io_end.get(physical_name_from_psutil)

                    if start_io and end_io:
                        read_bps = (end_io.read_bytes - start_io.read_bytes) / 2
                        write_bps = (end_io.write_bytes - start_io.write_bytes) / 2
                
                # Sử dụng display_name mới làm key
                results[display_name] = {
                    "read_bytes_per_sec": read_bps if read_bps > 0 else 0, 
                    "write_bytes_per_sec": write_bps if write_bps > 0 else 0
                }
            return results 
            
        @staticmethod
        def get_network_io_per_nic():
            """Trả về lưu lượng mạng (bits/s) cho tất cả các card mạng vật lý đang bật."""
            nic_stats = psutil.net_if_stats()
            net_io_start = psutil.net_io_counters(pernic=True)
            time.sleep(2)
            net_io_end = psutil.net_io_counters(pernic=True)

            results = {}
            # Lặp qua tất cả các NIC đang bật và không phải loopback
            for nic_name, stats in nic_stats.items():
                if stats.isup and "loopback" not in nic_name.lower():
                    start_io = net_io_start.get(nic_name)
                    end_io = net_io_end.get(nic_name)
                    
                    upload_bps = 0
                    download_bps = 0

                    if start_io and end_io:
                        upload_bps = (end_io.bytes_sent - start_io.bytes_sent) * 8 / 2
                        download_bps = (end_io.bytes_recv - start_io.bytes_recv) * 8 / 2
                    
                    # Luôn trả về kết quả cho NIC này
                    results[nic_name] = {
                        "upload_bits_per_sec": upload_bps if upload_bps > 0 else 0, 
                        "download_bits_per_sec": download_bps if download_bps > 0 else 0
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
            net_script = "Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType = 4' | Select-Object DeviceID, ProviderName | ConvertTo-Json"
            try:
                phys_disks = _run_powershell(phys_script, use_bypass=True) or []
                net_drives = _run_powershell(net_script) or []
                self._details = {"PhysicalDisks": [phys_disks] if isinstance(phys_disks, dict) else phys_disks, "NetworkDrives": [net_drives] if isinstance(net_drives, dict) else net_drives}
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

        def _decode_status(self, status_code: int) -> List[str]:
            status_map = {
                0x1: "Paused", 0x2: "Error", 0x4: "Pending Deletion", 0x8: "Paper Jam",
                0x10: "Paper Out", 0x20: "Manual Feed", 0x40: "Paper Problem", 0x80: "Offline",
                0x100: "IO Active", 0x200: "Busy", 0x400: "Printing", 0x800: "Output Bin Full",
                0x1000: "Not Available", 0x2000: "Waiting", 0x4000: "Processing", 0x8000: "Initializing",
                0x10000: "Warming Up", 0x20000: "Toner Low", 0x40000: "No Toner", 0x400000: "Output Bin Missing"
            }
            return [desc for bit, desc in status_map.items() if status_code & bit] or ["Ready"]

        def _decode_attributes(self, attr_code: int) -> List[str]:
            attr_map = {
                0x2: "Default", 0x4: "Shared", 0x8: "Hidden", 0x10: "Printer Fax",
                0x20: "Network", 0x40: "Enable Dev Query", 0x100: "Direct", 0x200: "Keep Printed Jobs",
                0x400: "Do Complete First", 0x800: "Work Offline", 0x1000: "Enable BIDI",
                0x2000: "Raw Only", 0x4000: "Published", 0x8000: "Enable Shared",
                0x10000: "Hidden Devmode", 0x20000: "Raw Queue", 0x40000: "Local"
            }
            return [desc for bit, desc in attr_map.items() if attr_code & bit]

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
                    status_list = self._decode_status(p.get("Status", 0))
                    attr_code = p.get("Attributes", 0)
                    attr_list = self._decode_attributes(attr_code)
                    is_offline = "Offline" in status_list

                    processed.append({
                        "Printer Name": p.get("pPrinterName"),
                        "Default": (p.get("pPrinterName") == default_printer),
                        "Online": not ("Offline" in status_list),
                        "Status": ", ".join(status_list),
                        "Driver Name": p.get("pDriverName"),
                        "Jobs in Queue": p.get("cJobs", 0),
                        "Port Name": p.get("pPortName"),
                        "Attributes": attr_code,
                        "Attributes Array": attr_list
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
        def _decode_manufacturer(code: str) -> str:
            manufacturer_map = {
                "0x0101": "AMD", "0x010B": "Nanya Technology", "0x012C": "Micron Technology", "0x0134": "Fujitsu", "0x0145": "SanDisk / Western Digital", "0x014F": "Transcend Information", "0x0198": "Kingston / Kioxia", "0x01AD": "SK Hynix", "0x01CE": "Samsung Electronics", "0x01DA": "Renesas Technology",
                "0x020D": "Spectek", "0x022D": "Nvidia", "0x02A4": "PNY Technologies", "0x02C0": "Micron Technology", "0x02E0": "Infineon Technologies", "0x0351": "Patriot Memory", "0x039E": "ADATA Technology", "0x040B": "Apacer Technology", "0x0434": "GeIL (Golden Emperor)", "0x04CD": "G.Skill",
                "0x04D2": "Winbond", "0x050D": "Team Group", "0x0539": "Virtium", "0x05CB": "Crucial Technology", "0x065B": "Kingston", "0x079D": "Mushkin", "0x8001": "AMD", "0x800B": "Nanya Technology", "0x802C": "Micron Technology", "0x803F": "Intel",
                "0x80AD": "SK Hynix", "0x80CE": "Samsung Electronics", "0x80E0": "Infineon Technologies", "0x859B": "Kingston", "0x7F7F7F9E": "ADATA Technology", "0x7F9D": "Corsair", "1337": "Kingmax Semiconductor", "1900": "Kingston", "0443": "G.Skill", "0x0000": "Unspecified",
                "0xFFFF": "Unspecified", "Unknown": "Unknown Manufacturer"
            }
            return manufacturer_map.get(code, code)

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
            type_map = {20:"DDR", 21:"DDR2", 24:"DDR3", 26:"DDR4", 28:"DDR5", 34: "LPDDR4"}
            form_map = {8:"DIMM", 9:"SODIMM", 12:"LRDIMM"}

            try:
                raw_modules = _run_powershell(cmd)
                raw_modules = [raw_modules] if isinstance(raw_modules, dict) else (raw_modules or [])
                
                processed_modules = []
                for i, module in enumerate(raw_modules, 1):
                    manufacturer = self._decode_manufacturer(module.get('Manufacturer', 'N/A'))
                    part_number = self._decode_hex_to_ascii(module.get('PartNumber', 'N/A'))

                    processed_modules.append({
                        "Slot": module.get('DeviceLocator', f'Slot {i}').strip(), 
                        "Capacity": int(module.get('Capacity', 0)),
                        "Speed": module.get('Speed', 0), 
                        "Manufacturer": manufacturer,
                        "PartNumber": part_number,
                        "SerialNumber": str(module.get('SerialNumber', 'N/A')).strip(),
                        "MemoryType": type_map.get(module.get('MemoryType'), "Unknown"), 
                        "FormFactor": form_map.get(module.get('FormFactor'), "Unknown")
                    })
                self._details = processed_modules
            except Exception as e: 
                self._details = [{"Error": f"Could not get RAM info: {e}"}]
            return self._details

    class _ServiceAudit:
        def __init__(self): self._details: Dict[str, List[Dict[str, Any]]] = {}
        def get_details(self) -> Dict[str, List[Dict[str, Any]]]:
            if self._details: return self._details
            ps_script = "Get-CimInstance Win32_Service | Where-Object { $_.PathName -and $_.PathName -notlike '*\\Windows\\system32\\*' } | Select-Object Name,DisplayName,State,StartMode,PathName | ConvertTo-Json"
            try:
                raw = _run_powershell(ps_script)
                raw = [raw] if isinstance(raw, dict) else (raw or [])
                grouped = {}
                for s in raw:
                    status = s.get("State", "Unknown")
                    if status not in grouped: grouped[status] = []
                    grouped[status].append(s)
                self._details = grouped
            except Exception as e: self._details = {"Error": f"Could not get service info: {e}"}
            return self._details

    class _SoftwareAudit:
        """Một thư viện nhỏ để thu thập và phân loại phần mềm đã cài đặt trên Windows."""
        
        def __init__(self):
            self._details: Optional[Dict[str, List]] = None

        def get_details(self) -> Dict[str, List]:
            """
            Trả về một dictionary chứa thông tin phần mềm đã được phân loại.
            Kết quả được cache lại sau lần gọi đầu tiên.
            """
            if self._details is None:
                self._details = self._fetch_and_process()
            return self._details

        def _fetch_and_process(self) -> Dict[str, List]:
            # ======================== PHẦN SỬA LỖI ========================
            # Script PowerShell được sửa lại để thu thập kết quả vào biến $apps
            # trước khi chuyển đổi sang JSON.
            ps_script = """
            $paths = @(
                'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
                'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
                'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
            );
            $apps = foreach ($path in $paths) {
                Get-ItemProperty $path -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName } |
                Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, InstallLocation, EstimatedSize
            }
            $apps | ConvertTo-Json -Depth 3 -Compress
            """
            # ==============================================================
            
            grouped = {"Applications": [], "System": [], "Hotfixes & Updates": [], "Errors": []}
            seen_apps = set()
            
            try:
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                completed = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_script],
                    capture_output=True, check=True, text=True, encoding='utf-8', errors='ignore',
                    startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW
                )
                raw_data = json.loads(completed.stdout.strip() or "[]")
                raw_apps = [raw_data] if isinstance(raw_data, dict) else raw_data
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
                error_msg = f"Lỗi khi thực thi PowerShell: {e}"
                if isinstance(e, subprocess.CalledProcessError) and e.stderr:
                    error_msg += f" | PowerShell Stderr: {e.stderr.strip()}"
                grouped["Errors"].append(error_msg)
                return {k: v for k, v in grouped.items() if v}

            # Phần xử lý logic bên dưới giữ nguyên vì nó đã đúng
            for app in raw_apps:
                name = (app.get("DisplayName") or "").strip()
                if not name: continue
                
                publisher = (app.get("Publisher") or "").strip()
                version = app.get("DisplayVersion")

                if (name, version, publisher) in seen_apps: continue
                seen_apps.add((name, version, publisher))

                category = "Applications"
                if "Microsoft Corporation" in publisher:
                    category = "Hotfixes & Updates" if re.search(r'\(KB\d+\)', name, re.IGNORECASE) else "System"

                install_date = None
                date_str = app.get("InstallDate")
                if isinstance(date_str, str) and len(date_str) == 8:
                    try: install_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
                    except ValueError: pass

                size_bytes = None
                size_kb = app.get("EstimatedSize")
                if size_kb is not None:
                    try: size_bytes = int(size_kb) * 1024
                    except (ValueError, TypeError): pass

                grouped[category].append({
                    "Name": name,
                    "Version": version,
                    "Publisher": publisher or None,
                    "InstallDate": install_date,
                    "InstallLocation": app.get("InstallLocation"),
                    "EstimatedSizeByte": size_bytes
                })

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
                "Opera": os.path.join(os.getenv("APPDATA"), "Opera Software", "Opera Stable"),
                "CocCoc": os.path.join(os.getenv("LOCALAPPDATA"), "CocCoc", "Browser", "User Data"),
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
        }