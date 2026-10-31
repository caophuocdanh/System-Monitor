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
                            <!-- Đường dẫn Breadcrumb tương tác -->
                            <div id="file-path-nav" style="margin-bottom:0.85rem; font-family:var(--font-mono); font-size:0.9rem; background:rgba(125,125,125,0.06); padding:0.5rem 0.8rem; border-radius:6px; display:flex; align-items:center; gap:0.35rem; flex-wrap:wrap; border:1px solid rgba(125,125,125,0.12);">
                                <span style="font-weight:700; color:var(--color-text-muted); margin-right:4px;"><i class="fa-solid fa-location-dot"></i></span>
                                <div id="breadcrumb-container" style="display:flex; align-items:center; gap:0.35rem; flex-wrap:wrap;">
                                    <span class="breadcrumb-item" style="font-weight:700; color:var(--color-primary); cursor:pointer;" onclick="browseFiles('drives')"><i class="fa-solid fa-hard-drive"></i> Drives</span>
                                </div>
                            </div>
                            
                            <!-- Thanh công cụ hành động -->
                            <div style="display:flex; gap:0.5rem; margin-bottom:1rem; align-items:center; flex-wrap:wrap;">
                                <button onclick="browseFiles('drives')" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem;" title="Xem danh sách các ổ đĩa"><i class="fa-solid fa-hard-drive"></i> Drives</button>
                                <button id="folder-up-btn" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem; display:none;" title="Lên thư mục cấp cha"><i class="fa-solid fa-arrow-up"></i> Up One Level</button>
                                <button id="folder-refresh-btn" onclick="refreshCurrentFolder()" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem;" title="Làm mới danh sách thư mục"><i class="fa-solid fa-rotate-right"></i> Refresh</button>
                                <button id="folder-create-btn" onclick="createNewFolder()" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem; display:none; background-color:#17a2b8;" title="Tạo thư mục mới tại đây"><i class="fa-solid fa-folder-plus"></i> New Folder</button>
                                <button id="file-upload-btn" onclick="triggerFileUpload()" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem; display:none; background-color:var(--color-primary);" title="Tải file từ máy bạn lên thư mục này"><i class="fa-solid fa-upload"></i> Upload File</button>
                                <button id="download-current-folder-btn" class="back-link" style="padding:0.4rem 0.8rem; font-size:0.8rem; display:none; background-color:var(--color-success);" title="Nén và tải về toàn bộ thư mục hiện tại dạng ZIP"><i class="fa-solid fa-file-zipper"></i> Download Folder (ZIP)</button>
                                
                                <input type="file" id="file-upload-input" style="display:none;" onchange="handleFileSelected(event)">
                                
                                <span id="file-status-indicator" style="display:none; font-size:0.85rem; color:var(--color-primary); font-weight:600; margin-left:auto;">
                                    <i class="fa-solid fa-spinner fa-spin"></i> <span id="file-status-text">Processing...</span>
                                </span>
                            </div>
                            
                            <div style="max-height:520px; overflow-y:auto; border-radius:6px; border:1px solid rgba(125,125,125,0.15);">
                                 <table class="table-responsive" style="width:100%; border-collapse:collapse; font-size:0.85rem;">
                                    <thead style="position:sticky; top:0; background:var(--color-bg); z-index:10; border-bottom:2px solid rgba(125,125,125,0.15);">
                                        <tr>
                                            <th style="text-align:left; padding:9px 12px; font-weight:700;">Name</th>
                                            <th style="text-align:left; padding:9px 12px; width:95px; font-weight:700;">Type</th>
                                            <th style="text-align:left; padding:9px 12px; width:115px; font-weight:700;">Size</th>
                                            <th style="text-align:center; padding:9px 12px; width:155px; font-weight:700;">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="file-table-body">
                                        <tr><td colspan="4" style="text-align:center; padding:1.5rem; color:var(--color-text-muted);">Click Drives to load.</td></tr>
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
    } else if (cmd === 'file_upload') {
        handleFileUploadResponse(res);
    } else if (cmd === 'file_delete') {
        handleFileDeleteResponse(res);
    } else if (cmd === 'create_folder') {
        handleCreateFolderResponse(res);
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

function renderBreadcrumbs(path) {
    const container = document.getElementById('breadcrumb-container');
    if (!container) return;

    if (!path || path === 'drives') {
        container.innerHTML = `<span style="font-weight:700; color:var(--color-primary); cursor:pointer;" onclick="browseFiles('drives')"><i class="fa-solid fa-hard-drive"></i> Drives</span>`;
        return;
    }

    let html = `<span style="color:var(--color-primary); cursor:pointer; font-weight:600;" onclick="browseFiles('drives')"><i class="fa-solid fa-hard-drive"></i> Drives</span>`;
    
    // Xử lý các thành phần của đường dẫn Windows (ví dụ C:\Users\Admin)
    const normalized = path.replace(/\//g, '\\');
    const parts = normalized.split('\\').filter(p => p);
    
    let accumulatedPath = '';
    for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        if (i === 0 && part.endsWith(':')) {
            accumulatedPath = part + '\\';
        } else {
            accumulatedPath += (accumulatedPath.endsWith('\\') ? '' : '\\') + part;
        }

        const isLast = (i === parts.length - 1);
        const escaped = accumulatedPath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        
        html += ` <span style="color:var(--color-text-muted);">\\</span> `;
        if (isLast) {
            html += `<span style="font-weight:700; color:var(--color-text);">${part}</span>`;
        } else {
            html += `<span style="color:var(--color-primary); cursor:pointer; font-weight:600;" onclick="browseFiles('${escaped}')">${part}</span>`;
        }
    }

    container.innerHTML = html;
}

function renderFileList(res) {
    const tbody = document.getElementById('file-table-body');
    const upBtn = document.getElementById('folder-up-btn');
    const downloadFolderBtn = document.getElementById('download-current-folder-btn');
    const uploadBtn = document.getElementById('file-upload-btn');
    const createFolderBtn = document.getElementById('folder-create-btn');

    if (res.type === 'drives') {
        currentDirPath = 'drives';
        renderBreadcrumbs('drives');
        
        if (upBtn) upBtn.style.display = 'none';
        if (downloadFolderBtn) downloadFolderBtn.style.display = 'none';
        if (uploadBtn) uploadBtn.style.display = 'none';
        if (createFolderBtn) createFolderBtn.style.display = 'none';

        tbody.innerHTML = res.items.map(drive => `
            <tr onclick="browseFiles('${drive.replace(/\\/g, '\\\\')}')" style="cursor:pointer;" class="file-row">
                <td style="padding:8px 12px; border-bottom:1px solid rgba(125,125,125,0.12); font-weight:600;"><i class="fa-solid fa-hard-drive" style="color:var(--color-primary); margin-right:6px;"></i> ${drive}</td>
                <td style="padding:8px 12px; border-bottom:1px solid rgba(125,125,125,0.12);">Drive</td>
                <td style="padding:8px 12px; border-bottom:1px solid rgba(125,125,125,0.12);">-</td>
                <td style="padding:8px 12px; border-bottom:1px solid rgba(125,125,125,0.12); text-align:center; color:#999;">-</td>
            </tr>
        `).join('');
    } else if (res.type === 'directory') {
        currentDirPath = res.path;
        renderBreadcrumbs(res.path);

        if (upBtn) upBtn.style.display = 'inline-block';
        if (downloadFolderBtn) {
            downloadFolderBtn.style.display = 'inline-block';
            downloadFolderBtn.onclick = () => downloadItem(currentDirPath, true);
        }
        if (uploadBtn) uploadBtn.style.display = 'inline-block';
        if (createFolderBtn) createFolderBtn.style.display = 'inline-block';
        
        // Sắp xếp: Thư mục trước, File sau
        res.items.sort((a, b) => {
            if (a.is_dir && !b.is_dir) return -1;
            if (!a.is_dir && b.is_dir) return 1;
            return a.name.localeCompare(b.name);
        });

        if (res.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--color-text-muted);">(Empty Directory)</td></tr>`;
            return;
        }

        tbody.innerHTML = res.items.map(item => {
            const icon = item.is_dir ? 'fa-folder' : 'fa-file';
            const iconColor = item.is_dir ? '#f39c12' : '#3498db';
            const fullItemPath = (res.path + (res.path.endsWith('\\') ? '' : '\\') + item.name);
            const escapedPath = fullItemPath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const clickAction = item.is_dir ? `onclick="browseFiles('${escapedPath}')"` : '';
            
            const downloadBtn = item.is_dir 
                ? `<button onclick="event.stopPropagation(); downloadItem('${escapedPath}', true)" title="Nén & Tải thư mục này (.zip)" style="padding:3px 7px; font-size:0.75rem; background:#6f42c1; color:white; border:none; border-radius:4px; cursor:pointer;"><i class="fa-solid fa-file-zipper"></i> ZIP</button>`
                : `<button onclick="event.stopPropagation(); downloadItem('${escapedPath}', false)" title="Tải file này về máy" style="padding:3px 7px; font-size:0.75rem; background:var(--color-primary); color:white; border:none; border-radius:4px; cursor:pointer;"><i class="fa-solid fa-download"></i> Tải về</button>`;

            const deleteBtn = `<button onclick="event.stopPropagation(); deleteItem('${escapedPath}', ${item.is_dir})" title="Xóa ${item.is_dir ? 'thư mục' : 'file'} này" style="padding:3px 7px; font-size:0.75rem; background:var(--color-danger); color:white; border:none; border-radius:4px; cursor:pointer; margin-left:4px;"><i class="fa-solid fa-trash-can"></i></button>`;

            return `
                <tr ${clickAction} style="cursor:${item.is_dir ? 'pointer' : 'default'};" class="file-row">
                    <td style="padding:7px 12px; border-bottom:1px solid rgba(125,125,125,0.12);">
                        <i class="fa-solid ${icon}" style="color:${iconColor}; margin-right:6px;"></i> 
                        <span style="font-weight:${item.is_dir ? '600' : 'normal'}">${item.name}</span>
                    </td>
                    <td style="padding:7px 12px; border-bottom:1px solid rgba(125,125,125,0.12); font-size:0.82rem; color:var(--color-text-muted);">${item.is_dir ? 'Folder' : 'File'}</td>
                    <td style="padding:7px 12px; border-bottom:1px solid rgba(125,125,125,0.12); font-size:0.82rem; font-family:var(--font-mono);">${item.is_dir ? '-' : formatBytes(item.size)}</td>
                    <td style="padding:7px 12px; border-bottom:1px solid rgba(125,125,125,0.12); text-align:center;">
                        ${downloadBtn}
                        ${deleteBtn}
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


function setFileStatus(show, text = '') {
    const statusEl = document.getElementById('file-status-indicator');
    const textEl = document.getElementById('file-status-text');
    if (!statusEl) return;
    if (show) {
        statusEl.style.display = 'inline-flex';
        if (textEl) textEl.innerText = text;
    } else {
        statusEl.style.display = 'none';
    }
}

function refreshCurrentFolder() {
    if (!currentDirPath || currentDirPath === 'drives') {
        browseFiles('drives');
    } else {
        browseFiles(currentDirPath);
    }
}

function createNewFolder() {
    if (!currentDirPath || currentDirPath === 'drives') {
        alert("Vui lòng mở một ổ đĩa hoặc thư mục cụ thể trước khi tạo thư mục mới.");
        return;
    }
    const folderName = prompt("Nhập tên thư mục mới cần tạo:");
    if (!folderName || !folderName.trim()) return;
    
    const sep = currentDirPath.endsWith('\\') ? '' : '\\';
    const targetPath = currentDirPath + sep + folderName.trim();
    setFileStatus(true, `Đang tạo thư mục: ${folderName.trim()}...`);
    sendRemoteCommand('create_folder', targetPath);
}

function handleCreateFolderResponse(res) {
    setFileStatus(false);
    if (res && res.success) {
        refreshCurrentFolder();
    } else {
        alert("Tạo thư mục thất bại: " + (res && res.error ? res.error : "Unknown error"));
    }
}

function triggerFileUpload() {
    if (!currentDirPath || currentDirPath === 'drives') {
        alert("Vui lòng mở một thư mục cụ thể trước khi tải file lên.");
        return;
    }
    const fileInput = document.getElementById('file-upload-input');
    if (fileInput) {
        fileInput.value = '';
        fileInput.click();
    }
}

function handleFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!currentDirPath || currentDirPath === 'drives') {
        alert("Vui lòng mở một thư mục cụ thể để tải file lên.");
        return;
    }

    if (file.size > 75 * 1024 * 1024) {
        alert(`File quá lớn (${(file.size / (1024 * 1024)).toFixed(1)}MB). Giới hạn tối đa là 75MB.`);
        return;
    }

    setFileStatus(true, `Đang đọc file ${file.name}...`);
    const reader = new FileReader();
    reader.onload = function(evt) {
        const base64Data = evt.target.result.split(',')[1];
        const sep = currentDirPath.endsWith('\\') ? '' : '\\';
        const targetPath = currentDirPath + sep + file.name;
        
        setFileStatus(true, `Đang truyền file ${file.name} lên máy trạm...`);
        sendRemoteCommand('file_upload', {
            path: targetPath,
            content: base64Data
        });
    };
    reader.onerror = function() {
        setFileStatus(false);
        alert("Không thể đọc file từ thiết bị của bạn.");
    };
    reader.readAsDataURL(file);
}

function handleFileUploadResponse(res) {
    setFileStatus(false);
    if (res && res.success) {
        alert("Tải lên file thành công!");
        refreshCurrentFolder();
    } else {
        alert("Tải lên thất bại: " + (res && res.error ? res.error : "Unknown error"));
    }
}

function deleteItem(itemPath, isFolder) {
    const typeLabel = isFolder ? "toàn bộ THƯ MỤC" : "FILE";
    const name = itemPath.split('\\').pop();
    if (!confirm(`Bạn có chắc chắn muốn XÓA vĩnh viễn ${typeLabel} "${name}" trên máy trạm không?\nHành động này không thể hoàn tác!`)) {
        return;
    }

    setFileStatus(true, `Đang xóa ${name}...`);
    sendRemoteCommand('file_delete', itemPath);
}

function handleFileDeleteResponse(res) {
    setFileStatus(false);
    if (res && res.success) {
        refreshCurrentFolder();
    } else {
        alert("Xóa thất bại: " + (res && res.error ? res.error : "Unknown error"));
    }
}
