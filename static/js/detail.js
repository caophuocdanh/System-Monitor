// static/js/detail.js

// --- DATA MAPS FOR DECODING ---
const manufacturer_map = {
    "1337": "Kingmax", "1900": "Kingston", "0x0101": "AMD", "0x010B": "Nanya", "0x012C": "Micron", 
    "0x0134": "Fujitsu", "0x0145": "SanDisk / Western Digital", "0x014F": "Transcend", 
    "0x0198": "HyperX", "0x01AD": "SK Hynix", "0x01CE": "Samsung", "0x01DA": "Renesas", 
    "0x020D": "Spectek", "0x022D": "Nvidia", "0x02A4": "PNY", "0x02C0": "Micron", "0x02E0": "Infineon", 
    "0x0351": "Patriot", "0x039E": "ADATA", "0x040B": "Apacer", "0x0434": "GeIL", "0x04CD": "G.Skill", 
    "0x04D2": "Winbond", "0x050D": "Team Group", "0x0539": "Virtium", "0x05CB": "Crucial", 
    "0x065B": "Kingston", "0x079D": "Mushkin", "0x8001": "AMD", "0x800B": "Nanya", "0x802C": "Micron", 
    "0x803F": "Intel", "0x80AD": "SK Hynix", "0x80CE": "Samsung", "0x80E0": "Infineon", "0x859B": "Kingston", 
    "0x7F7F7F9E": "ADATA", "0x7F9D": "Corsair", "0443": "G.Skill", "0x0000": "Unspecified", 
    "0xFFFF": "Unspecified", "Unknown": "Unknown", "04CB": "A-DATA", "017A": "Apacer", "029E": "Corsair", 
    "059B": "Crucial", "00CE": "Samsung"
};

const type_map = {
    20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 28: "DDR5", 34: "LPDDR4"
};

const form_map = {
    8: "DIMM", 9: "SODIMM", 12: "LRDIMM"
};

const printer_status_map = {
    0x1: "Paused", 0x2: "Error", 0x4: "Pending Deletion", 0x8: "Paper Jam",
    0x10: "Paper Out", 0x20: "Manual Feed", 0x40: "Paper Problem", 0x80: "Offline",
    0x100: "IO Active", 0x200: "Busy", 0x400: "Printing", 0x800: "Output Bin Full",
    0x1000: "Not Available", 0x2000: "Waiting", 0x4000: "Processing", 0x8000: "Initializing",
    0x10000: "Warming Up", 0x20000: "Toner Low", 0x40000: "No Toner", 0x400000: "Output Bin Missing"
};

const printer_attributes_map = {
    0x2: "Default", 0x4: "Shared", 0x8: "Hidden", 0x10: "Printer Fax",
    0x20: "Network", 0x40: "Enable Dev Query", 0x100: "Direct", 0x200: "Keep Printed Jobs",
    0x400: "Do Complete First", 0x800: "Work Offline", 0x1000: "Enable BIDI",
    0x2000: "Raw Only", 0x4000: "Published", 0x8000: "Enable Shared",
    0x10000: "Hidden Devmode", 0x20000: "Raw Queue", 0x40000: "Local"
};

function decodeBitmask(map, code) {
    const descriptions = [];
    for (const bit in map) {
        if (code & bit) {
            descriptions.push(map[bit]);
        }
    }
    return descriptions;
}

// --- Tab Handling ---
function openTab(evt, tabName) {
    document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
    document.querySelectorAll('.tab-link').forEach(tl => tl.classList.remove('active'));
    const targetTabContent = document.getElementById(tabName);
    if (targetTabContent) targetTabContent.classList.add('active');
    if (evt.currentTarget) evt.currentTarget.classList.add('active');
}

document.addEventListener('DOMContentLoaded', () => {
    // Luôn mở tab đầu tiên khi tải trang
    if (document.querySelector('.tab-link')) {
        document.querySelector('.tab-link').click();
    }
    
    // Listener cho các toggle của Web History, được ủy quyền cho body
    document.body.addEventListener('click', function(e) {
        if (e.target.classList.contains('toggle-header')) {
            e.preventDefault();
            e.target.classList.toggle('active');
            const content = e.target.nextElementSibling;
            if (content && content.classList.contains('toggle-content')) {
                content.classList.toggle('active');
            }
        }
    });

    let auditData = {};
    const charts = {};
    const tableManagers = {}; // Đối tượng để chứa các trình quản lý bảng

    // --- Helper Functions ---
    function getUsageLevelClass(percentage) {
        if (percentage < 35) return 'level-low';
        if (percentage < 70) return 'level-medium';
        return 'level-high';
    }

    function formatSpeed(mbps, unit = 'Mbps') {
        if (mbps === null || mbps === undefined) return 'N/A';
        if (mbps < 1) {
            const kbps = mbps * 1024;
            const newUnit = unit.replace('M', 'K');
            return `${kbps.toFixed(1)} ${newUnit}`;
        }
        return `${mbps.toFixed(2)} ${unit}`;
    }

    function formatBytes(bytes, decimals = 2) {
        if (!bytes || typeof bytes !== 'number') return 'N/A';
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(dm) + ' ' + sizes[i];
    }

    function formatSpeedFromBps(bytesPerSecond, decimals = 2) {
        if (typeof bytesPerSecond !== 'number' || bytesPerSecond < 0) return '0 B/s';
        if (bytesPerSecond === 0) return '0 B/s';
        const k = 1024;
        const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s'];
        const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k));
        return `${parseFloat((bytesPerSecond / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
    }

    function formatSpeedFromBits(bitsPerSecond, decimals = 2) {
        if (typeof bitsPerSecond !== 'number' || bitsPerSecond < 0) return '0 bps';
        if (bitsPerSecond === 0) return '0 bps';
        const k = 1000; // Mạng dùng hệ 1000
        const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
        const i = Math.floor(Math.log(bitsPerSecond) / Math.log(k));
        return `${parseFloat((bitsPerSecond / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
    }

    function formatKey(key) {
        key = key.replace(/Bytes|Bps|MHz|_Bps|Array/g, '').replace('SID Value', 'SID');
        key = key.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ');
        return key.replace(/\b\w/g, char => char.toUpperCase()).trim();
    }

    function formatRamSpeed(clockSpeedMhz, memoryType = '') {
        if (clockSpeedMhz === null || clockSpeedMhz === undefined || typeof clockSpeedMhz !== 'number') {
            return 'N/A';
        }
        let effectiveSpeed = clockSpeedMhz;
        const typeStr = String(memoryType).toUpperCase();
        if (typeStr.includes('DDR')) {
            effectiveSpeed = clockSpeedMhz * 2;
        }
        return `${effectiveSpeed} MT/s`;
    }
    
    function formatValue(key, value) {
        if (value === null || value === undefined || value === '') return 'N/A';
        if (typeof value === 'string' && /^\d{14}\./.test(value)) {
            try {
                const year = value.substring(0, 4);
                const month = value.substring(4, 6);
                const day = value.substring(6, 8);
                return `${year}-${month}-${day}`; 
            } catch (e) {
                return value;
            }
        }
        const lowerKey = key.toLowerCase();
        if (lowerKey.includes('bytes') || lowerKey.includes('size') || lowerKey.includes('capacity') || lowerKey.includes('space')) {
            return formatBytes(Number(value));
        }
        if (lowerKey === 'speed' && typeof value === 'number') {
            if (value >= 1000000000) return `${(value / 1000000000).toFixed(1)} Gbps`;
            if (value >= 1000000) return `${(value / 1000000).toFixed(0)} Mbps`;
            if (value >= 1000) return `${(value / 1000).toFixed(0)} Kbps`;
            if (value > 0) return `${value} bps`;
            if (String(value).includes('MHz')) return value;
        }
        if (lowerKey.includes('speed') && !lowerKey.includes('bps')) {
            return `${value}`;
        }
        if (typeof value === 'boolean') {
            return value ? '<span style="color:var(--color-success); font-weight:bold;">Enabled</span>' : '<span style="color:var(--color-danger); font-weight:bold;">Disabled</span>';
        }
        return value;
    }
    
    function renderKeyValue(key, value, isHighlight = false) {
        if (value === null || value === undefined) return '';
        const formattedKey = formatKey(key);
        let displayValue;
        const highlightClass = isHighlight ? 'highlight-value' : '';
        if (Array.isArray(value)) {
            if (value.length === 0) return '<i>(empty)</i>';
            const listItems = value.map(item => {
                if (typeof item === 'object' && item !== null) {
                    const nestedContent = Object.entries(item)
                        .map(([nestedKey, nestedValue]) => renderKeyValue(nestedKey, nestedValue))
                        .join('');
                    return `<li class="nested-object">${nestedContent}</li>`;
                }
                return `<li>${formatValue(key, item)}</li>`;
            }).join('');
            displayValue = `<ul>${listItems}</ul>`;
        } else if (typeof value === 'object') {
             return `<div class="key-value ${highlightClass} nested"><span class="key">${formattedKey}</span><pre class="value">${JSON.stringify(value, null, 2)}</pre></div>`;
        } else {
            displayValue = formatValue(key, value);
        }
        return `<div class="key-value ${highlightClass}"><span class="key">${formattedKey}</span><div class="value">${displayValue}</div></div>`;
    }

    function buildCard(tabId, title, icon, content, extraClasses = '') {
        const tabButton = document.querySelector(`button[onclick*="'${tabId}'"]`);
        if (!content || content.trim() === '' || (Array.isArray(content) && content.length === 0)) {
            if(tabButton) tabButton.style.display = 'none';
            return '<p>No data available for this section.</p>';
        }
        if(tabButton) tabButton.style.display = 'flex';
        const titleHtml = (typeof title === 'string') 
            ? `<h2><i class="fa-solid ${icon}"></i> ${title}</h2>` 
            : title;
        return `
            <div class="info-card ${extraClasses}">
                ${titleHtml}
                <div class="card-content">${content}</div>
            </div>`;
    }

    class PaginatedTableManager {
        constructor(config) {
            this.allData = [];
            this.currentPage = 1;
            this.filterValue = 'All';
            this.itemsPerPage = config.itemsPerPage || 10;
            
            this.containerId = config.containerId;
            this.gridContainerId = config.gridContainerId;
            this.paginationContainerId = config.paginationContainerId;
            this.filterSelectId = config.filterSelectId;
            this.prevBtnId = config.prevBtnId;
            this.nextBtnId = config.nextBtnId;
            
            this.filterKey = config.filterKey;
            this.filterLabel = config.filterLabel || 'Filter:';
            this.createGridFn = config.createGridFn;
            this.cardTitle = config.cardTitle;
        }
    
        loadData(data) {
            this.allData = data;
            this.populateFilter();
            this.addEventListeners();
            this.updateView();
        }
    
        populateFilter() {
            const filterSelect = document.getElementById(this.filterSelectId);
            if (!filterSelect || !this.filterKey) return;
    
            const uniqueValues = [...new Set(this.allData.map(item => item[this.filterKey]))];
            
            filterSelect.innerHTML = `<option value="All">All</option>`;
            uniqueValues.sort().forEach(value => {
                if (value) {
                    const option = document.createElement('option');
                    option.value = value;
                    option.textContent = value;
                    filterSelect.appendChild(option);
                }
            });
        }
        
        addEventListeners() {
            const filterSelect = document.getElementById(this.filterSelectId);
            if (filterSelect) {
                filterSelect.addEventListener('change', e => {
                    this.filterValue = e.target.value;
                    this.currentPage = 1;
                    this.updateView();
                });
            }
            
            const paginationContainer = document.getElementById(this.paginationContainerId);
            if (paginationContainer) {
                paginationContainer.addEventListener('click', e => {
                    if (e.target.id === this.prevBtnId) {
                        if (this.currentPage > 1) {
                            this.currentPage--;
                            this.updateView();
                        }
                    }
                    if (e.target.id === this.nextBtnId) {
                        const totalPages = Math.ceil(this.getFilteredData().length / this.itemsPerPage);
                        if (this.currentPage < totalPages) {
                            this.currentPage++;
                            this.updateView();
                        }
                    }
                });
            }
        }
    
        getFilteredData() {
            if (this.filterValue === 'All' || !this.filterKey) {
                return this.allData;
            }
            return this.allData.filter(item => item[this.filterKey] === this.filterValue);
        }
    
        updateView() {
            const filteredData = this.getFilteredData();
            const totalPages = Math.ceil(filteredData.length / this.itemsPerPage);
            
            if (this.currentPage > totalPages) {
                this.currentPage = totalPages || 1;
            }
            
            const startIndex = (this.currentPage - 1) * this.itemsPerPage;
            const paginatedData = filteredData.slice(startIndex, startIndex + this.itemsPerPage);
            
            const gridContainer = document.getElementById(this.gridContainerId);
            if (gridContainer) {
                const title = `(Showing ${filteredData.length} of ${this.allData.length} entries)`;
                gridContainer.innerHTML = this.createGridFn(title, paginatedData, this.currentPage, this.itemsPerPage);
            }
            
            const paginationContainer = document.getElementById(this.paginationContainerId);
            if (paginationContainer) {
                const startItem = startIndex + 1;
                const endItem = Math.min(startIndex + this.itemsPerPage, filteredData.length);
                const infoText = filteredData.length > 0 ? `Showing ${startItem}-${endItem} of ${filteredData.length}` : 'No items to display.';
                
                paginationContainer.innerHTML = `
                    <div class="log-pagination-info">Page ${this.currentPage} of ${totalPages || 1} | ${infoText}</div>
                    <div class="log-pagination-buttons">
                        <button id="${this.prevBtnId}" ${this.currentPage === 1 ? 'disabled' : ''}>Previous</button>
                        <button id="${this.nextBtnId}" ${this.currentPage >= totalPages ? 'disabled' : ''}>Next</button>
                    </div>
                `;
            }
        }
    
        static renderLayout(filterLabel, filterSelectId, gridContainerId, paginationContainerId) {
            const hasFilter = filterLabel && filterSelectId;
            const filterHtml = hasFilter ? `
                <div class="log-controls">
                    <label for="${filterSelectId}">${filterLabel}</label>
                    <select id="${filterSelectId}"></select>
                </div>` : '';

            return `
                ${filterHtml}
                <div id="${gridContainerId}"></div>
                <div class="log-pagination" id="${paginationContainerId}"></div>
            `;
        }
    }


    // --- Server & Metrics Updates ---
    function updateServerStatus() {
        fetch('/api/dashboard_data').then(res => res.json()).then(data => {
            const statusBar = document.getElementById('server-status-bar');
            const statusText = document.getElementById('server-status-text');
            if (!statusBar || !statusText) return;
            statusBar.className = data.server_status.is_online ? 'server-status-bar online' : 'server-status-bar offline';
            statusText.textContent = data.server_status.is_online ? 'Server is Online' : 'Server is Offline';
        }).catch(() => {
             const statusBar = document.getElementById('server-status-bar');
             if(statusBar) statusBar.className = 'server-status-bar offline';
             if(document.getElementById('server-status-text')) document.getElementById('server-status-text').textContent = 'Server Unreachable';
        });
    }

    function updateRealtimeMetrics() {
        fetch(`/api/client_realtime_metrics/${CLIENT_GUID}`)
            .then(res => res.json())
            .then(data => {
                const updateProgressBar = (type, value) => {
                    const fill = document.getElementById(`realtime-${type}-fill`);
                    const text = document.getElementById(`realtime-${type}-text`);
                    const bar = document.getElementById(`realtime-${type}-bar`);
                    if (!fill || !text || !bar) return;
                    
                    const percentage = value || 0;
                    bar.className = `progress-bar ${getUsageLevelClass(percentage)}`;
                    fill.style.width = `${percentage}%`;
                    text.textContent = `${percentage.toFixed(1)}%`;
                };
                const updateText = (type, value, isBits = false) => {
                    const textElement = document.getElementById(`realtime-${type}-text`);
                    if (!textElement) return;
                    textElement.textContent = isBits ? formatSpeedFromBits(value, 2) : formatSpeedFromBps(value, 2);
                };
                
                if (data.status === 'success' && data.metrics) {
                    const metrics = data.metrics;
                    updateProgressBar('cpu', metrics.cpu_usage);
                    updateProgressBar('ram', metrics.ram_usage);
                    updateProgressBar('disk', metrics.disk_usage);
                    
                    let totalDiskRead = 0, totalDiskWrite = 0;
                    if (metrics.disk_io) {
                        for (const disk in metrics.disk_io) {
                            totalDiskRead += metrics.disk_io[disk].read_bytes_per_sec || 0;
                            totalDiskWrite += metrics.disk_io[disk].write_bytes_per_sec || 0;
                        }
                    }
                    let totalNetUpload = 0, totalNetDownload = 0;
                    if (metrics.network_io) {
                        for (const nic in metrics.network_io) {
                            totalNetUpload += metrics.network_io[nic].upload_bits_per_sec || 0;
                            totalNetDownload += metrics.network_io[nic].download_bits_per_sec || 0;
                        }
                    }
                    updateText('disk_read', totalDiskRead);
                    updateText('disk_write', totalDiskWrite);
                    updateText('net_upload', totalNetUpload, true);
                    updateText('net_download', totalNetDownload, true);
                } else {
                    ['cpu', 'ram', 'disk'].forEach(type => updateProgressBar(type, 0));
                    ['disk_read', 'disk_write'].forEach(type => updateText(type, 0));
                    ['net_upload', 'net_download'].forEach(type => updateText(type, 0, true));
                }
            })
            .catch(err => console.error("Failed to fetch realtime metrics:", err));
    }

    // --- Charting Functions ---
    function updatePerformanceCharts() {
        const performanceTab = document.getElementById('performance');
        if (!performanceTab.classList.contains('active') || Object.keys(charts).length === 0) return;

        fetch(`/api/client_realtime_metrics/${CLIENT_GUID}`)
            .then(res => res.json())
            .then(data => {
                if (data.status !== 'success' || !data.metrics) return;
                const newLabel = new Date().toLocaleTimeString('en-GB');
                const { metrics } = data;
                const MAX_POINTS = 50;

                const updateChartData = (chart, label, newPoints) => {
                    if (!chart) return;
                    chart.data.labels.push(label);
                    newPoints.forEach((point, index) => {
                        if (chart.data.datasets[index]) chart.data.datasets[index].data.push(point || 0);
                    });
                    while (chart.data.labels.length > MAX_POINTS) {
                        chart.data.labels.shift();
                        chart.data.datasets.forEach(dataset => dataset.data.shift());
                    }
                    chart.update('none');
                };

                updateChartData(charts['cpuPerfChart'], newLabel, [metrics.cpu_usage]);
                updateChartData(charts['ramPerfChart'], newLabel, [metrics.ram_usage]);
                
                for (const chartId in charts) {
                    if (chartId.startsWith('diskIoChart-')) {
                        const originalDiskName = Object.keys(data.disk_io || {}).find(dName => chartId === `diskIoChart-${dName.replace(/[^a-zA-Z0-9]/g, '')}`);
                        let read_mbps = 0, write_mbps = 0;
                        if (originalDiskName && metrics.disk_io[originalDiskName]) {
                            read_mbps = (metrics.disk_io[originalDiskName].read_bytes_per_sec || 0) / (1024 * 1024);
                            write_mbps = (metrics.disk_io[originalDiskName].write_bytes_per_sec || 0) / (1024 * 1024);
                        }
                        updateChartData(charts[chartId], newLabel, [read_mbps, write_mbps]);
                    }
                    else if (chartId.startsWith('netIoChart-')) {
                        const originalNicName = Object.keys(data.network_io || {}).find(nName => chartId === `netIoChart-${nName.replace(/[^a-zA-Z0-9]/g, '')}`);
                        let upload_mbps = 0, download_mbps = 0;
                        if (originalNicName && metrics.network_io[originalNicName]) {
                            upload_mbps = (metrics.network_io[originalNicName].upload_bits_per_sec || 0) / (1000 * 1000);
                            download_mbps = (metrics.network_io[originalNicName].download_bits_per_sec || 0) / (1000 * 1000);
                        }
                        updateChartData(charts[chartId], newLabel, [upload_mbps, download_mbps]);
                    }
                }
            })
            .catch(err => console.error("Failed to update performance charts:", err));
    }

    function createPieChart(canvasId, labels, dataPoints) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        if (charts[canvasId]) charts[canvasId].destroy();
        const colorPairs = [['#ff6384', '#ffb1c1'], ['#36a2eb', '#a8d5f5'], ['#ffce56', '#ffe6a7']];
        const bgColors = [];
        for (let j = 0; j < Math.ceil(labels.length / 2); j++) { bgColors.push(colorPairs[j % colorPairs.length][0]); bgColors.push(colorPairs[j % colorPairs.length][1]); }
        if (labels.some(l => l.includes('Unallocated'))) bgColors.push('#cccccc');
        charts[canvasId] = new Chart(ctx, { type: 'doughnut', data: { labels, datasets: [{ data: dataPoints, backgroundColor: bgColors, borderColor: 'var(--color-surface)', borderWidth: 2 }] }, options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => `${context.label}` } } } } });
    }

    function createMultiLineChart(canvasId, title, labels, datasets, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return; 
        if (charts[canvasId]) charts[canvasId].destroy();

        const defaultOptions = { isPercentage: false, yAxisMax: undefined };
        const finalOptions = { ...defaultOptions, ...options };

        const chartDatasets = datasets.map(ds => ({
            label: ds.label, data: ds.data, borderColor: ds.color,
            backgroundColor: ds.color.replace('1)', '0.2)'), fill: true,
            tension: 0.3, pointRadius: 1, borderWidth: 1.5,
        }));
        charts[canvasId] = new Chart(ctx, { 
            type: 'line', data: { labels, datasets: chartDatasets },
            options: { responsive: true, maintainAspectRatio: false,
                scales: { y: { beginAtZero: true, max: finalOptions.isPercentage ? 100 : finalOptions.yAxisMax },
                    x: { ticks: { display: true, autoSkip: true, maxTicksLimit: 12, maxRotation: 45, minRotation: 45 } }
                },
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 20, padding: 15 } } },
                animation: { duration: 0 }
            }
        });
    }

    // --- Grid Creation Functions ---
    function createWebHistoryGrid(dataArray) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) {
            return '<p>No data found.</p>';
        }
        const headers = [
            { key: 'title',           displayName: 'Title' },
            { key: 'url',             displayName: 'Url' },
            { key: 'last_visit_time', displayName: 'Last Visit Time' }
        ];        
        const gridTemplateColumns = "10% 20% 50% 20%";        
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headers.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const rowCells = headers.map(header => {
                let cellContent;
                if (header.key === 'url') { const url = row[header.key]; if (url && (url.startsWith('http://') || url.startsWith('https://'))) { cellContent = `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`; } else { cellContent = formatValue(header.key, url); } } else { cellContent = formatValue(header.key, row[header.key]); }
                return `<div class="grid-cell">${cellContent}</div>`; }).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${index + 1}</div>${rowCells}</div>`;
        }).join('');

        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createEventLogGrid(title, dataArray, currentPage, itemsPerPage) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No logs match the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [{ key: 'Id', displayName: 'Id' }, { key: 'LevelDisplayName', displayName: 'Level' }, { key: 'ProviderName', displayName: 'Provider Name' }, { key: 'Message', displayName: 'Message' }, { key: 'TimeCreated', displayName: 'Time Created' }];
        const gridTemplateColumns = "7% 8% 15% 15% 40% 15%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const globalIndex = (currentPage - 1) * itemsPerPage + index + 1;
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${globalIndex}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `
            ${titleHtml}
            <div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createServiceGrid(title, dataArray, currentPage, itemsPerPage) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No services match the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [{ key: 'DisplayName', displayName: 'Display Name' }, { key: 'Name', displayName: 'Name' }, { key: 'StartMode', displayName: 'Start Mode' }, { key: 'PathName', displayName: 'Path Name' }, { key: 'State', displayName: 'State' }];
        const gridTemplateColumns = "8% 22% 15% 10% 35% 10%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const globalIndex = (currentPage - 1) * itemsPerPage + index + 1;
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${globalIndex}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createProcessGrid(title, dataArray, currentPage, itemsPerPage) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No processes match the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [{ key: 'PID', displayName: 'PID' }, { key: 'Name', displayName: 'Name' }, { key: 'ExePath', displayName: 'Path' }, { key: 'MemoryRSS', displayName: 'Size' }, { key: 'Username', displayName: 'User' }, { key: 'CreateTime', displayName: 'Create Time' }, { key: 'Status', displayName: 'Status' }];
        const gridTemplateColumns = "5% 8% 10% 35% 8% 15% 10% 9%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const globalIndex = (currentPage - 1) * itemsPerPage + index + 1;
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${header.key === 'MemoryRSS' ? formatBytes(row[header.key]) : formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${globalIndex}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createSoftwareGrid(title, dataArray, currentPage, itemsPerPage) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No software matches the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [{ key: 'Name', displayName: 'Name' }, { key: 'EstimatedSizeByte', displayName: 'Size' }, { key: 'InstallDate', displayName: 'Install Date' }, { key: 'InstallLocation', displayName: 'Install Location' }, { key: 'Publisher', displayName: 'Publisher' }, { key: 'Version', displayName: 'Version' }, { key: 'Group', displayName: 'Group' }];
        const gridTemplateColumns = "5% 15% 10% 12% 27% 12% 9% 10%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const globalIndex = (currentPage - 1) * itemsPerPage + index + 1;
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${header.key === 'EstimatedSizeByte' ? formatBytes(row[header.key]) : formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${globalIndex}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createCredentialGrid(title, dataArray) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No credentials match the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [{ key: 'Target', displayName: 'Target' }, { key: 'Type', displayName: 'Type' }, { key: 'User', displayName: 'User' }, { key: 'Group', displayName: 'Group' }];
        const gridTemplateColumns = "5% 40% 20% 20% 15%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => `<div class="grid-row"><div class="grid-cell col-no">${index + 1}</div>${headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('')}</div>`).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }
    
    function createUserGrid(title, dataArray) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No data found.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [{ key: 'Name', displayName: 'Name' }, { key: 'FullName', displayName: 'Full Name' }, { key: 'AccountDomain', displayName: 'Account Domain' }, { key: 'SID_Value', displayName: 'SID Value' }, { key: 'Enabled', displayName: 'Enabled' }];
        const gridTemplateColumns = "10% 15% 15% 25% 25% 10%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => `<div class="grid-row"><div class="grid-cell col-no">${index + 1}</div>${headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('')}</div>`).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createStartupCommandsGrid(title, dataArray, currentPage, itemsPerPage) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No startup commands match the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [
            { key: 'Name', displayName: 'Name' },
            { key: 'Command', displayName: 'Command' },
            { key: 'Location', displayName: 'Location' },
            { key: 'User', displayName: 'User' }
        ];
        const gridTemplateColumns = "5% 20% 30% 30% 15%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const globalIndex = (currentPage - 1) * itemsPerPage + index + 1;
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${globalIndex}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    function createAutoStartServicesGrid(title, dataArray, currentPage, itemsPerPage) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No auto-start services match the current filter.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [
            { key: 'DisplayName', displayName: 'Display Name' },
            { key: 'Name', displayName: 'Service Name' },
            { key: 'PathName', displayName: 'Path' },
            { key: 'State', displayName: 'Current State' }
        ];
        const gridTemplateColumns = "5% 25% 20% 40% 10%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const globalIndex = (currentPage - 1) * itemsPerPage + index + 1;
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${globalIndex}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    // Hàm này không cần phân trang vì thường danh sách này rất ngắn, nhưng vẫn giữ để nhất quán
    function createScheduledTasksGridSimple(title, dataArray) {
        if (!Array.isArray(dataArray) || dataArray.length === 0) return title ? `<h3>${title}</h3><p>No scheduled tasks at logon found.</p>` : '<p>No data found.</p>';
        const headersToDisplay = [
            { key: 'TaskName', displayName: 'Task Name' },
            { key: 'TaskPath', displayName: 'Task Path' },
            { key: 'State', displayName: 'State' }
        ];
        const gridTemplateColumns = "5% 40% 45% 10%";
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headersToDisplay.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            const rowCells = headersToDisplay.map(header => `<div class="grid-cell">${formatValue(header.key, row[header.key])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${index + 1}</div>${rowCells}</div>`;
        }).join('');
        const titleHtml = title ? `<h3>${title}</h3>` : '';
        return `<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

    // --- Render Functions ---
    function renderBasicInfo() {
        const os = auditData.os?.data || {};
        const mainboard = auditData.mainboard?.data?.BaseBoard || {};
        const cpu = auditData.cpu?.data || {};
        const ram = auditData.ram?.data || [];
        const disk = auditData.disk?.data?.PhysicalDisks || [];
        const gpu = auditData.gpu?.data || [];

        const createUsageHTML = (label, type, unit = '%', isProgressBar = false) => {
            if (isProgressBar) return `<div class="key-value"><span class="key">${label}</span><div class="progress-bar-container"><div id="realtime-${type}-bar" class="progress-bar"><div id="realtime-${type}-fill" class="progress-bar-fill"></div><span id="realtime-${type}-text" class="progress-bar-text">0.0${unit}</span></div></div></div>`;
            return `<div class="key-value"><span class="key">${label}</span><div id="realtime-${type}-text" class="realtime-io-text">N/A</div></div>`;
        };
        
        const metricsContent = `${createUsageHTML('CPU Usage', 'cpu', '%', true)}${createUsageHTML('RAM Usage', 'ram', '%', true)}${createUsageHTML('Disk Usage', 'disk', '%', true)}<hr class="item-separator">${createUsageHTML('Disk Read', 'disk_read')}${createUsageHTML('Disk Write', 'disk_write')}<hr class="item-separator">${createUsageHTML('Net Upload', 'net_upload')}${createUsageHTML('Net Download', 'net_download')}`;
        let ramSummary = '', diskSummary = '', gpuSummary = '';
        if (ram.length > 0 && !ram[0].Error) ramSummary = renderKeyValue('Total Memory', `${ram.length} Sticks, ${formatBytes(ram.reduce((acc, r) => acc + (r.Capacity || 0), 0))} Total`);
        if (disk.length > 0 && !disk[0].Error) disk.forEach((d, i) => { diskSummary += renderKeyValue(`Disk ${i}`, `${d.Model || ''} (${formatBytes(d.Size)})`); });
        if (gpu.length > 0 && !gpu[0].Error && !gpu[0].Info) gpu.forEach((g, i) => { gpuSummary += renderKeyValue(`GPU ${i}`, `${g.Name || ''}`); });
        const hardwareContent = `${renderKeyValue('OS', os.Caption)}${renderKeyValue('Mainboard', `${mainboard.Manufacturer||''} ${mainboard.Product||''}`)}${renderKeyValue('Processor', cpu.Brand)}${ramSummary}${diskSummary}${gpuSummary}`;

        document.getElementById('basic-info').innerHTML = `<div class="content-grid grid-cols-2">${buildCard('basic-info','Realtime Usage','fa-tachometer-alt',metricsContent)}${buildCard('basic-info','Summary','fa-server',hardwareContent)}</div>`;
        updateRealtimeMetrics();
    }

    function renderPerformance() {
        const perfTab = document.getElementById('performance');
        perfTab.innerHTML = '<div id="performance-grid" class="content-grid grid-cols-2"></div>'; 
        const perfGrid = document.getElementById('performance-grid');

        fetch(`/api/client_metrics_history/${CLIENT_GUID}`)
            .then(res => { if (!res.ok) throw new Error(`API call failed with status ${res.status}`); return res.json(); })
            .then(data => {
                if (!data || !data.labels || data.labels.length === 0) {
                    perfGrid.innerHTML = buildCard('performance', 'Performance History', 'fa-solid fa-microchip', '<p>No performance history data available.</p>');
                    perfGrid.classList.remove('grid-cols-2'); return;
                }
                const convertBytesToMB = arr => (arr || []).map(v => (v || 0) / (1024 * 1024));
                const convertBitsToMb = arr => (arr || []).map(v => (v || 0) / (1000 * 1000));
                
                const chartsToRender = [
                    { id: 'cpuPerfChart', title: 'CPU Usage (%)', datasets: [{ label: 'CPU', data: data.cpu, color: 'rgba(253, 126, 20, 1)' }], options: { isPercentage: true }, icon: 'fa-solid fa-microchip' },
                    { id: 'ramPerfChart', title: 'RAM Usage (%)', datasets: [{ label: 'RAM', data: data.ram, color: 'rgba(13, 110, 253, 1)' }], options: { isPercentage: true }, icon: 'fa-solid fa-memory' }
                ];
                chartsToRender.forEach(chart => {
                    perfGrid.insertAdjacentHTML('beforeend', buildCard('performance', chart.title, chart.icon, `<div style="height: 300px;"><canvas id="${chart.id}"></canvas></div>`));
                    createMultiLineChart(chart.id, chart.title, data.labels, chart.datasets, chart.options);
                });

                Object.entries(data.disk_io || {}).forEach(([diskName, diskData]) => {
                    const chartId = `diskIoChart-${diskName.replace(/[^a-zA-Z0-9]/g, '')}`;
                    const title = `${diskName} (MB/s)`;
                    perfGrid.insertAdjacentHTML('beforeend', buildCard('performance', title, 'fa-solid fa-hdd', `<div style="height: 300px;"><canvas id="${chartId}"></canvas></div>`));
                    createMultiLineChart(chartId, title, data.labels, [{ label: 'Read', data: convertBytesToMB(diskData.read_bytes_per_sec), color: 'rgba(75, 192, 192, 1)' }, { label: 'Write', data: convertBytesToMB(diskData.write_bytes_per_sec), color: 'rgba(255, 99, 132, 1)' }]);
                });
                Object.entries(data.network_io || {}).forEach(([nicName, nicData]) => {
                    const chartId = `netIoChart-${nicName.replace(/[^a-zA-Z0-9]/g, '')}`;
                    const title = `Network: ${nicName} (Mbps)`;
                    perfGrid.insertAdjacentHTML('beforeend', buildCard('performance', title, 'fa-solid fa-ethernet', `<div style="height: 300px;"><canvas id="${chartId}"></canvas></div>`));
                    createMultiLineChart(chartId, title, data.labels, [{ label: 'Upload', data: convertBitsToMb(nicData.upload_bits_per_sec), color: 'rgba(255, 159, 64, 1)' }, { label: 'Download', data: convertBitsToMb(nicData.download_bits_per_sec), color: 'rgba(54, 162, 235, 1)' }]);
                });
            })
            .catch(error => {
                console.error('Error fetching or rendering performance charts:', error);
                perfGrid.innerHTML = buildCard('performance', 'Error', 'fa-exclamation-triangle', `<p>Could not load performance data.</p><pre>${error.message}</pre>`);
                perfGrid.classList.remove('grid-cols-2');
            });
    }

    function renderHardware() {
        const osCard = buildCard('hardware', 'Operating System', 'fa-brands fa-windows', Object.entries(auditData.os?.data || {}).map(([k, v]) => renderKeyValue(k, v)).join(''));
        const desiredProcessorOrder = ['Brand', 'Architecture', 'Bits', 'Logical Cores', 'Physical Cores', 'Machine', 'Platform', 'System', 'Version'];
        const processorCardContent = desiredProcessorOrder.map(key => auditData.cpu?.data.hasOwnProperty(key) ? renderKeyValue(key, auditData.cpu.data[key]) : '').join('');
        const processorCard = buildCard('hardware', 'Processor', 'fa-microchip', processorCardContent);
        
        let mainboardCardContent = '';
        if (auditData.mainboard?.data?.BaseBoard || auditData.mainboard?.data?.BIOS) {
            const baseboardHtml = auditData.mainboard.data.BaseBoard ? `<div><h3><i class="fa-solid fa-microchip"></i> BaseBoard</h3>${Object.entries(auditData.mainboard.data.BaseBoard).map(([k, v]) => renderKeyValue(k, v)).join('')}</div>` : '';
            const biosHtml = auditData.mainboard.data.BIOS ? `<div><h3><i class="fa-solid fa-bookmark"></i> BIOS</h3>${Object.entries(auditData.mainboard.data.BIOS).map(([k, v]) => renderKeyValue(k, v)).join('')}</div>` : '';
            mainboardCardContent = `<div class="column-layout grid-cols-2">${baseboardHtml}${biosHtml}</div>`;
        } else {
            mainboardCardContent = '<p>No Mainboard or BIOS data available.</p>';
        }
        const mainboardCard = buildCard('hardware', 'Mainboard & BIOS', 'fa-sitemap', mainboardCardContent);
        


        let memoryCardContent = '';
        const memoryData = auditData.ram?.data || [];
        if (memoryData.length > 0 && !memoryData[0].Error) {
            const ramBlocksHtml = memoryData.map(ram => {
                const slotName = ram.Slot || 'RAM Stick';
                const manufacturerCode = String(ram.Manufacturer || 'Unknown');
                const manufacturer = manufacturer_map[manufacturerCode] || manufacturerCode;
                const memoryTypeCode = ram.MemoryType;
                const memoryType = type_map[memoryTypeCode] || `Unknown (${memoryTypeCode})`;
                const formFactorCode = ram.FormFactor;
                const formFactor = form_map[formFactorCode] || `Unknown (${formFactorCode})`;
                const ram_map = {
                    ...ram,
                    Manufacturer: manufacturer, // Ghi đè giá trị đã giải mã
                    MemoryType: memoryType,
                    FormFactor: formFactor
                };
                const capacity = formatBytes(ram.Capacity || 0);
                const speedKeys = ['ConfiguredClockSpeed', 'Speed', 'BusSpeed'];
                let clockSpeed;
                for (const key of speedKeys) { if (ram[key]) { clockSpeed = Number(ram[key]); break; } }
                const effectiveSpeedMhz = clockSpeed ? (clockSpeed * (String(memoryType).toUpperCase().includes('DDR') ? 2 : 1)) : null; 
                const displaySpeedMhz = clockSpeed ? clockSpeed : null; 
                // const speedForTitle = displaySpeedMhz ? ` bus ${displaySpeedMhz} MHz` : 'MHz';
                const speedForTitle = displaySpeedMhz ? `${displaySpeedMhz * 8}` : '';
                const title = `${slotName}: ${manufacturer} ${memoryType}-${speedForTitle} ${capacity} `.replace(/\s+/g, ' ').trim();
                const handledKeys = ['Slot', ...speedKeys];
                const detailsHtml = Object.entries(ram_map).filter(([key]) => !handledKeys.includes(key)).map(([key, value]) => renderKeyValue(key, value)).join('');
                const finalDetailsHtml = detailsHtml + (displaySpeedMhz ? renderKeyValue('Bus', `${displaySpeedMhz} MHz`) : '');
                return `<div><h3><i class="fa-solid fa-memory"></i> ${title}</h3>${finalDetailsHtml}</div>`;
            }).join('');
            const gridClass = memoryData.length > 1 ? 'grid-cols-2' : 'grid-cols-1';
            memoryCardContent = `<div class="column-layout ${gridClass}">${ramBlocksHtml}</div>`;
        } else {
            memoryCardContent = '<p>No memory data available.</p>';
        }
        const memoryCard = buildCard('hardware', 'Memory (RAM)', 'fa-memory', memoryCardContent);
        


        let gpuCard = '';
        const gpuData = auditData.gpu?.data || [];
        if (Array.isArray(gpuData) && gpuData.length > 0 && !gpuData[0]?.Error) {
            const gpuBlocksHtml = gpuData.map(gpu => {
                const gpuDetails = { ...gpu };
                const title = gpuDetails.Name || 'GPU';
                delete gpuDetails.Name;
                return `<div><h3><i class="fa-solid fa-display"></i> ${title}</h3>${Object.entries(gpuDetails).map(([k, v]) => renderKeyValue(k, v)).join('')}</div>`;
            }).join('');
            const gridClass = gpuData.length === 1 ? 'grid-cols-1' : 'grid-cols-2';
            const gpuCardContent = `<div class="column-layout ${gridClass}">${gpuBlocksHtml}</div>`;
            gpuCard = buildCard('hardware', 'Graphics (GPU)', 'fa-tv', gpuCardContent);
        } else {
            gpuCard = buildCard('hardware', 'Graphics (GPU)', 'fa-tv', '<p>No GPU data available.</p>');
        }

        // --- LOGIC SẮP XẾP VÀ RENDER ĐỘNG ---
        let finalHtml = '';

        // Hàng 1: Luôn là OS và Processor
        finalHtml += `<div class="content-grid grid-cols-2">${osCard}${processorCard}</div>`;
        
        // Hàng 2: Luôn là Mainboard và Memory
        finalHtml += `<div class="content-grid grid-cols-1">${mainboardCard}</div>`;



        switch (true) {
            case (gpuData.length === 1 && memoryData.length === 1):
                finalHtml += `<div class="content-grid grid-cols-2">${memoryCard}${gpuCard}</div>`;
                break;

            case (memoryData.length === 1):
                finalHtml += `<div class="content-grid grid-cols-1">${gpuCard}</div>`;
                finalHtml += `<div class="content-grid grid-cols-2">${memoryCard}</div>`;
                break;

            case (gpuData.length === 1):
                finalHtml += `<div class="content-grid grid-cols-1">${memoryCard}</div>`;
                finalHtml += `<div class="content-grid grid-cols-2">${gpuCard}</div>`;
                break;

            default:
                finalHtml += `<div class="content-grid grid-cols-1">${memoryCard}</div>`;
                finalHtml += `<div class="content-grid grid-cols-1">${gpuCard}</div>`;
                break;
        }


        // Gán toàn bộ HTML đã tạo vào tab hardware
        document.getElementById('hardware').innerHTML = finalHtml;
    }

    function renderDisk() {
        const diskData = auditData.disk?.data || {};
        const diskTab = document.getElementById('disk');
        let finalHtml = '';
        const physicalDisks = diskData.PhysicalDisks || [];
        if (physicalDisks.length > 0 && !physicalDisks[0].Error) {
            const physicalDisksRows = physicalDisks.map((disk, i) => {
                const physicalInfo = { ...disk };
                delete physicalInfo.Partitions; delete physicalInfo.DeviceID; delete physicalInfo.Model;
                const physicalCardContent = `<div class="pie-chart-container"><canvas id="diskPieChart-${i}"></canvas></div>${Object.entries(physicalInfo).map(([k, v]) => renderKeyValue(k, v)).join('')}`;
                const physicalCard = buildCard('disk', disk.Model || `Physical Disk ${i}`, 'fa-hard-drive', physicalCardContent);
                const logicalDisks = (disk.Partitions || []).flatMap(p => p.LogicalDisks || []);
                let logicalCardContent = logicalDisks.length > 0 ? logicalDisks.map(ld => {
                    const ldInfo = {...ld}, ldTitle = ldInfo.DeviceID || 'Logical Partition';
                    delete ldInfo.DeviceID;
                    return `<h3><i class="fa-solid fa-folder-open"></i> ${ldTitle} (${ldInfo.VolumeName || 'No Name'})</h3>${Object.entries(ldInfo).map(([k,v]) => renderKeyValue(k,v)).join('')}`;
                }).join('<hr class="item-separator">') : '<p>No logical partitions found.</p>';
                const logicalCard = `<div class="info-card scrollable-card"><div class="card-content">${logicalCardContent}</div></div>`;
                return `<div class="_info-card"><div class="card-content"><div class="content-grid grid-cols-2">${physicalCard}${logicalCard}</div></div></div>`;
            }).join('');
            finalHtml += `<div class="content-grid grid-cols-1">${physicalDisksRows}</div>`;
        }
        const networkDrives = diskData.NetworkDrives || [];
        if (networkDrives.length > 0) {
            const networkDrivesContent = networkDrives.map((drive, i) => buildCard('disk', drive.DeviceID || `Net Drive ${i}`, 'fa-server', renderKeyValue('Provider Name', drive.ProviderName))).join('');
            finalHtml += `<div class="info-card"><h2><i class="fa-solid fa-network-wired"></i> Network Drives</h2><div class="card-content"><div class="content-grid grid-cols-2">${networkDrivesContent}</div></div></div>`;
        }
        diskTab.innerHTML = finalHtml.trim() === '' ? buildCard('disk', 'Storage', 'fa-hdd', '<p>No disk data.</p>') : finalHtml;
        physicalDisks.forEach((disk, i) => {
            const logicalDisks = (disk.Partitions || []).flatMap(p => p.LogicalDisks || []);
            if (logicalDisks.length === 0) return;
            const labels = [], dataPoints = [];
            let totalAllocatedSpace = 0;
            logicalDisks.forEach(ld => {
                const size = ld.Size || 0, free = ld.FreeSpace || 0, used = size - free;
                labels.push(`${ld.DeviceID} Used (${formatBytes(used)})`); dataPoints.push(used);
                labels.push(`${ld.DeviceID} Free (${formatBytes(free)})`); dataPoints.push(free);
                totalAllocatedSpace += size;
            });
            const unallocatedSpace = (disk.Size || 0) - totalAllocatedSpace;
            if (unallocatedSpace > 1024 * 1024) { labels.push(`Unallocated (${formatBytes(unallocatedSpace)})`); dataPoints.push(unallocatedSpace); }
            createPieChart(`diskPieChart-${i}`, labels, dataPoints);
        });
    }
    
    function renderNetwork() {
        const networkAdapters = auditData.network?.data || [];
        const networkTab = document.getElementById('network');
        if (networkAdapters.length === 0 || (networkAdapters.length > 0 && networkAdapters[0].Error)) {
            networkTab.innerHTML = buildCard('network', 'Network Adapters', 'fa-ethernet', '<p>No network data available.</p>');
            return;
        }
        const content = networkAdapters.map(adapter => {
            const adapterDetails = {...adapter};
            const name = adapterDetails.NetConnectionID || adapterDetails.Description || 'Network Adapter';
            let titleHtml = `<div class="network-card-title"><span>${name}</span>`;
            if (adapterDetails.Status && adapterDetails.Status.toLowerCase() === 'connected') titleHtml += `<span class="status-badge connected">Connected</span>`;
            titleHtml += `</div>`;
            delete adapterDetails.NetConnectionID; delete adapterDetails.Description;
            const detailsHtml = Object.entries(adapterDetails).map(([k,v]) => renderKeyValue(k,v)).join('');
            return buildCard('network', titleHtml, 'fa-ethernet', detailsHtml);
        }).join('');
        networkTab.innerHTML = `<div class="content-grid grid-cols-2">${content}</div>`;
    }

    function renderPeripherals() {
        const printers = auditData.printers?.data || [];
        if (printers.length === 0 || (printers.length > 0 && printers[0].Error)) {
             document.getElementById('peripherals').innerHTML = buildCard('peripherals', 'Printers', 'fa-print', '<p>No printer data.</p>');
             return;
        }
        
        const content = printers.map(p => {
            // --- LOGIC DECODE MỚI TẠI ĐÂY ---
            const statusList = decodeBitmask(printer_status_map, p.Status);
            const attributesList = decodeBitmask(printer_attributes_map, p.Attributes);
            
            const statusText = (statusList.length > 0) ? statusList.join(', ') : 'Ready';

            const printerDetails = {
                ...p,
                Status: statusText, // Ghi đè mã số bằng chuỗi đã giải mã
                Attributes: attributesList.join(', ') || 'None' // Thay thế bằng chuỗi thuộc tính
            };
            // --- KẾT THÚC LOGIC DECODE ---

            let titleHtml = `<i class="fa-solid fa-print"></i> <span class="printer-name">${printerDetails['Printer Name'] || 'Unknown'}</span>`;
            if (printerDetails.Default) {
                titleHtml += `<span class="printer-badge status-badge default">Default</span>`;
            }
            
            // Xóa các key không cần hiển thị lặp lại trong phần chi tiết
            delete printerDetails['Printer Name'];
            delete printerDetails.Default;
            delete printerDetails.Attributes;
            
            const orderedKeys = [
                'Online',
                'Status',
                'Jobs in Queue',
                'Port Name',
                'Driver Name',
                'Attributes' // Chúng ta sẽ xử lý key này một cách đặc biệt
            ];

            let detailsHtml = '';

            // 2. Lặp qua mảng thứ tự và tạo HTML
            orderedKeys.forEach(key => {
                if (p.hasOwnProperty(key)) {
                    let value = p[key];
                    
                    // Xử lý các trường hợp đặc biệt
                    if (key === 'Status') {
                        value = statusText; // Sử dụng giá trị đã giải mã
                        detailsHtml += renderKeyValue(key, value);
                    } else if (key === 'Attributes') {
                        // Render riêng cho "Attributes" với định dạng thẻ <p>
                        if (attributesList.length > 0) {
                            const attributesHtml = attributesList.map(attr => `<p>${attr}</p>`).join('');
                            detailsHtml += `
                                <div class="key-value">
                                    <span class="key">Attributes</span>
                                    <div class="value attributes-list">${attributesHtml}</div>
                                </div>
                            `;
                        } else {
                            detailsHtml += renderKeyValue('Attributes', 'None');
                        }
                    } else {
                        // Render các key-value bình thường
                        detailsHtml += renderKeyValue(key, value);
                    }
                }
            });
            
            return buildCard('peripherals', titleHtml, null, detailsHtml);
        }).join('');
        
        document.getElementById('peripherals').innerHTML = `<div class="content-grid grid-cols-2">${content}</div>`;
    }

    function renderSecurity() {
        const credentialsData = auditData.credentials?.data || {};
        const securityContainer = document.getElementById('security');
        if (Object.keys(credentialsData).length === 0) {
            securityContainer.innerHTML = buildCard('security', 'Stored Credentials', 'fa-key', '<p>No data.</p>');
            return;
        }
        const allCredentials = Object.entries(credentialsData).flatMap(([group, items]) => {
            if (!Array.isArray(items)) return [];
            return items.map(item => ({ ...item, Group: group }));
        });
        allCredentials.sort((a, b) => (a.Target || '').toLowerCase().localeCompare((b.Target || '').toLowerCase()));
        
        const layoutHtml = PaginatedTableManager.renderLayout('Filter by Group:', 'credential-group-filter', 'credential-grid-container', 'credential-pagination-container');
        securityContainer.innerHTML = buildCard('security', 'Stored Credentials', 'fa-key', layoutHtml);

        tableManagers.credentials = new PaginatedTableManager({
            itemsPerPage: ITEMS_PER_PAGE, filterKey: 'Group', createGridFn: createCredentialGrid,
            cardTitle: 'Stored Credentials', filterLabel: 'Filter by Group:',
            gridContainerId: 'credential-grid-container', paginationContainerId: 'credential-pagination-container',
            filterSelectId: 'credential-group-filter', prevBtnId: 'credential-prev-btn', nextBtnId: 'credential-next-btn'
        });
        tableManagers.credentials.loadData(allCredentials);
    }
    
    function renderUsers() {
        const usersData = auditData.users?.data || {};
        let content = '';
        if (usersData && usersData.CurrentUser) content += renderKeyValue('Current User', usersData.CurrentUser, true);
        if (usersData && Array.isArray(usersData.LocalUsers)) {
            const processedUsers = usersData.LocalUsers.map(user => ({ Name: user.Name, FullName: user.FullName, AccountDomain: user.SID?.AccountDomainSid, SID_Value: user.SID?.Value, Enabled: user.Enabled }));
            content += createUserGrid('Local Users', processedUsers);
        }
        document.getElementById('users').innerHTML = buildCard('users', 'User Accounts', 'fa-users', content);
    }

    function renderHistory() {
        const historyData = auditData.web_history?.data || {};
        const historyContainer = document.getElementById('history');
        const browsersWithData = Object.entries(historyData).filter(([_, profiles]) => !profiles.Info && Object.keys(profiles).length > 0);
        if (browsersWithData.length === 0) {
            historyContainer.innerHTML = buildCard('history', 'Web History', 'fa-globe', '<p>No web history data found.</p>');
            return;
        }
        const content = browsersWithData.map(([browser, profiles]) => {
            const profilesHtml = Object.entries(profiles).map(([profile, items]) => `<h3 class="toggle-header">${profile}</h3><div class="toggle-content">${createWebHistoryGrid(items)}</div>`).join('');
            return buildCard('history', browser, 'fa-globe', profilesHtml);
        }).join('');
        historyContainer.innerHTML = `<div class="content-grid grid-cols-1">${content}</div>`;
    }
    
    function renderStartup() {
        const startupData = auditData.startup?.data || {};
        const startupContainer = document.getElementById('startup');

        if (Object.keys(startupData).length === 0 || (startupData.AutoStartServices && startupData.AutoStartServices[0]?.Error)) {
            startupContainer.innerHTML = buildCard('startup', 'Startup Items', 'fa-rocket', '<p>No startup data available or an error occurred.</p>');
            return;
        }

        let content = '';
        
        // --- 1. Startup Commands (với Phân trang & Filter) ---
        const commandsData = startupData.Commands || [];
        // Sử dụng PaginatedTableManager.renderLayout để tạo khung HTML
        const commandsLayoutHtml = PaginatedTableManager.renderLayout(
            'Filter by User:', 
            'startup-commands-user-filter', 
            'startup-commands-grid-container', 
            'startup-commands-pagination-container'
        );
        content += buildCard('startup', 'Startup Commands', 'fa-terminal', commandsLayoutHtml);
        
        // --- 2. Auto-Start Services (với Phân trang & Filter) ---
        const autoServicesData = startupData.AutoStartServices || [];
        const servicesLayoutHtml = PaginatedTableManager.renderLayout(
            'Filter by State:', 
            'startup-services-state-filter', 
            'startup-services-grid-container', 
            'startup-services-pagination-container'
        );
        content += buildCard('startup', 'Auto-Start Services (3rd Party)', 'fa-cogs', servicesLayoutHtml);
        
        // --- 3. Scheduled Tasks (Hiển thị đơn giản, không phân trang) ---
        const scheduledTasksData = startupData.ScheduledTasks || [];
        content += buildCard('startup', 'Scheduled Tasks (At Logon)', 'fa-clock', createScheduledTasksGridSimple(null, scheduledTasksData));
        
        // --- Render toàn bộ nội dung ---
        startupContainer.innerHTML = `<div class="content-grid grid-cols-1">${content}</div>`;
        
        // --- Khởi tạo Paginator cho Commands ---
        // (Phải thực hiện sau khi đã render HTML vào trang)
        if (commandsData.length > 0) {
            tableManagers.startupCommands = new PaginatedTableManager({
                itemsPerPage: 10, // Giới hạn 10 mục
                filterKey: 'User',
                createGridFn: createStartupCommandsGrid,
                cardTitle: 'Startup Commands',
                filterLabel: 'Filter by User:',
                containerId: 'startup-commands-container', // ID của card
                gridContainerId: 'startup-commands-grid-container',
                paginationContainerId: 'startup-commands-pagination-container',
                filterSelectId: 'startup-commands-user-filter',
                prevBtnId: 'startup-commands-prev-btn',
                nextBtnId: 'startup-commands-next-btn'
            });
            tableManagers.startupCommands.loadData(commandsData);
        }
        
        // --- Khởi tạo Paginator cho Services ---
        if (autoServicesData.length > 0) {
            tableManagers.startupServices = new PaginatedTableManager({
                itemsPerPage: 10, // Giới hạn 10 mục
                filterKey: 'State',
                createGridFn: createAutoStartServicesGrid,
                cardTitle: 'Auto-Start Services (3rd Party)',
                filterLabel: 'Filter by State:',
                containerId: 'startup-services-container',
                gridContainerId: 'startup-services-grid-container',
                paginationContainerId: 'startup-services-pagination-container',
                filterSelectId: 'startup-services-state-filter',
                prevBtnId: 'startup-services-prev-btn',
                nextBtnId: 'startup-services-next-btn'
            });
            tableManagers.startupServices.loadData(autoServicesData);
        }
    }

    // --- Paginated/Filtered Render Functions ---
    function renderLogs() {
        const logsContainer = document.getElementById('logs');
        const layoutHtml = PaginatedTableManager.renderLayout('Filter by Level:', 'log-level-filter', 'log-grid-container', 'log-pagination-container');
        logsContainer.innerHTML = buildCard('logs', 'Event Logs', 'fa-clipboard-list', layoutHtml);
    
        tableManagers.logs = new PaginatedTableManager({
            itemsPerPage: ITEMS_PER_PAGE, filterKey: 'LevelDisplayName', createGridFn: createEventLogGrid,
            cardTitle: 'System Log', filterLabel: 'Filter by Level:',
            gridContainerId: 'log-grid-container', paginationContainerId: 'log-pagination-container',
            filterSelectId: 'log-level-filter', prevBtnId: 'log-prev-btn', nextBtnId: 'log-next-btn'
        });
        tableManagers.logs.loadData(auditData.event_log?.data || []);
    }

    function renderServices() {
        const servicesContainer = document.getElementById('services');
        if (!auditData.services?.data || auditData.services.data.Error) {
            servicesContainer.innerHTML = buildCard('services', 'Services', 'fa-concierge-bell', '<p>No data.</p>');
            return;
        }
        const layoutHtml = PaginatedTableManager.renderLayout('Filter by State:', 'service-state-filter', 'service-grid-container', 'service-pagination-container');
        servicesContainer.innerHTML = buildCard('services', 'Services', 'fa-concierge-bell', layoutHtml);
        
        tableManagers.services = new PaginatedTableManager({
            itemsPerPage: ITEMS_PER_PAGE, filterKey: 'State', createGridFn: createServiceGrid,
            cardTitle: 'Services', filterLabel: 'Filter by State:',
            gridContainerId: 'service-grid-container', paginationContainerId: 'service-pagination-container',
            filterSelectId: 'service-state-filter', prevBtnId: 'service-prev-btn', nextBtnId: 'service-next-btn'
        });
        const allServicesData = Object.values(auditData.services.data).flat();
        tableManagers.services.loadData(allServicesData);
    }
    
    function renderRuntime() {
        const runtimeContainer = document.getElementById('runtime');
        if (!auditData.processes?.data || auditData.processes.data.Error) {
            runtimeContainer.innerHTML = buildCard('runtime', 'Processes', 'fa-cogs', '<p>No data.</p>');
            return;
        }
        const layoutHtml = PaginatedTableManager.renderLayout('Filter by Status:', 'process-status-filter', 'process-grid-container', 'process-pagination-container');
        runtimeContainer.innerHTML = buildCard('runtime', 'Processes', 'fa-cogs', layoutHtml);
    
        tableManagers.processes = new PaginatedTableManager({
            itemsPerPage: ITEMS_PER_PAGE, filterKey: 'Status', createGridFn: createProcessGrid,
            cardTitle: 'Processes', filterLabel: 'Filter by Status:',
            gridContainerId: 'process-grid-container', paginationContainerId: 'process-pagination-container',
            filterSelectId: 'process-status-filter', prevBtnId: 'process-prev-btn', nextBtnId: 'process-next-btn'
        });
        const allProcessesData = Object.entries(auditData.processes.data).flatMap(([user, procs]) => procs.map(proc => ({ ...proc, Username: user })));
        allProcessesData.sort((a, b) => a.Name.toLowerCase().localeCompare(b.Name.toLowerCase()));
        tableManagers.processes.loadData(allProcessesData);
    }
    
    function renderSoftware() {
        const softwareContainer = document.getElementById('software');
        if (!auditData.software?.data || auditData.software.data.Error) {
            softwareContainer.innerHTML = buildCard('software', 'Software', 'fa-cubes', '<p>No data.</p>');
            return;
        }
        const layoutHtml = PaginatedTableManager.renderLayout('Filter by Group:', 'software-group-filter', 'software-grid-container', 'software-pagination-container');
        softwareContainer.innerHTML = buildCard('software', 'Installed Software', 'fa-cubes', layoutHtml);
    
        tableManagers.software = new PaginatedTableManager({
            itemsPerPage: ITEMS_PER_PAGE, filterKey: 'Group', createGridFn: createSoftwareGrid,
            cardTitle: 'Installed Software', filterLabel: 'Filter by Group:',
            gridContainerId: 'software-grid-container', paginationContainerId: 'software-pagination-container',
            filterSelectId: 'software-group-filter', prevBtnId: 'software-prev-btn', nextBtnId: 'software-next-btn'
        });
        const allSoftwareData = Object.entries(auditData.software.data).flatMap(([group, items]) => {
            if (!Array.isArray(items)) return [];
            return items.map(item => ({ ...item, Group: group }));
        });
        allSoftwareData.sort((a, b) => (a.Name || '').toLowerCase().localeCompare((b.Name || '').toLowerCase()));
        tableManagers.software.loadData(allSoftwareData);
    }
    
    // --- Main Fetch and Render Call ---
    function fetchDataAndRender() {
        fetch(`/api/client_audit_data/${CLIENT_GUID}`).then(res => res.json()).then(data => {
            auditData = data;
            renderBasicInfo(); renderPerformance(); renderHardware(); renderDisk(); renderNetwork(); renderPeripherals();
            renderSecurity(); renderUsers(); renderSoftware(); renderRuntime(); renderServices(); renderLogs(); renderHistory();renderStartup();
        }).catch(err => {
            console.error("Failed to fetch audit data:", err);
            document.querySelector('.tabs-container').innerHTML = `<p style="color:red;text-align:center;">Error loading client details.</p>`;
        });
    }

    // --- Initialization ---
    fetchDataAndRender();
    updateServerStatus();
    setInterval(updateServerStatus, SERVER_STATUS_INTERVAL);
    setInterval(updateRealtimeMetrics, REALTIME_METRICS_INTERVAL);
    setInterval(updatePerformanceCharts, REALTIME_METRICS_INTERVAL);
});