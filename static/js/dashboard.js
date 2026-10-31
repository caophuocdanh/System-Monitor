// static/js/dashboard.js

document.addEventListener('DOMContentLoaded', () => {

    const DECOR_ICONS_UNICODE = [

        "⛲", "⛳", "⛺", "⛽", "⛪", "⚽", "⚾", "⛄", "⛅", "☔", "☕",

        "🌈", "🔥", "🌟", "💧", "🍀", "🍁", "🌻", "🌊", "🌙", "⭐",

        "🎯", "🎨", "🎉", "🪁", "🧩", "🛸", "🚀", "🌍", "🗻", "🌋"

    ];

    function getRandomDecorIcon() {

        const randomIndex = Math.floor(Math.random() * DECOR_ICONS_UNICODE.length);

        return DECOR_ICONS_UNICODE[randomIndex];

    }

    

    // Gán icon trang trí ngẫu nhiên cho mỗi stat-card khi trang tải

    document.querySelectorAll('.stat-card').forEach(card => {

        card.setAttribute('data-decor-icon', getRandomDecorIcon());

    });

    const clientsViewContainer = document.getElementById('clients-view-container');

    const clientsGrid = document.getElementById('clients-grid');

    const clientsTableWrapper = document.getElementById('clients-table-wrapper');

    const clientsTableBody = document.getElementById('clients-table-body');

    

    // Target các element mới trong stat cards

    const statElements = {

        total: {

            value: document.getElementById('stat-total-clients'),

            progress: document.getElementById('progress-total'),

            subtext: document.getElementById('subtext-total').querySelector('span')

        },

        online: {

            value: document.getElementById('stat-clients-online'),

            progress: document.getElementById('progress-online'),

            subtext: document.getElementById('subtext-online').querySelector('span')

        },

        records: {

            value: document.getElementById('stat-record-count'),

            progress: document.getElementById('progress-records'),

            subtext: document.getElementById('subtext-records').querySelector('span')

        },

        dbsize: {

            value: document.getElementById('stat-db-size'),

            progress: document.getElementById('progress-dbsize'),

            subtext: document.getElementById('subtext-dbsize').querySelector('span')

        }

    };

    // --- PHÂN TRANG BIẾN TOÀN CỤC ---

    let currentPage = 1;

    let totalPages = 1;

    const btnPrev = document.getElementById('btn-prev-page');

    const btnNext = document.getElementById('btn-next-page');

    function getUsageLevelClass(percentage) {

        if (percentage < 35) return 'level-low';

        if (percentage < 70) return 'level-medium';

        return 'level-high';

    }

    function timeAgo(timestamp) {

        if (!timestamp) return 'N/A';

        const now = new Date();

        const past = new Date(timestamp * 1000);

        const seconds = Math.floor((now - past) / 1000);

        if (seconds < 5) return "just now";

        if (seconds < 60) return `${seconds}s ago`;

        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;

        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;

        return `${Math.floor(seconds / 86400)}d ago`;

    }

    // ==========================================

    // 1. CHẾ ĐỘ LƯỚI THẺ (GRID CARD VIEW)

    // ==========================================

    function createClientCard(client) {

        const clientCard = document.createElement('div');

        clientCard.setAttribute('data-decor-icon', getRandomDecorIcon());

        updateClientCardContent(clientCard, client);

        return clientCard;

    }

    function updateClientCardContent(cardElement, client) {
        const statusClass = client.status.toLowerCase();
        cardElement.className = `client-card status-${statusClass}`;
        cardElement.dataset.guid = client.guid;

        const lastUpdate = timeAgo(client.metrics_timestamp);
        const cpu = parseFloat(client.cpu_usage) || 0;
        const ram = parseFloat(client.ram_usage) || 0;
        const disk = parseFloat(client.disk_usage) || 0;
        
        const cpuLevelClass = getUsageLevelClass(cpu);
        const ramLevelClass = getUsageLevelClass(ram);
        const diskLevelClass = getUsageLevelClass(disk);

        const currentInput = cardElement.querySelector('.username-input');
        const isEditing = currentInput && !currentInput.hasAttribute('readonly');

        if (!cardElement.querySelector('.client-card-header')) {
            cardElement.innerHTML = `
                <div class="client-card-header">
                    <div class="client-card-identity">
                        <div class="hostname-wrapper">
                            <i class="icon fa-solid fa-server"></i>
                            <p class="hostname">${client.hostname}</p>
                        </div>
                        <div class="username-wrapper">
                            <i class="icon fa-solid fa-user"></i>
                            <input type="text" class="username-input ip-font" value="${client.username}" readonly data-guid="${client.guid}">
                            <button class="edit-username-btn" title="Edit Username">
                                <i class="fa-solid fa-pencil"></i>
                            </button>
                        </div>
                    </div>
                    <div class="status-dot ${statusClass}"></div>
                </div>
                <div class="client-card-body">
                    <p><i class="icon fa-solid fa-desktop"></i> <span class="ip-font ip-local">${client.local_ip || 'N/A'}</span></p>
                    <p><i class="icon fa-solid fa-globe"></i> <span class="ip-font ip-wan">${client.wan_ip || 'N/A'}</span></p>
                </div>
                <div class="client-card-metrics">
                    <div class="metric-item metric-cpu ${cpuLevelClass}">
                        <div class="metric-icon"><i class="fa-solid fa-microchip"></i></div>
                        <div class="metric-value">${cpu.toFixed(1)}%</div>
                        <div class="metric-label">CPU</div>
                    </div>
                    <div class="metric-item metric-ram ${ramLevelClass}">
                        <div class="metric-icon"><i class="fa-solid fa-memory"></i></div>
                        <div class="metric-value">${ram.toFixed(1)}%</div>
                        <div class="metric-label">RAM</div>
                    </div>
                    <div class="metric-item metric-disk ${diskLevelClass}">
                        <div class="metric-icon"><i class="fa-solid fa-hard-drive"></i></div>
                        <div class="metric-value">${disk.toFixed(1)}%</div>
                        <div class="metric-label">Disk</div>
                    </div>
                </div>
                <div class="client-card-footer-wrapper">
                    <div class="client-card-status">
                        <span>Last update: ${lastUpdate}</span>
                    </div>
                    <div class="client-card-actions">
                        ${client.needs_update ? `
                        <button class="btn-icon btn-update" data-guid="${client.guid}" title="Phiên bản hiện tại: v${client.version || '1.0.0'} - Bấm để cập nhật">
                            <i class="fa-solid fa-cloud-arrow-down"></i>
                        </button>` : ''}
                        <a href="/client/${client.guid}" class="btn-icon btn-detail" title="View Details">
                            <i class="fa-solid fa-info"></i>
                        </a>
                        <button class="btn-icon btn-refresh" data-guid="${client.guid}" title="Refresh Data">
                            <i class="fa-solid fa-sync-alt"></i>
                        </button>
                        <button class="btn-icon btn-delete" data-guid="${client.guid}" title="Delete Client">
                            <i class="fa-solid fa-trash-alt"></i>
                        </button>
                    </div>
                </div>
            `;
            return;
        }

        // Targeted DOM update
        const hostEl = cardElement.querySelector('.hostname');
        if (hostEl && hostEl.textContent !== client.hostname) {
            hostEl.textContent = client.hostname;
        }

        if (!isEditing && currentInput) {
            if (currentInput.value !== client.username) {
                currentInput.value = client.username;
            }
            currentInput.defaultValue = client.username;
        }

        const statusDot = cardElement.querySelector('.status-dot');
        if (statusDot) {
            statusDot.className = `status-dot ${statusClass}`;
        }

        const localIp = cardElement.querySelector('.ip-local');
        if (localIp) {
            localIp.textContent = client.local_ip || 'N/A';
        }

        const wanIp = cardElement.querySelector('.ip-wan');
        if (wanIp) {
            wanIp.textContent = client.wan_ip || 'N/A';
        }

        const cpuItem = cardElement.querySelector('.metric-cpu');
        if (cpuItem) {
            cpuItem.className = `metric-item metric-cpu ${cpuLevelClass}`;
            const val = cpuItem.querySelector('.metric-value');
            if (val) val.textContent = `${cpu.toFixed(1)}%`;
        }

        const ramItem = cardElement.querySelector('.metric-ram');
        if (ramItem) {
            ramItem.className = `metric-item metric-ram ${ramLevelClass}`;
            const val = ramItem.querySelector('.metric-value');
            if (val) val.textContent = `${ram.toFixed(1)}%`;
        }

        const diskItem = cardElement.querySelector('.metric-disk');
        if (diskItem) {
            diskItem.className = `metric-item metric-disk ${diskLevelClass}`;
            const val = diskItem.querySelector('.metric-value');
            if (val) val.textContent = `${disk.toFixed(1)}%`;
        }

        const statusTime = cardElement.querySelector('.client-card-status span');
        if (statusTime) {
            statusTime.textContent = `Last update: ${lastUpdate}`;
        }

        // Cập nhật động nút CẬP NHẬT TỪNG MÁY
        const actionsEl = cardElement.querySelector('.client-card-actions');
        if (actionsEl) {
            let updateBtn = actionsEl.querySelector('.btn-update');
            if (client.needs_update) {
                const tooltipText = `Phiên bản hiện tại: v${client.version || '1.0.0'} - Bấm để cập nhật`;
                if (!updateBtn) {
                    updateBtn = document.createElement('button');
                    updateBtn.className = 'btn-icon btn-update';
                    updateBtn.dataset.guid = client.guid;
                    updateBtn.title = tooltipText;
                    updateBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i>';
                    actionsEl.insertBefore(updateBtn, actionsEl.firstChild);
                } else {
                    updateBtn.title = tooltipText;
                }
            } else if (updateBtn) {
                updateBtn.remove();
            }
        }
    }

    // ==========================================
    // 2. CHẾ ĐỘ BẢNG DANH SÁCH (TABLE / LIST ROW VIEW)
    // ==========================================
    function createClientRow(client) {
        const tr = document.createElement('tr');
        updateClientRowContent(tr, client);
        return tr;
    }

    function updateClientRowContent(rowElement, client) {
        const statusClass = client.status.toLowerCase();
        rowElement.className = `client-row status-${statusClass}`;
        rowElement.dataset.guid = client.guid;

        const lastUpdate = timeAgo(client.metrics_timestamp);
        const cpu = parseFloat(client.cpu_usage) || 0;
        const ram = parseFloat(client.ram_usage) || 0;
        const disk = parseFloat(client.disk_usage) || 0;
        
        const cpuLevelClass = getUsageLevelClass(cpu);
        const ramLevelClass = getUsageLevelClass(ram);
        const diskLevelClass = getUsageLevelClass(disk);

        const currentInput = rowElement.querySelector('.username-input');
        const isEditing = currentInput && !currentInput.hasAttribute('readonly');

        if (!rowElement.querySelector('.td-hostname')) {
            rowElement.innerHTML = `
                <td class="td-status">
                    <div class="status-dot ${statusClass}" title="${client.status}"></div>
                </td>
                <td class="td-hostname">
                    <div class="hostname-wrapper">
                        <i class="icon fa-solid fa-server"></i>
                        <span class="hostname">${client.hostname}</span>
                    </div>
                </td>
                <td class="td-username">
                    <div class="username-wrapper">
                        <i class="icon fa-solid fa-user"></i>
                        <input type="text" class="username-input ip-font" value="${client.username}" readonly data-guid="${client.guid}">
                        <button class="edit-username-btn" title="Edit Username">
                            <i class="fa-solid fa-pencil"></i>
                        </button>
                    </div>
                </td>
                <td class="td-ip"><span class="ip-local">${client.local_ip || 'N/A'}</span></td>
                <td class="td-ip"><span class="ip-wan">${client.wan_ip || 'N/A'}</span></td>
                <td class="td-metric metric-cpu ${cpuLevelClass}"><span class="metric-val">${cpu.toFixed(1)}%</span></td>
                <td class="td-metric metric-ram ${ramLevelClass}"><span class="metric-val">${ram.toFixed(1)}%</span></td>
                <td class="td-metric metric-disk ${diskLevelClass}"><span class="metric-val">${disk.toFixed(1)}%</span></td>
                <td class="td-time"><span class="time-ago">${lastUpdate}</span></td>
                <td class="td-actions">
                    <div class="client-card-actions">
                        ${client.needs_update ? `
                        <button class="btn-icon btn-update" data-guid="${client.guid}" title="Phiên bản hiện tại: v${client.version || '1.0.0'} - Bấm để cập nhật">
                            <i class="fa-solid fa-cloud-arrow-down"></i>
                        </button>` : ''}
                        <a href="/client/${client.guid}" class="btn-icon btn-detail" title="View Details">
                            <i class="fa-solid fa-info"></i>
                        </a>
                        <button class="btn-icon btn-refresh" data-guid="${client.guid}" title="Refresh Data">
                            <i class="fa-solid fa-sync-alt"></i>
                        </button>
                        <button class="btn-icon btn-delete" data-guid="${client.guid}" title="Delete Client">
                            <i class="fa-solid fa-trash-alt"></i>
                        </button>
                    </div>
                </td>
            `;
            return;
        }

        // Targeted Row Update
        const statusDot = rowElement.querySelector('.status-dot');
        if (statusDot) {
            statusDot.className = `status-dot ${statusClass}`;
            statusDot.title = client.status;
        }

        const hostEl = rowElement.querySelector('.hostname');
        if (hostEl && hostEl.textContent !== client.hostname) {
            hostEl.textContent = client.hostname;
        }

        if (!isEditing && currentInput) {
            if (currentInput.value !== client.username) {
                currentInput.value = client.username;
            }
            currentInput.defaultValue = client.username;
        }

        const localIp = rowElement.querySelector('.ip-local');
        if (localIp) localIp.textContent = client.local_ip || 'N/A';

        const wanIp = rowElement.querySelector('.ip-wan');
        if (wanIp) wanIp.textContent = client.wan_ip || 'N/A';

        const cpuCell = rowElement.querySelector('.metric-cpu');
        if (cpuCell) {
            cpuCell.className = `td-metric metric-cpu ${cpuLevelClass}`;
            const val = cpuCell.querySelector('.metric-val');
            if (val) val.textContent = `${cpu.toFixed(1)}%`;
        }

        const ramCell = rowElement.querySelector('.metric-ram');
        if (ramCell) {
            ramCell.className = `td-metric metric-ram ${ramLevelClass}`;
            const val = ramCell.querySelector('.metric-val');
            if (val) val.textContent = `${ram.toFixed(1)}%`;
        }

        const diskCell = rowElement.querySelector('.metric-disk');
        if (diskCell) {
            diskCell.className = `td-metric metric-disk ${diskLevelClass}`;
            const val = diskCell.querySelector('.metric-val');
            if (val) val.textContent = `${disk.toFixed(1)}%`;
        }

        const timeSpan = rowElement.querySelector('.time-ago');
        if (timeSpan) timeSpan.textContent = lastUpdate;

        // Cập nhật động nút CẬP NHẬT TỪNG MÁY trong bảng
        const rowActionsEl = rowElement.querySelector('.client-card-actions');
        if (rowActionsEl) {
            let updateBtn = rowActionsEl.querySelector('.btn-update');
            if (client.needs_update) {
                const tooltipText = `Phiên bản hiện tại: v${client.version || '1.0.0'} - Bấm để cập nhật`;
                if (!updateBtn) {
                    updateBtn = document.createElement('button');
                    updateBtn.className = 'btn-icon btn-update';
                    updateBtn.dataset.guid = client.guid;
                    updateBtn.title = tooltipText;
                    updateBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-down"></i>';
                    rowActionsEl.insertBefore(updateBtn, rowActionsEl.firstChild);
                } else {
                    updateBtn.title = tooltipText;
                }
            } else if (updateBtn) {
                updateBtn.remove();
            }
        }
    }

    function updateDashboard(page = null) {

        if (page !== null) currentPage = page;

        

        fetch(`/api/dashboard_data?page=${currentPage}`)

            .then(response => {

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                return response.json();

            })

            .then(data => {

                const statusBar = document.getElementById('server-status-bar');

                const statusText = document.getElementById('server-status-text');

                if (data.server_status.is_online) {

                    statusBar.className = 'server-status-bar online';

                    statusText.textContent = 'Server is Online';

                } else {

                    statusBar.className = 'server-status-bar offline';

                    statusText.textContent = `Server is Offline. Last data received at ${data.server_status.last_data_update}`;

                }

                // CẬP NHẬT DỮ LIỆU CHO STATS-GRID MỚI

                const stats = data.stats;

                const thresholds = data.thresholds;

                const calculatePercent = (current, max) => {

                    if (max <= 0) return 0;

                    return Math.min((current / max) * 100, 100);

                };

                

                // Card 1: Total Clients

                const totalClientsPercent = calculatePercent(stats.total_clients, thresholds.clients);

                statElements.total.value.textContent = stats.total_clients;

                statElements.total.progress.style.width = `${totalClientsPercent}%`;

                statElements.total.subtext.textContent = `${stats.total_clients} / ${thresholds.clients} registered`;

                

                // Card 2: Clients Online

                const onlinePercent = stats.total_clients > 0 ? (stats.clients_online / stats.total_clients) * 100 : 0;

                statElements.online.value.textContent = stats.clients_online;

                statElements.online.progress.style.width = `${onlinePercent}%`;

                statElements.online.subtext.textContent = `${stats.clients_online}/${stats.total_clients} active`;

                // Card 3: Metrics Logged

                const recordsPercent = calculatePercent(stats.record_count, thresholds.records);

                statElements.records.value.textContent = stats.record_count.toLocaleString();

                statElements.records.progress.style.width = `${recordsPercent}%`;

                statElements.records.subtext.textContent = `${stats.record_count.toLocaleString()} / ${thresholds.records.toLocaleString()} entries`;

                // Card 4: Database Size

                const dbPercent = calculatePercent(stats.db_size_mb, thresholds.db_size);

                statElements.dbsize.value.textContent = stats.db_size;

                statElements.dbsize.progress.style.width = `${dbPercent}%`;

                statElements.dbsize.subtext.textContent = `Limit: ${thresholds.db_size} MB`;

                // CẬP NHẬT PHÂN TRANG

                const pagin = data.pagination;

                currentPage = pagin.current_page;

                totalPages = pagin.total_pages;

                const paginationContainer = document.getElementById('dashboard-pagination');

                if (paginationContainer) {

                    if (totalPages <= 1) {

                        paginationContainer.style.display = 'none';

                    } else {

                        paginationContainer.style.display = 'flex';

                        paginationContainer.innerHTML = `

                            <button id="btn-prev-page" class="btn-minimal" ${currentPage <= 1 ? 'disabled' : ''}>&#9664;</button>

                            <span class="page-info">

                                <span id="current-page-num">${currentPage}</span>/<span id="total-pages-num">${totalPages}</span>

                            </span>

                            <button id="btn-next-page" class="btn-minimal" ${currentPage >= totalPages ? 'disabled' : ''}>&#9654;</button>

                        `;

                        

                        const newBtnPrev = paginationContainer.querySelector('#btn-prev-page');

                        const newBtnNext = paginationContainer.querySelector('#btn-next-page');

                        newBtnPrev.onclick = () => { if (currentPage > 1) updateDashboard(currentPage - 1); };

                        newBtnNext.onclick = () => { if (currentPage < totalPages) updateDashboard(currentPage + 1); };

                    }

                }

                // Đếm số lượng máy trạm cần cập nhật

                const targetVersion = data.target_version || '1.0.1';

                const outdatedClients = data.clients.filter(c => c.needs_update && c.status === 'Online');

                const btnUpdateAll = document.getElementById('btn-update-all-clients');

                const outdatedCountSpan = document.getElementById('outdated-count');

                

                if (btnUpdateAll && outdatedCountSpan) {

                    if (outdatedClients.length > 0) {

                        btnUpdateAll.style.display = 'inline-flex';

                        outdatedCountSpan.textContent = outdatedClients.length;

                        btnUpdateAll.onclick = () => triggerUpdateAllClients(outdatedClients, targetVersion);

                    } else {

                        btnUpdateAll.style.display = 'none';

                    }

                }

                const receivedGuids = new Set(data.clients.map(c => c.guid));

                

                // Cập nhật Grid view

                if (clientsGrid) {

                    data.clients.forEach(client => {

                        let card = clientsGrid.querySelector(`.client-card[data-guid="${client.guid}"]`);

                        if (card) {

                            updateClientCardContent(card, client);

                        } else {

                            card = createClientCard(client);

                            clientsGrid.appendChild(card);

                        }

                    });

                    

                    const existingCards = clientsGrid.querySelectorAll('.client-card');

                    existingCards.forEach(card => {

                        if (!receivedGuids.has(card.dataset.guid)) {

                            card.remove();

                        }

                    });

                    

                    if (clientsGrid.children.length === 0 && !clientsGrid.querySelector('.no-clients-message')) {

                         clientsGrid.innerHTML = '<p class="no-clients-message">No clients found.</p>';

                    } else if (clientsGrid.children.length > 0) {

                        const noClientsMessage = clientsGrid.querySelector('.no-clients-message');

                        if (noClientsMessage) noClientsMessage.remove();

                    }

                }

                // Cập nhật Table view

                if (clientsTableBody) {

                    data.clients.forEach(client => {

                        let row = clientsTableBody.querySelector(`.client-row[data-guid="${client.guid}"]`);

                        if (row) {

                            updateClientRowContent(row, client);

                        } else {

                            row = createClientRow(client);

                            clientsTableBody.appendChild(row);

                        }

                    });

                    const existingRows = clientsTableBody.querySelectorAll('.client-row');

                    existingRows.forEach(row => {

                        if (!receivedGuids.has(row.dataset.guid)) {

                            row.remove();

                        }

                    });

                    if (clientsTableBody.children.length === 0 && !clientsTableBody.querySelector('.no-clients-row')) {

                        clientsTableBody.innerHTML = '<tr class="no-clients-row"><td colspan="10" style="text-align:center; padding: 2rem; color: var(--color-text-muted);">No clients found.</td></tr>';

                    } else if (clientsTableBody.children.length > 0) {

                        const emptyRow = clientsTableBody.querySelector('.no-clients-row');

                        if (emptyRow) emptyRow.remove();

                    }

                }

            })

            .catch(error => {

                console.error('Error updating dashboard:', error);

                const statusBar = document.getElementById('server-status-bar');

                 if(statusBar) {

                    statusBar.className = 'server-status-bar offline';

                    statusBar.innerHTML = '<span id="server-status-text">Could not connect to the backend. Is the Flask server running?</span>';

                 }

            });

    }

    // Xử lý sự kiện nút phân trang

    if (btnPrev) {

        btnPrev.addEventListener('click', () => {

            if (currentPage > 1) {

                updateDashboard(currentPage - 1);

            }

        });

    }

    if (btnNext) {

        btnNext.addEventListener('click', () => {

            if (currentPage < totalPages) {

                updateDashboard(currentPage + 1);

            }

        });

    }

    function disableEditing(inputElement, buttonElement) {

        inputElement.setAttribute('readonly', true);

        buttonElement.classList.remove('editing');

        buttonElement.title = "Edit Username";

        buttonElement.innerHTML = '<i class="fa-solid fa-pencil"></i>';

    }

    function saveUsername(inputElement, buttonElement) {

        const guid = inputElement.dataset.guid;

        const newUsername = inputElement.value.trim();

        

        if (!newUsername) {

            alert('Tên người dùng không được để trống.');

            inputElement.focus();

            return;

        }

        buttonElement.disabled = true;

        buttonElement.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

        

        fetch('/api/client/update_username', {

            method: 'POST',

            headers: { 'Content-Type': 'application/json' },

            body: JSON.stringify({ guid: guid, username: newUsername })

        })

        .then(response => response.json())

        .then(data => {

            buttonElement.disabled = false;

            if (data.status === 'success') {

                inputElement.value = newUsername;

                inputElement.defaultValue = newUsername;

                disableEditing(inputElement, buttonElement);

                // Đồng bộ giá trị vào tất cả các input có cùng guid (cả trong card và trong row)

                document.querySelectorAll(`.username-input[data-guid="${guid}"]`).forEach(inp => {

                    inp.value = newUsername;

                    inp.defaultValue = newUsername;

                    const btn = inp.closest('.username-wrapper')?.querySelector('.edit-username-btn');

                    if (btn) disableEditing(inp, btn);

                });

            } else {

                buttonElement.innerHTML = '<i class="fa-solid fa-check"></i>';

                alert('Lỗi cập nhật tên người dùng: ' + data.message);

                inputElement.focus();

            }

        })

        .catch(error => {

            buttonElement.disabled = false;

            buttonElement.innerHTML = '<i class="fa-solid fa-check"></i>';

            alert('An error occurred while saving.');

            inputElement.focus();

        });

    }

    // ==========================================

    // 4. LẮNG NGHE SỰ KIỆN CHỈNH SỬA & THAO TÁC TRÊN CONTAINER CHUNG

    // ==========================================

    const containerToListen = clientsViewContainer || document.body;

    containerToListen.addEventListener('click', function(e) {

        const editBtn = e.target.closest('.edit-username-btn');

        const deleteBtn = e.target.closest('.btn-delete');

        const refreshBtn = e.target.closest('.btn-refresh');

        const updateBtn = e.target.closest('.btn-update');

        if (editBtn) {

            const input = editBtn.closest('.username-wrapper').querySelector('.username-input');

            if (input.hasAttribute('readonly')) {

                input.removeAttribute('readonly');

                editBtn.classList.add('editing');

                editBtn.title = "Save Username";

                editBtn.innerHTML = '<i class="fa-solid fa-check"></i>';

                input.focus();

                input.select();

            } else {

                saveUsername(input, editBtn);

            }

        } else if (deleteBtn) {

            const guid = deleteBtn.dataset.guid;

            if (confirm(`Are you sure you want to delete client ${guid}? This action cannot be undone.`)) {

                fetch('/api/client/delete', {

                    method: 'POST',

                    headers: { 'Content-Type': 'application/json' },

                    body: JSON.stringify({ guid: guid })

                }).then(() => {

                    console.log(`Client ${guid} deleted. Refreshing dashboard...`);

                    updateDashboard();

                });

            }

        } else if (refreshBtn) {

             updateDashboard();

        } else if (updateBtn) {

             const guid = updateBtn.dataset.guid;

             triggerUpdateSingleClient(guid);

        }

    });

    containerToListen.addEventListener('keydown', function(e) {

        if (e.target.classList.contains('username-input') && !e.target.hasAttribute('readonly')) {

            const input = e.target;

            const editBtn = input.closest('.username-wrapper').querySelector('.edit-username-btn');

            if (e.key === 'Enter') {

                e.preventDefault();

                saveUsername(input, editBtn);

            } else if (e.key === 'Escape') {

                input.value = input.defaultValue;

                disableEditing(input, editBtn);

            }

        }

    });

    // ==========================================

    // 5. LOGIC CHUYỂN ĐỔI CHẾ ĐỘ HIỂN THỊ (LƯỚI / DANH SÁCH BẢNG)

    // ==========================================

    const viewModeSwitcher = document.getElementById('view-mode-switcher');

    const viewModeIcon = document.getElementById('view-mode-icon');

    const viewModeContainer = document.getElementById('view-mode-container');

    function applyViewMode(mode) {

        const isList = (mode === 'list');

        

        // Điều khiển trực tiếp hiển thị phần tử DOM

        if (clientsTableWrapper) {

            clientsTableWrapper.style.display = isList ? 'block' : 'none';

        }

        if (clientsGrid) {

            clientsGrid.style.display = isList ? 'none' : 'grid';

        }

        // Cập nhật class body và các điều khiển trên header

        if (isList) {

            document.body.classList.add('view-list');

            document.body.classList.remove('view-grid');

            if (viewModeSwitcher) viewModeSwitcher.value = 'list';

            if (viewModeIcon) viewModeIcon.className = 'fa-solid fa-table-list';

        } else {

            document.body.classList.remove('view-list');

            document.body.classList.add('view-grid');

            if (viewModeSwitcher) viewModeSwitcher.value = 'grid';

            if (viewModeIcon) viewModeIcon.className = 'fa-solid fa-table-cells-large';

        }

        localStorage.setItem('dashboard_view_mode', mode);

    }

    if (viewModeContainer) viewModeContainer.style.display = 'inline-flex';

    if (viewModeSwitcher) {

        let savedViewMode = localStorage.getItem('dashboard_view_mode') || 'grid';

        if (savedViewMode === 'detailed') savedViewMode = 'grid';

        if (savedViewMode === 'simple') savedViewMode = 'list';

        applyViewMode(savedViewMode);

        viewModeSwitcher.addEventListener('change', (e) => {

            applyViewMode(e.target.value);

        });

    }

    updateDashboard();

    setInterval(updateDashboard, DASHBOARD_INTERVAL);

});

// ==========================================

// CÁC HÀM CẬP NHẬT CLIENT (AUTO UPDATE)

// ==========================================

async function triggerUpdateSingleClient(guid) {

    if (!confirm(`Bạn có chắc chắn muốn gửi lệnh CẬP NHẬT tới máy trạm này không?\nServer sẽ đẩy trực tiếp bộ cài client_setup.exe qua WebSocket. Máy trạm sẽ tự động tắt smchost, cài đặt phiên bản mới và khởi động lại ngầm.`)) {

        return;

    }

    // 1. Ưu tiên gửi qua WebSocket trực tiếp của trình duyệt nếu đang kết nối

    const ws = window.globalWs;

    if (ws && ws.readyState === WebSocket.OPEN) {

        ws.send(JSON.stringify({

            type: 'remote_command',

            target_guid: guid,

            command: 'update_client'

        }));

        if (typeof showToast === 'function') {

            showToast("Đã gửi lệnh cập nhật tới máy trạm qua WebSocket!", "connect", guid);

        } else {

            alert("Đã phát lệnh cập nhật tới máy trạm qua WebSocket!");

        }

        return;

    }

    // 2. Kênh dự phòng (Fallback): Gửi qua API HTTP của Backend Flask

    // Backend sẽ kết nối WebSocket nội bộ (127.0.0.1:9630) để đẩy lệnh cập nhật xuống Agent ngay lập tức

    try {

        if (typeof showToast === 'function') {

            showToast("Đang kích hoạt cập nhật máy trạm qua Server...", "connect", guid);

        }

        const res = await fetch('/api/client/trigger_update', {

            method: 'POST',

            headers: { 'Content-Type': 'application/json' },

            body: JSON.stringify({ guid: guid })

        });

        const result = await res.json();

        if (result.status === 'success') {

            const msg = result.message || "Đã gửi gói cập nhật thành công!";

            if (typeof showToast === 'function') {

                showToast(msg, "connect", guid);

            } else {

                alert(msg);

            }

        } else {

            const errMsg = result.message || "Lỗi không xác định khi cập nhật";

            if (typeof showToast === 'function') {

                showToast(`Cập nhật thất bại: ${errMsg}`, "alert", guid);

            } else {

                alert(`Cập nhật thất bại: ${errMsg}`);

            }

        }

    } catch (err) {

        const errText = `Không thể gửi lệnh cập nhật: ${err.message}`;

        if (typeof showToast === 'function') {

            showToast(errText, "alert", guid);

        } else {

            alert(errText);

        }

    }

}

async function triggerUpdateAllClients(outdatedClients, targetVersion) {

    const count = outdatedClients ? outdatedClients.length : 0;

    if (!confirm(`Phát hiện ${count} máy trạm đang sử dụng phiên bản cũ.\nBạn có chắc chắn muốn CẬP NHẬT TOÀN BỘ lên phiên bản v${targetVersion} không?\nServer sẽ đẩy trực tiếp bộ cài client_setup.exe qua WebSocket tới tất cả máy trạm.`)) {

        return;

    }

    // 1. Ưu tiên gửi qua WebSocket trực tiếp của trình duyệt nếu đang kết nối

    const ws = window.globalWs;

    if (ws && ws.readyState === WebSocket.OPEN) {

        ws.send(JSON.stringify({

            type: 'remote_command',

            target_guid: 'ALL',

            command: 'update_client'

        }));

        if (typeof showToast === 'function') {

            showToast(`Đã phát lệnh cập nhật tới toàn bộ ${count} máy trạm!`, "connect");

        } else {

            alert(`Đã phát lệnh cập nhật toàn bộ qua WebSocket!\nServer đang đẩy trực tiếp gói cập nhật tới tất cả máy trạm...`);

        }

        return;

    }

    // 2. Kênh dự phòng (Fallback): Gửi qua API HTTP của Backend Flask

    try {

        if (typeof showToast === 'function') {

            showToast(`Đang phát lệnh cập nhật tới toàn bộ ${count} máy trạm qua Server...`, "connect");

        }

        const res = await fetch('/api/client/trigger_update', {

            method: 'POST',

            headers: { 'Content-Type': 'application/json' },

            body: JSON.stringify({ guid: 'ALL' })

        });

        const result = await res.json();

        if (result.status === 'success') {

            const msg = result.message || `Đã đẩy gói cập nhật tới ${result.sent_count || count} máy trạm!`;

            if (typeof showToast === 'function') {

                showToast(msg, "connect");

            } else {

                alert(msg);

            }

        } else {

            const errMsg = result.message || "Lỗi không xác định khi cập nhật toàn bộ";

            if (typeof showToast === 'function') {

                showToast(`Cập nhật thất bại: ${errMsg}`, "alert");

            } else {

                alert(`Cập nhật thất bại: ${errMsg}`);

            }

        }

    } catch (err) {

        const errText = `Không thể gửi lệnh cập nhật: ${err.message}`;

        if (typeof showToast === 'function') {

            showToast(errText, "alert");

        } else {

            alert(errText);

        }

    }

}
