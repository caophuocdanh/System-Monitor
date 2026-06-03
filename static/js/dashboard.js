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

    const clientsGrid = document.getElementById('clients-grid');
    
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
    const spanCurrentPage = document.getElementById('current-page-num');
    const spanTotalPages = document.getElementById('total-pages-num');
    const spanTotalClients = document.getElementById('total-clients-num'); // Vẫn giữ để cập nhật ngầm nếu cần

    // ... (code getUsageLevelClass và timeAgo không đổi) ...
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

        if (seconds < 5) return "vừa xong";
        if (seconds < 60) return `${seconds} giây trước`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ trước`;
        return `${Math.floor(seconds / 86400)} ngày trước`;
    }

    function createClientCard(client) {
        const clientCard = document.createElement('div');
        // Gán icon ngẫu nhiên ngay khi tạo card
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
                        <button class="edit-username-btn" title="Sửa tên người dùng">
                            <i class="fa-solid fa-pencil"></i>
                        </button>
                    </div>
                </div>
                <div class="status-dot ${statusClass}"></div>
            </div>
            <div class="client-card-body">
                <p><i class="icon fa-solid fa-desktop"></i> <span class="ip-font">${client.local_ip || 'N/A'}</span></p>
                <p><i class="icon fa-solid fa-globe"></i> <span class="ip-font">${client.wan_ip || 'N/A'}</span></p>
            </div>
            <div class="client-card-metrics">
                <div class="metric-item ${cpuLevelClass}">
                    <div class="metric-icon"><i class="fa-solid fa-microchip"></i></div>
                    <div class="metric-value">${cpu.toFixed(1)}%</div>
                    <div class="metric-label">CPU</div>
                </div>
                <div class="metric-item ${ramLevelClass}">
                    <div class="metric-icon"><i class="fa-solid fa-memory"></i></div>
                    <div class="metric-value">${ram.toFixed(1)}%</div>
                    <div class="metric-label">RAM</div>
                </div>
                <div class="metric-item ${diskLevelClass}">
                    <div class="metric-icon"><i class="fa-solid fa-hard-drive"></i></div>
                    <div class="metric-value">${disk.toFixed(1)}%</div>
                    <div class="metric-label">Disk</div>
                </div>
            </div>
            <div class="client-card-footer-wrapper">
                <div class="client-card-status">
                    <span>Cập nhật: ${lastUpdate}</span>
                </div>
                <div class="client-card-actions">
                    <a href="/client/${client.guid}" class="btn-icon btn-detail" title="Xem chi tiết">
                        <i class="fa-solid fa-info"></i>
                    </a>
                    <button class="btn-icon btn-refresh" data-guid="${client.guid}" title="Làm mới dữ liệu">
                        <i class="fa-solid fa-sync-alt"></i>
                    </button>
                    <button class="btn-icon btn-delete" data-guid="${client.guid}" title="Xóa Client">
                        <i class="fa-solid fa-trash-alt"></i>
                    </button>
                </div>
            </div>
        `;
    }

    // ... (các hàm còn lại updateDashboard, disableEditing, saveUsername, event listeners không đổi) ...
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
                    statusText.textContent = 'Máy chủ Trực tuyến';
                } else {
                    statusBar.className = 'server-status-bar offline';
                    statusText.textContent = `Máy chủ Ngoại tuyến. Dữ liệu cuối nhận lúc ${data.server_status.last_data_update}`;
                }

                // CẬP NHẬT DỮ LIỆU CHO STATS-GRID MỚI
                const stats = data.stats;
                const thresholds = data.thresholds; // Lấy giá trị ngưỡng từ API

                // Hàm tiện ích để tính toán và giới hạn %
                const calculatePercent = (current, max) => {
                    if (max <= 0) return 0;
                    return Math.min((current / max) * 100, 100);
                };
                
                // Card 1: Total Clients
                const totalClientsPercent = calculatePercent(stats.total_clients, thresholds.clients);
                statElements.total.value.textContent = stats.total_clients;
                statElements.total.progress.style.width = `${totalClientsPercent}%`;
                statElements.total.subtext.textContent = `${stats.total_clients} / ${thresholds.clients} đã đăng ký`;
                
                // Card 2: Clients Online
                const onlinePercent = stats.total_clients > 0 ? (stats.clients_online / stats.total_clients) * 100 : 0;
                statElements.online.value.textContent = stats.clients_online;
                statElements.online.progress.style.width = `${onlinePercent}%`;
                statElements.online.subtext.textContent = `${stats.clients_online}/${stats.total_clients} đang hoạt động`;

                // Card 3: Metrics Logged
                const recordsPercent = calculatePercent(stats.record_count, thresholds.records);
                statElements.records.value.textContent = stats.record_count.toLocaleString();
                statElements.records.progress.style.width = `${recordsPercent}%`;
                statElements.records.subtext.textContent = `${stats.record_count.toLocaleString()} / ${thresholds.records.toLocaleString()} bản ghi`;

                // Card 4: Database Size
                const dbPercent = calculatePercent(stats.db_size_mb, thresholds.db_size);
                statElements.dbsize.value.textContent = stats.db_size;
                statElements.dbsize.progress.style.width = `${dbPercent}%`;
                statElements.dbsize.subtext.textContent = `Giới hạn: ${thresholds.db_size} MB`;

                // --- CẬP NHẬT PHÂN TRANG ---
                const pagin = data.pagination;
                currentPage = pagin.current_page;
                totalPages = pagin.total_pages;

                const paginationContainer = document.getElementById('dashboard-pagination');
                if (paginationContainer) {
                    if (totalPages <= 1) {
                        paginationContainer.style.display = 'none';
                    } else {
                        paginationContainer.style.display = 'flex';
                        // ÉP BUỘC ĐỊNH DẠNG ◀ 1/10 ▶ QUA JS ĐỂ TRÁNH TEMPLATE CŨ
                        paginationContainer.innerHTML = `
                            <button id="btn-prev-page" class="btn-minimal" ${currentPage <= 1 ? 'disabled' : ''}>&#9664;</button>
                            <span class="page-info">
                                <span id="current-page-num">${currentPage}</span>/<span id="total-pages-num">${totalPages}</span>
                            </span>
                            <button id="btn-next-page" class="btn-minimal" ${currentPage >= totalPages ? 'disabled' : ''}>&#9654;</button>
                        `;
                        
                        // Gán lại sự kiện vì innerHTML đã làm mất listener cũ
                        const newBtnPrev = paginationContainer.querySelector('#btn-prev-page');
                        const newBtnNext = paginationContainer.querySelector('#btn-next-page');
                        newBtnPrev.onclick = () => { if (currentPage > 1) updateDashboard(currentPage - 1); };
                        newBtnNext.onclick = () => { if (currentPage < totalPages) updateDashboard(currentPage + 1); };
                    }
                }

                const receivedGuids = new Set(data.clients.map(c => c.guid));
                
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
                     clientsGrid.innerHTML = '<p class="no-clients-message">Không tìm thấy client nào.</p>';
                } else if (clientsGrid.children.length > 0) {
                    const noClientsMessage = clientsGrid.querySelector('.no-clients-message');
                    if (noClientsMessage) noClientsMessage.remove();
                }

            })
            .catch(error => {
                console.error('Error updating dashboard:', error);
                const statusBar = document.getElementById('server-status-bar');
                 if(statusBar) {
                    statusBar.className = 'server-status-bar offline';
                    statusBar.innerHTML = '<span id="server-status-text">Không thể kết nối với máy chủ. Flask server đã chạy chưa?</span>';
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
        buttonElement.title = "Sửa tên người dùng";
        buttonElement.innerHTML = '<i class="fa-solid fa-pencil"></i>';
    }

    function saveUsername(inputElement, buttonElement) {
        const guid = inputElement.dataset.guid;
        const newUsername = inputElement.value;
        
        fetch('/api/client/update_username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ guid: guid, username: newUsername })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                disableEditing(inputElement, buttonElement);
                inputElement.defaultValue = newUsername;
            } else {
                alert('Lỗi cập nhật tên người dùng: ' + data.message);
            }
        })
        .catch(error => alert('Đã xảy ra lỗi khi lưu.'));
    }

    clientsGrid.addEventListener('click', function(e) {
        const editBtn = e.target.closest('.edit-username-btn');
        const deleteBtn = e.target.closest('.btn-delete');
        const refreshBtn = e.target.closest('.btn-refresh');

        if (editBtn) {
            const input = editBtn.closest('.username-wrapper').querySelector('.username-input');
            if (input.hasAttribute('readonly')) {
                input.removeAttribute('readonly');
                editBtn.classList.add('editing');
                editBtn.title = "Lưu tên người dùng";
                editBtn.innerHTML = '<i class="fa-solid fa-check"></i>';
                input.focus();
                input.select();
            } else {
                saveUsername(input, editBtn);
            }
        } else if (deleteBtn) {
            const guid = deleteBtn.dataset.guid;
            if (confirm(`Bạn có chắc chắn muốn xóa client ${guid}? Hành động này không thể hoàn tác.`)) {
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
        }
    });

    clientsGrid.addEventListener('keydown', function(e) {
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

    updateDashboard();
    setInterval(updateDashboard, DASHBOARD_INTERVAL);
});