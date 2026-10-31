/**
 * remote_control.js - Client-side logic for Remote Control features
 */

let ws = null;
let terminalOutput = null;

function initRemoteControl() {
    const container = document.getElementById('remote-control');
    if (!container) return;

    container.innerHTML = `
        <div class="remote-control-layout">
            <!-- Sidebar bên trái -->
            <div class="remote-sidebar">
                <div class="remote-status-box">
                    <span class="status-title">Connection Status</span>
                    <div id="ws-status" class="status-badge" style="background-color: #6c757d; margin-left: 0; text-align: center; width: 100%;">Connecting...</div>
                    <button id="reconnect-btn" class="reconnect-button-mini" style="display:none; margin-top: 0.5rem;">Reconnect</button>
                </div>
                
                <div class="remote-tabs">
                    <button class="remote-tab-btn active" onclick="openRemoteTab(event, 'remote-screenshot')">
                        <i class="fa-solid fa-camera"></i> Screenshot
                    </button>
                    <button class="remote-tab-btn" onclick="openRemoteTab(event, 'remote-processes')">
                        <i class="fa-solid fa-microchip"></i> Process Manager
                    </button>
                    <button class="remote-tab-btn" onclick="openRemoteTab(event, 'remote-terminal')">
                        <i class="fa-solid fa-terminal"></i> Remote Terminal
                    </button>
                    <button class="remote-tab-btn" onclick="openRemoteTab(event, 'remote-files')">
                        <i class="fa-solid fa-folder-open"></i> File Manager
                    </button>
                </div>
            </div>
            
            <!-- Content bên phải -->
            <div class="remote-content">
                <!-- Tab Screenshot -->
                <div id="remote-screenshot" class="remote-tab-panel active">
                    <div class="info-card">
                        <h2><i class="fa-solid fa-camera"></i> Screenshot</h2>
                        <div class="card-content" style="text-align:center;">
                            <div id="screenshot-container" style="border:1px solid #ddd; min-height:300px; display:flex; align-items:center; justify-content:center; background:#f8f9fa; position:relative; overflow:hidden;">
                                <p id="screenshot-msg">No screenshot yet. Click capture to take one.</p>
                                <img id="screenshot-img" style="max-width:100%; max-height: 500px; display:none; cursor:zoom-in;" onclick="viewLargeImage(this.src)">
                            </div>
                            <div style="margin-top:1rem; display:flex; gap:0.5rem; justify-content:center;">
                                <button onclick="sendRemoteCommand('screenshot')" class="back-link" style="background-color:var(--color-primary);">Capture Now</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Tab Process Manager -->
                <div id="remote-processes" class="remote-tab-panel">
                    <div class="info-card">
                        <h2><i class="fa-solid fa-microchip"></i> Process Manager</h2>
                        <div class="card-content">
                            <div style="display:flex; gap:0.5rem; margin-bottom:1rem;">
                                <input type="text" id="process-search" placeholder="Search by name..." style="flex-grow:1; padding:0.4rem; border-radius:4px; border:1px solid #ccc;">
                                <button onclick="sendRemoteCommand('process_list')" class="back-link" style="background-color:var(--color-primary); padding:0.4rem 0.8rem;">Refresh</button>
                            </div>
                            <div style="max-height:500px; overflow-y:auto;">
                                <table class="table-responsive" style="width:100%; border-collapse:collapse;">
                                    <thead style="position:sticky; top:0; background:#f8f9fa; z-index:10;">
                                        <tr>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd;">PID</th>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd;">Name</th>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd;">User</th>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd;">Action</th>
                                        </tr>
                                    </thead>
                                    <tbody id="process-table-body">
                                        <tr><td colspan="4" style="text-align:center; padding:1rem;">Click refresh to load.</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Tab Remote Terminal -->
                <div id="remote-terminal" class="remote-tab-panel">
                    <div class="info-card">
                        <h2><i class="fa-solid fa-terminal"></i> Remote Terminal</h2>
                        <div class="card-content">
                            <div style="display:flex; gap:1rem; margin-bottom:1rem;">
                                <select id="terminal-shell" style="padding:0.5rem; border-radius:4px;">
                                    <option value="cmd">CMD</option>
                                    <option value="powershell">PowerShell</option>
                                </select>
                                <input type="text" id="terminal-input" placeholder="Enter command..." style="flex-grow:1; padding:0.5rem; border-radius:4px; border:1px solid #ccc;">
                                <button id="terminal-send" class="back-link" style="background-color:var(--color-primary);">Run</button>
                            </div>
                            <pre id="terminal-output" style="background:#1e1e1e; color:#00ff00; padding:1rem; border-radius:4px; min-height:200px; max-height:500px; overflow-y:auto; font-family:var(--font-mono); font-size:0.9rem;">Ready...</pre>
                        </div>
                    </div>
                </div>
                
                <!-- Tab File Manager -->
                <div id="remote-files" class="remote-tab-panel">
                    <div class="info-card">
                        <h2><i class="fa-solid fa-folder-open"></i> File Manager</h2>
                        <div class="card-content">
                            <div id="file-path-nav" style="margin-bottom:1rem; font-weight:bold; font-family:var(--font-mono);">
                                Current Path: <span id="current-path">Drives</span>
                            </div>
                            <div style="display:flex; gap:0.5rem; margin-bottom:1rem; align-items:center; flex-wrap:wrap;">
                                <button onclick="browseFiles('drives')" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem;"><i class="fa-solid fa-hard-drive"></i> Drives</button>
                                <button id="folder-up-btn" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem; display:none;"><i class="fa-solid fa-arrow-up"></i> Up One Level</button>
                                <button id="download-current-folder-btn" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem; display:none; background-color: var(--color-success);" title="Nén và tải về toàn bộ thư mục hiện tại dạng ZIP">
                                    <i class="fa-solid fa-file-zipper"></i> Download Folder (ZIP)
                                </button>
                                <span id="file-download-status" style="display:none; font-size:0.85rem; color:var(--color-primary); font-weight:600;">
                                    <i class="fa-solid fa-spinner fa-spin"></i> <span id="file-download-text">Downloading...</span>
                                </span>
                            </div>
                            <div style="max-height:500px; overflow-y:auto;">
                                 <table class="table-responsive" style="width:100%; border-collapse:collapse;">
                                    <thead style="position:sticky; top:0; background:#f8f9fa; z-index:10;">
                                        <tr>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd;">Name</th>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd; width:90px;">Type</th>
                                            <th style="text-align:left; padding:8px; border-bottom:2px solid #ddd; width:110px;">Size</th>
                                            <th style="text-align:center; padding:8px; border-bottom:2px solid #ddd; width:120px;">Action</th>
                                        </tr>
                                    </thead>
                                    <tbody id="file-table-body">
                                        <tr><td colspan="4" style="text-align:center; padding:1rem;">Click Drives to load.</td></tr>
                                    </tbody>
                                 </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    terminalOutput = document.getElementById('terminal-output');
    
    document.getElementById('terminal-send').onclick = () => {
        const input = document.getElementById('terminal-input');
        const shell = document.getElementById('terminal-shell').value;
        if (input.value.trim()) {
            sendRemoteCommand('terminal', input.value.trim(), shell);
            appendToTerminal(`\n> ${input.value}\n`, '#ffffff');
            input.value = '';
        }
    };

    document.getElementById('terminal-input').onkeypress = (e) => {
        if (e.key === 'Enter') document.getElementById('terminal-send').click();
    };

    const processSearch = document.getElementById('process-search');
    if (processSearch) {
        processSearch.oninput = (e) => {
            filterProcessTable(e.target.value);
        };
    }

    document.getElementById('reconnect-btn').onclick = connectWS;

    connectWS();
}

window.openRemoteTab = function(evt, panelId) {
    document.querySelectorAll('.remote-tab-panel').forEach(panel => panel.classList.remove('active'));
    document.querySelectorAll('.remote-tab-btn').forEach(btn => btn.classList.remove('active'));
    
    const targetPanel = document.getElementById(panelId);
    if (targetPanel) targetPanel.classList.add('active');
    if (evt && evt.currentTarget) evt.currentTarget.classList.add('active');
    
    // Tự động load dữ liệu cho tab tương ứng
    if (panelId === 'remote-screenshot') {
        // user bấm Capture, không load tự động tránh nặng mạng
    } else if (panelId === 'remote-processes') {
        sendRemoteCommand('process_list');
    } else if (panelId === 'remote-files') {
        if (currentDirPath === '') {
            browseFiles('drives');
        }
    }
}

function viewLargeImage(src) {
    const overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.backgroundColor = 'rgba(0,0,0,0.85)';
    overlay.style.zIndex = '9999';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.cursor = 'zoom-out';
    overlay.onclick = () => document.body.removeChild(overlay);

    const img = document.createElement('img');
    img.src = src;
    img.style.maxWidth = '95%';
    img.style.maxHeight = '95%';
    img.style.border = '2px solid white';
    img.style.boxShadow = '0 0 20px rgba(0,0,0,0.5)';
    
    overlay.appendChild(img);
    document.body.appendChild(overlay);
}

function getResolvedWsUrl() {
    let rawUrl = (typeof WS_URL !== 'undefined' && WS_URL) ? WS_URL : '';
    const currentHost = window.location.hostname;
    const isCurrentHostLocal = (currentHost === 'localhost' || currentHost === '127.0.0.1');

    try {
        if (!rawUrl) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${protocol}//${currentHost}:9630`;
        }
        
        const url = new URL(rawUrl);
        // Tự động thay thế localhost/127.0.0.1/0.0.0.0 bằng hostname/IP hiện tại nếu truy cập từ xa qua mạng LAN
        if ((url.hostname === '127.0.0.1' || url.hostname === 'localhost' || url.hostname === '0.0.0.0') && !isCurrentHostLocal) {
            url.hostname = currentHost;
        }
        
        // Hỗ trợ giao thức an toàn wss: nếu trang web tải qua https:
        if (window.location.protocol === 'https:' && url.protocol === 'ws:') {
            url.protocol = 'wss:';
        }

        return url.href;
    } catch (e) {
        console.warn("[Remote Control] Error resolving WS URL, fallback to current hostname:", e);
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${currentHost}:9630`;
    }
}

function connectWS() {
    if (ws) ws.close();

    const statusBadge = document.getElementById('ws-status');
    const reconnectBtn = document.getElementById('reconnect-btn');
    
    statusBadge.innerText = "Connecting...";
    statusBadge.style.backgroundColor = "#6c757d";
    reconnectBtn.style.display = "none";

    const targetUrl = getResolvedWsUrl();
    console.log("[Remote Control] Connecting to WebSocket:", targetUrl);

    try {
        ws = new WebSocket(targetUrl);
    } catch (err) {
        console.error("[Remote Control] WebSocket creation failed:", err);
        statusBadge.innerText = "Error";
        statusBadge.style.backgroundColor = "#dc3545";
        reconnectBtn.style.display = "inline-block";
        return;
    }

    ws.onopen = () => {
        console.log("WS Connected to", targetUrl);
        statusBadge.innerText = "Authenticating...";
        // Gửi tin nhắn login đầu tiên
        ws.send(jsonStr({
            type: "dashboard_login",
            guid: CLIENT_GUID,
            access_token: ACCESS_TOKEN
        }));
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("WS Received:", data.type);

        if (data.type === 'login_success') {
            statusBadge.innerText = "Connected";
            statusBadge.style.backgroundColor = "#28a745";
        } else if (data.type === 'remote_response') {
            handleRemoteResponse(data);
        } else if (data.type === 'metrics') {
            // Có thể dùng để update biểu đồ realtime nếu muốn
        }
    };

    ws.onclose = () => {
        console.log("WS Disconnected");
        statusBadge.innerText = "Disconnected";
        statusBadge.style.backgroundColor = "#dc3545";
        reconnectBtn.style.display = "inline-block";
    };

    ws.onerror = (err) => {
        console.error("WS Error:", err);
    };
}

function sendRemoteCommand(command, payload = null, shell = 'cmd') {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert("Not connected to server.");
        return;
    }

    ws.send(jsonStr({
        type: "remote_command",
        target_guid: CLIENT_GUID,
        command: command,
        payload: payload,
        shell: shell,
        access_token: ACCESS_TOKEN
    }));
}

function handleRemoteResponse(data) {
    const cmd = data.command;
    const res = data.result;

    if (data.error) {
        alert("Error: " + data.error);
        return;
    }

    if (cmd === 'terminal') {
        if (res.error) {
            appendToTerminal(`Error: ${res.error}\n`, '#ff4444');
        } else {
            if (res.stdout) appendToTerminal(res.stdout, '#00ff00');
            if (res.stderr) appendToTerminal(res.stderr, '#ffbb33');
            appendToTerminal(`[Exit Code: ${res.exit_code}]\n`, '#888');
        }
    } else if (cmd === 'process_list') {
        renderProcessList(res);
    } else if (cmd === 'kill_process') {
        if (res.success) {
            alert("Process terminated.");
            sendRemoteCommand('process_list');
        } else {
            alert("Failed to terminate process.");
        }
    } else if (cmd === 'screenshot') {
        const img = document.getElementById('screenshot-img');
        const msg = document.getElementById('screenshot-msg');
        if (res.image) {
            img.src = "data:image/jpeg;base64," + res.image;
            img.style.display = "block";
            msg.style.display = "none";
        } else {
            alert("Failed to capture screenshot.");
        }
    } else if (cmd === 'file_browse') {
        renderFileList(res);
    } else if (cmd === 'file_download') {
        handleFileDownloadResponse(res);
    }
}

function appendToTerminal(text, color) {
    const span = document.createElement('span');
    span.style.color = color;
    span.innerText = text;
    terminalOutput.appendChild(span);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

let fullProcessList = [];

function renderProcessList(list) {
    fullProcessList = list || [];
    const searchInput = document.getElementById('process-search');
    filterProcessTable(searchInput ? searchInput.value : '');
}

function filterProcessTable(searchTerm) {
    const tbody = document.getElementById('process-table-body');
    if (!tbody) return;

    const term = (searchTerm || '').toLowerCase();
    
    const filtered = fullProcessList.filter(p => 
        p.name.toLowerCase().includes(term) || 
        String(p.pid).includes(term) ||
        (p.user && p.user.toLowerCase().includes(term))
    );

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:1rem;">${fullProcessList.length > 0 ? 'No matches found.' : 'No processes found.'}</td></tr>`;
        return;
    }

    // Sắp xếp theo tên
    filtered.sort((a, b) => a.name.localeCompare(b.name));

    tbody.innerHTML = filtered.map(p => `
        <tr>
            <td style="padding:8px; border-bottom:1px solid #eee;">${p.pid}</td>
            <td style="padding:8px; border-bottom:1px solid #eee; font-weight:600;">${p.name}</td>
            <td style="padding:8px; border-bottom:1px solid #eee; font-size:0.85rem; color:#666;">${p.user || 'N/A'}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">
                <button onclick="sendRemoteCommand('kill_process', ${p.pid})" style="padding:2px 8px; background:#dc3545; color:white; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">Kill</button>
            </td>
        </tr>
    `).join('');
}

let currentDirPath = '';

function renderFileList(res) {
    const tbody = document.getElementById('file-table-body');
    const pathSpan = document.getElementById('current-path');
    const upBtn = document.getElementById('folder-up-btn');

    if (res.type === 'drives') {
        currentDirPath = 'drives';
        pathSpan.innerText = 'Drives';
        upBtn.style.display = 'none';
        const downloadFolderBtn = document.getElementById('download-current-folder-btn');
        if (downloadFolderBtn) downloadFolderBtn.style.display = 'none';

        tbody.innerHTML = res.items.map(drive => `
            <tr onclick="browseFiles('${drive.replace(/\\/g, '\\\\')}')" style="cursor:pointer;">
                <td style="padding:8px; border-bottom:1px solid #eee; font-weight:600;"><i class="fa-solid fa-hard-drive"></i> ${drive}</td>
                <td style="padding:8px; border-bottom:1px solid #eee;">Drive</td>
                <td style="padding:8px; border-bottom:1px solid #eee;">-</td>
                <td style="padding:8px; border-bottom:1px solid #eee; text-align:center; color:#999;">-</td>
            </tr>
        `).join('');
    } else if (res.type === 'directory') {
        currentDirPath = res.path;
        pathSpan.innerText = res.path;
        upBtn.style.display = 'inline-block';

        const downloadFolderBtn = document.getElementById('download-current-folder-btn');
        if (downloadFolderBtn) {
            downloadFolderBtn.style.display = 'inline-block';
            downloadFolderBtn.onclick = () => downloadItem(currentDirPath, true);
        }
        
        // Sắp xếp: Thư mục trước, File sau
        res.items.sort((a, b) => {
            if (a.is_dir && !b.is_dir) return -1;
            if (!a.is_dir && b.is_dir) return 1;
            return a.name.localeCompare(b.name);
        });

        if (res.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:1.5rem; color:#888;">(Empty Folder)</td></tr>`;
            return;
        }

        tbody.innerHTML = res.items.map(item => {
            const icon = item.is_dir ? 'fa-folder' : 'fa-file';
            const iconColor = item.is_dir ? '#f39c12' : '#3498db';
            const fullItemPath = (res.path + (res.path.endsWith('\\') ? '' : '\\') + item.name);
            const escapedPath = fullItemPath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const clickAction = item.is_dir ? `onclick="browseFiles('${escapedPath}')"` : '';
            
            const actionBtn = item.is_dir 
                ? `<button onclick="event.stopPropagation(); downloadItem('${escapedPath}', true)" class="btn-item-download" title="Nén & Tải thư mục này về (.zip)" style="padding:3px 8px; font-size:0.75rem; background:#6f42c1; color:white; border:none; border-radius:4px; cursor:pointer;"><i class="fa-solid fa-file-zipper"></i> ZIP</button>`
                : `<button onclick="event.stopPropagation(); downloadItem('${escapedPath}', false)" class="btn-item-download" title="Tải file này về" style="padding:3px 8px; font-size:0.75rem; background:var(--color-primary); color:white; border:none; border-radius:4px; cursor:pointer;"><i class="fa-solid fa-download"></i> Tải về</button>`;

            return `
                <tr ${clickAction} style="cursor:${item.is_dir ? 'pointer' : 'default'};">
                    <td style="padding:8px; border-bottom:1px solid #eee;">
                        <i class="fa-solid ${icon}" style="color:${iconColor}; margin-right:6px;"></i> 
                        <span style="font-weight:${item.is_dir ? '600' : 'normal'}">${item.name}</span>
                    </td>
                    <td style="padding:8px; border-bottom:1px solid #eee; font-size:0.85rem; color:#666;">${item.is_dir ? 'Folder' : 'File'}</td>
                    <td style="padding:8px; border-bottom:1px solid #eee; font-size:0.85rem; font-family:var(--font-mono);">${item.is_dir ? '-' : formatBytes(item.size)}</td>
                    <td style="padding:8px; border-bottom:1px solid #eee; text-align:center;">
                        ${actionBtn}
                    </td>
                </tr>
            `;
        }).join('');
    } else if (res.error) {
        alert("Error: " + res.error);
    }
}

function browseFiles(path) {
    sendRemoteCommand('file_browse', path);
}

// Hàm đi lên 1 thư mục
document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'folder-up-btn') {
        if (!currentDirPath || currentDirPath === 'drives') return;
        
        // Xử lý path Windows
        let parts = currentDirPath.split('\\').filter(p => p);
        if (parts.length <= 1) {
            browseFiles('drives');
        } else {
            parts.pop();
            let newPath = parts.join('\\');
            if (newPath.length === 2 && newPath.endsWith(':')) newPath += '\\';
            browseFiles(newPath);
        }
    }
});

function jsonStr(obj) { return JSON.stringify(obj); }

function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}


// ==========================================
// CÁC HÀM DOWNLOAD FILE & FOLDER (ZIP)
// ==========================================
function setDownloadStatus(show, text = '') {
    const statusEl = document.getElementById('file-download-status');
    const textEl = document.getElementById('file-download-text');
    if (!statusEl) return;
    if (show) {
        statusEl.style.display = 'inline-flex';
        if (textEl) textEl.innerText = text;
    } else {
        statusEl.style.display = 'none';
    }
}

function downloadItem(filePath, isFolder = false) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert("Not connected to server.");
        return;
    }
    const label = isFolder ? "Nén thư mục thành ZIP & chuẩn bị tải..." : "Đang đọc file để tải về...";
    setDownloadStatus(true, label);
    sendRemoteCommand('file_download', filePath);
}

function handleFileDownloadResponse(res) {
    setDownloadStatus(false);
    if (!res || !res.success) {
        alert("Download thất bại: " + (res && res.error ? res.error : "Unknown error"));
        return;
    }

    try {
        downloadBase64File(res.content, res.filename);
        console.log(`[Remote Control] Downloaded ${res.filename} (${res.size || 'N/A'} bytes)`);
    } catch (e) {
        console.error("[Remote Control] Error saving downloaded file:", e);
        alert("Lỗi khi giải mã và lưu file: " + e.message);
    }
}

function downloadBase64File(base64Data, filename) {
    const byteCharacters = atob(base64Data);
    const byteArrays = [];
    const sliceSize = 1024;

    for (let offset = 0; offset < byteCharacters.length; offset += sliceSize) {
        const slice = byteCharacters.slice(offset, offset + sliceSize);
        const byteNumbers = new Array(slice.length);
        for (let i = 0; i < slice.length; i++) {
            byteNumbers[i] = slice.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        byteArrays.push(byteArray);
    }

    const mimeType = filename.endsWith('.zip') ? 'application/zip' : 'application/octet-stream';
    const blob = new Blob(byteArrays, { type: mimeType });
    const blobUrl = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
    }, 2000);
}
