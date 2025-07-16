// static/js/detail.js

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

    // --- Helper Functions ---
    function getUsageLevelClass(percentage) {
        if (percentage < 35) return 'level-low';
        if (percentage < 70) return 'level-medium';
        return 'level-high';
    }

    function formatSpeed(mbps, unit = 'Mbps') {
        if (mbps === null || mbps === undefined) return 'N/A';
        if (mbps < 1) {
            // Nếu nhỏ hơn 1 Mbps/MBps, chuyển sang Kbps/KBps
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

        // Mặc định, nếu không có loại bộ nhớ, hiển thị giá trị gốc.
        let effectiveSpeed = clockSpeedMhz;
        
        // Nếu là loại DDR, nhân đôi tốc độ xung nhịp để có tốc độ hiệu dụng.
        const typeStr = String(memoryType).toUpperCase();
        if (typeStr.includes('DDR')) {
            effectiveSpeed = clockSpeedMhz * 2;
        }

        // MT/s (MegaTransfers per second) là đơn vị chính xác về mặt kỹ thuật,
        // nhưng MHz vẫn được sử dụng rộng rãi. Ta có thể chọn 1 trong 2. MT/s tốt hơn.
        return `${effectiveSpeed} MT/s`;
    }
    
    function formatValue(key, value) {
        if (value === null || value === undefined || value === '') return 'N/A';
        
        // Xử lý ngày tháng từ WMIC
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

        // Xử lý kích thước (Bytes, Size, Capacity, Space)
        if (lowerKey.includes('bytes') || lowerKey.includes('size') || lowerKey.includes('capacity') || lowerKey.includes('space')) {
            return formatBytes(Number(value)); // Đảm bảo value là số
        }

        // *** LOGIC MỚI ĐỂ XỬ LÝ TỐC ĐỘ MẠNG ***
        // Dữ liệu 'Speed' từ NetworkAudit là bits per second
        if (lowerKey === 'speed' && typeof value === 'number') {
            if (value >= 1000000000) {
                // Chuyển sang Gbps
                return `${(value / 1000000000).toFixed(1)} Gbps`;
            }
            if (value >= 1000000) {
                // Chuyển sang Mbps
                return `${(value / 1000000).toFixed(0)} Mbps`;
            }
            if (value >= 1000) {
                // Chuyển sang Kbps
                return `${(value / 1000).toFixed(0)} Kbps`;
            }
            if (value > 0) {
                return `${value} bps`;
            }
            // Giữ nguyên các giá trị MHz cho RAM/CPU
            if (String(value).includes('MHz')) return value;
        }
        
        // Giữ lại logic cũ cho tốc độ RAM/CPU (MHz)
        if (lowerKey.includes('speed') && !lowerKey.includes('bps')) {
            return `${value}`;
        }

        // Xử lý giá trị boolean
        if (typeof value === 'boolean') {
            return value ? '<span style="color:var(--color-success); font-weight:bold;">Enabled</span>' : '<span style="color:var(--color-danger); font-weight:bold;">Disabled</span>';
        }
        
        // Trả về giá trị gốc nếu không khớp với quy tắc nào
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
            : title; // Accept pre-formatted HTML title
        return `
            <div class="info-card ${extraClasses}">
                ${titleHtml}
                <div class="card-content">${content}</div>
            </div>`;
    }

    function createGrid(title, dataArray) {
        if (!Array.isArray(dataArray) || dataArray.length === 0 || (dataArray.length === 1 && dataArray[0].Error)) {
            return title ? `<h3>${title}</h3><p>No data found.</p>` : '<p>No data found.</p>';
        }
        const headers = Object.keys(dataArray[0]).map(key => ({ originalKey: key, displayName: formatKey(key) }));
        const headerHtml = `<div class="grid-header"><div class="grid-cell col-no">No.</div>${headers.map(h => `<div class="grid-cell">${h.displayName}</div>`).join('')}</div>`;
        const bodyHtml = dataArray.map((row, index) => {
            if (typeof row !== 'object' || row === null) return '';
            const rowCells = headers.map(header => `<div class="grid-cell">${formatValue(header.originalKey, row[header.originalKey])}</div>`).join('');
            return `<div class="grid-row"><div class="grid-cell col-no">${index + 1}</div>${rowCells}</div>`;
        }).join('');
        const gridTemplateColumns = `50px repeat(${headers.length}, minmax(150px, 1fr))`;
        return `${title ? `<h3>${title}</h3>` : ''}<div class="table-responsive"><div class="data-grid" style="grid-template-columns: ${gridTemplateColumns};">${headerHtml}${bodyHtml}</div></div>`;
    }

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

                // --- THAY ĐỔI Ở ĐÂY: Sửa lại hàm updateText ---
                const updateText = (type, value, unit, isBits = false) => {
                    const textElement = document.getElementById(`realtime-${type}-text`);
                    if (!textElement) return;

                    if (isBits) {
                        // Sử dụng hàm format từ bits
                        textElement.textContent = formatSpeedFromBits(value, 2);
                    } else {
                        // Sử dụng hàm format từ bytes
                        textElement.textContent = formatSpeedFromBps(value, 2);
                    }
                };
                
                if (data.status === 'success' && data.metrics) {
                    const metrics = data.metrics;
                    
                    // Cập nhật progress bar như cũ
                    updateProgressBar('cpu', metrics.cpu_usage);
                    updateProgressBar('ram', metrics.ram_usage);
                    updateProgressBar('disk', metrics.disk_usage);
                    
                    // --- LOGIC MỚI: Tính tổng I/O ---
                    
                    // 1. Tính tổng Disk I/O (bytes/s)
                    let totalDiskRead = 0;
                    let totalDiskWrite = 0;
                    if (metrics.disk_io) {
                        for (const disk in metrics.disk_io) {
                            totalDiskRead += metrics.disk_io[disk].read_bytes_per_sec || 0;
                            totalDiskWrite += metrics.disk_io[disk].write_bytes_per_sec || 0;
                        }
                    }

                    // 2. Tính tổng Network I/O (bits/s)
                    let totalNetUpload = 0;
                    let totalNetDownload = 0;
                    if (metrics.network_io) {
                        for (const nic in metrics.network_io) {
                            totalNetUpload += metrics.network_io[nic].upload_bits_per_sec || 0;
                            totalNetDownload += metrics.network_io[nic].download_bits_per_sec || 0;
                        }
                    }

                    // 3. Cập nhật giao diện với giá trị tổng
                    updateText('disk_read', totalDiskRead, 'B/s');
                    updateText('disk_write', totalDiskWrite, 'B/s');
                    updateText('net_upload', totalNetUpload, 'bps', true); // isBits = true
                    updateText('net_download', totalNetDownload, 'bps', true); // isBits = true

                } else {
                    // Reset tất cả về 0 hoặc N/A
                    updateProgressBar('cpu', 0);
                    updateProgressBar('ram', 0);
                    updateProgressBar('disk', 0);
                    updateText('disk_read', 0, 'B/s');
                    updateText('disk_write', 0, 'B/s');
                    updateText('net_upload', 0, 'bps', true);
                    updateText('net_download', 0, 'bps', true);
                }
            })
            .catch(err => console.error("Failed to fetch realtime metrics:", err));
    }

    // FILE: detail.js

    function updatePerformanceCharts() {
        const performanceTab = document.getElementById('performance');
        if (!performanceTab.classList.contains('active') || Object.keys(charts).length === 0) {
            return;
        }

        fetch(`/api/client_realtime_metrics/${CLIENT_GUID}`)
            .then(res => res.json())
            .then(data => {
                if (data.status !== 'success' || !data.metrics) {
                    return;
                }

                const newLabel = new Date().toLocaleTimeString('en-GB');
                const { metrics } = data;
                const MAX_POINTS = 50;

                const updateChartData = (chart, label, newPoints) => {
                    if (!chart) return;
                    chart.data.labels.push(label);
                    newPoints.forEach((point, index) => {
                        if (chart.data.datasets[index]) {
                            chart.data.datasets[index].data.push(point || 0);
                        }
                    });
                    while (chart.data.labels.length > MAX_POINTS) {
                        chart.data.labels.shift();
                        chart.data.datasets.forEach(dataset => {
                            dataset.data.shift();
                        });
                    }
                    chart.update('none');
                };

                // Cập nhật từng biểu đồ riêng biệt
                updateChartData(charts['cpuPerfChart'], newLabel, [metrics.cpu_usage]);
                updateChartData(charts['ramPerfChart'], newLabel, [metrics.ram_usage]);
                updateChartData(charts['diskPerfChart'], newLabel, [metrics.disk_usage]);
                
                // Cập nhật các biểu đồ I/O (logic giữ nguyên)
                for (const chartId in charts) {
                    if (chartId.startsWith('diskIoChart-')) {
                        const originalDiskName = Object.keys(data.disk_io || {}).find(
                            dName => chartId === `diskIoChart-${dName.replace(/[^a-zA-Z0-9]/g, '')}`
                        );
                        let read_mb_per_sec = 0, write_mb_per_sec = 0;
                        if (originalDiskName && metrics.disk_io[originalDiskName]) {
                            const diskMetrics = metrics.disk_io[originalDiskName];
                            read_mb_per_sec = (diskMetrics.read_bytes_per_sec || 0) / (1024 * 1024);
                            write_mb_per_sec = (diskMetrics.write_bytes_per_sec || 0) / (1024 * 1024);
                        }
                        updateChartData(charts[chartId], newLabel, [read_mb_per_sec, write_mb_per_sec]);
                    }
                    else if (chartId.startsWith('netIoChart-')) {
                        const originalNicName = Object.keys(data.network_io || {}).find(
                            nName => chartId === `netIoChart-${nName.replace(/[^a-zA-Z0-9]/g, '')}`
                        );
                        let upload_mbps = 0, download_mbps = 0;
                        if (originalNicName && metrics.network_io[originalNicName]) {
                            const netMetrics = metrics.network_io[originalNicName];
                            upload_mbps = (netMetrics.upload_bits_per_sec || 0) / (1000 * 1000);
                            download_mbps = (netMetrics.download_bits_per_sec || 0) / (1000 * 1000);
                        }
                        updateChartData(charts[chartId], newLabel, [upload_mbps, download_mbps]);
                    }
                }
            })
            .catch(err => console.error("Failed to update performance charts:", err));
    }

    function createLineChart(canvasId, label, labels, data, color) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        if (charts[canvasId]) charts[canvasId].destroy();
        charts[canvasId] = new Chart(ctx, { type: 'line', data: { labels, datasets: [{ label, data, borderColor: color, backgroundColor: color.replace('0.6', '0.2'), fill: true, tension: 0.3, pointRadius: 2 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, max: 100 } }, animation: { duration: 0 } } });
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
        const container = document.getElementById('performance');
        if (!document.getElementById(canvasId)) {
            const chartCardHtml = buildCard('performance', title, 'fa-chart-line', `<div style="height: 300px;"><canvas id="${canvasId}"></canvas></div>`);
            container.insertAdjacentHTML('beforeend', chartCardHtml);
        }

        const ctx = document.getElementById(canvasId);
        if (!ctx) return; 
        
        if (charts[canvasId]) {
            charts[canvasId].destroy();
        }

        const defaultOptions = { isPercentage: false, yAxisMax: undefined };
        const finalOptions = { ...defaultOptions, ...options };

        const chartDatasets = datasets.map(ds => ({
            label: ds.label,
            data: ds.data,
            borderColor: ds.color,
            backgroundColor: ds.color.replace('1)', '0.2)'),
            fill: true,
            tension: 0.3,
            pointRadius: 1,
            borderWidth: 1.5,
        }));

        charts[canvasId] = new Chart(ctx, { 
            type: 'line', 
            data: { 
                labels: labels, // Tham số labels
                datasets: chartDatasets // Tham số datasets
            },
            options: { 
                responsive: true, 
                maintainAspectRatio: false,
                scales: { 
                    y: { 
                        beginAtZero: true,
                        max: finalOptions.isPercentage ? 100 : finalOptions.yAxisMax 
                    },
                    x: { 
                        ticks: { 
                            display: true,
                            autoSkip: true,
                            maxTicksLimit: 12,
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            boxWidth: 20,
                            padding: 15
                        }
                    }
                },
                animation: { duration: 0 }
            }
        });
    }

    function renderBasicInfo() {
        const os = auditData.os?.data || {};
        const mainboard = auditData.mainboard?.data?.BaseBoard || {};
        const cpu = auditData.cpu?.data || {};
        const ram = auditData.ram?.data || [];
        const disk = auditData.disk?.data?.PhysicalDisks || [];
        const gpu = auditData.gpu?.data || [];

        // Hàm nội bộ để tạo cấu trúc HTML
        const createUsageHTML = (label, type, unit = '%', isProgressBar = false) => {
            // Nếu là progress bar
            if (isProgressBar) {
                return `
                    <div class="key-value">
                        <span class="key">${label}</span>
                        <div class="progress-bar-container">
                            <div id="realtime-${type}-bar" class="progress-bar">
                                <div id="realtime-${type}-fill" class="progress-bar-fill"></div>
                                <span id="realtime-${type}-text" class="progress-bar-text">0.0${unit}</span>
                            </div>
                        </div>
                    </div>`;
            }
            // Nếu chỉ là text
            return `
                <div class="key-value">
                    <span class="key">${label}</span>
                    <div id="realtime-${type}-text" class="realtime-io-text">N/A</div>
                </div>`;
        };
        
        // Xây dựng nội dung cho card Realtime Usage
        const metricsContent = `
            ${createUsageHTML('CPU Usage', 'cpu', '%', true)}
            ${createUsageHTML('RAM Usage', 'ram', '%', true)}
            ${createUsageHTML('Disk Usage', 'disk', '%', true)}
            <hr class="item-separator">
            ${createUsageHTML('Disk Read', 'disk_read', 'MB/s')}
            ${createUsageHTML('Disk Write', 'disk_write', 'MB/s')}
            <hr class="item-separator">
            ${createUsageHTML('Net Upload', 'net_upload', 'Mbps')}
            ${createUsageHTML('Net Download', 'net_download', 'Mbps')}
        `;
        let ramSummary = '', diskSummary = '', gpuSummary = '';
        if (ram.length > 0 && !ram[0].Error) ramSummary = renderKeyValue('Total Memory', `${ram.length} Sticks, ${formatBytes(ram.reduce((acc, r) => acc + (r.Capacity || 0), 0))} Total`);
        if (disk.length > 0 && !disk[0].Error) disk.forEach((d, i) => { diskSummary += renderKeyValue(`Disk ${i}`, `${d.Model || ''} (${formatBytes(d.Size)})`); });
        if (gpu.length > 0 && !gpu[0].Error && !gpu[0].Info) gpu.forEach((g, i) => { gpuSummary += renderKeyValue(`GPU ${i}`, `${g.Name || ''}`); });
        const hardwareContent = `${renderKeyValue('OS', os.Caption)}${renderKeyValue('Mainboard', `${mainboard.Manufacturer||''} ${mainboard.Product||''}`)}${renderKeyValue('Processor', cpu.Brand)}${ramSummary}${diskSummary}${gpuSummary}`;

        document.getElementById('basic-info').innerHTML = `<div class="content-grid grid-cols-2">${buildCard('basic-info','Realtime Usage','fa-tachometer-alt',metricsContent)}${buildCard('basic-info','Summary','fa-server',hardwareContent)}</div>`;
        
        // Gọi update lần đầu để điền dữ liệu
        updateRealtimeMetrics();
    }

    function renderPerformance() {
        const perfTab = document.getElementById('performance');
        perfTab.innerHTML = '<div id="performance-grid" class="content-grid grid-cols-2"></div>'; 
        const perfGrid = document.getElementById('performance-grid');

        fetch(`/api/client_metrics_history/${CLIENT_GUID}`)
            .then(res => {
                if (!res.ok) throw new Error(`API call failed with status ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (!data || !data.labels || data.labels.length === 0) {
                    perfGrid.innerHTML = buildCard('performance', 'Performance History', 'fa-solid fa-microchip', '<p>No performance history data available for this client.</p>');
                    perfGrid.classList.remove('grid-cols-2');
                    return;
                }

                const convertBytesToMB = arr => (arr || []).map(v => (v || 0) / (1024 * 1024));
                const convertBitsToMb = arr => (arr || []).map(v => (v || 0) / (1000 * 1000));

                const chartsToRender = [
                    {
                        id: 'cpuPerfChart',
                        title: 'CPU Usagea (%)',
                        datasets: [{ label: 'CPU', data: data.cpu, color: 'rgba(253, 126, 20, 1)' }],
                        options: { isPercentage: true },
                        icon: {icon: 'fa-solid fa-microchip'}
                    },
                    {
                        id: 'ramPerfChart',
                        title: 'RAM Usage (%)',
                        datasets: [{ label: 'RAM', data: data.ram, color: 'rgba(13, 110, 253, 1)' }],
                        options: { isPercentage: true },
                        icon: {icon: 'fa-solid fa-memory'}
                    }
                    // ,
                    // {
                    //     id: 'diskPerfChart',
                    //     title: 'Disk Usage (%)',
                    //     datasets: [{ label: 'Disk', data: data.disk, color: 'rgba(111, 66, 193, 1)' }],
                    //     options: { isPercentage: true },
                    //     icon: {icon: 'fa-solid fa-hdd'}
                    // }
                ];

                chartsToRender.forEach(chart => {
                    const chartHtml = buildCard('performance', chart.title, chart.icon.icon, `<div style="height: 300px;"><canvas id="${chart.id}"></canvas></div>`);
                    perfGrid.insertAdjacentHTML('beforeend', chartHtml);
                    createMultiLineChart(chart.id, chart.title, data.labels, chart.datasets, chart.options);
                });

                Object.entries(data.disk_io || {}).forEach(([diskName, diskData]) => {
                    const chartId = `diskIoChart-${diskName.replace(/[^a-zA-Z0-9]/g, '')}`;
                    const title = `${diskName} (MB/s)`;
                    const chartHtml = buildCard('performance', title, 'fa-solid fa-hdd', `<div style="height: 300px;"><canvas id="${chartId}"></canvas></div>`);
                    perfGrid.insertAdjacentHTML('beforeend', chartHtml);
                    createMultiLineChart(chartId, title, data.labels, [
                        { label: 'Read', data: convertBytesToMB(diskData.read_bytes_per_sec), color: 'rgba(75, 192, 192, 1)' },
                        { label: 'Write', data: convertBytesToMB(diskData.write_bytes_per_sec), color: 'rgba(255, 99, 132, 1)' }
                    ]);
                });

                Object.entries(data.network_io || {}).forEach(([nicName, nicData]) => {
                    const chartId = `netIoChart-${nicName.replace(/[^a-zA-Z0-9]/g, '')}`;
                    const title = `Network: ${nicName} (Mbps)`;
                    const chartHtml = buildCard('performance', title, 'fa-solid fa-ethernet', `<div style="height: 300px;"><canvas id="${chartId}"></canvas></div>`);
                    perfGrid.insertAdjacentHTML('beforeend', chartHtml);
                    createMultiLineChart(chartId, title, data.labels, [
                        { label: 'Upload', data: convertBitsToMb(nicData.upload_bits_per_sec), color: 'rgba(255, 159, 64, 1)' },
                        { label: 'Download', data: convertBitsToMb(nicData.download_bits_per_sec), color: 'rgba(54, 162, 235, 1)' }
                    ]);
                });
            })
            .catch(error => {
                console.error('Error fetching or rendering performance charts:', error);
                perfGrid.innerHTML = buildCard('performance', 'Error', 'fa-exclamation-triangle', `<p>Could not load performance data.</p><pre>${error.message}</pre>`);
                perfGrid.classList.remove('grid-cols-2');
            });
    }


// Thay thế hàm renderHardware cũ trong file detail.js của bạn

    function renderHardware() {
        const osData = auditData.os?.data || {};
        const processorData = auditData.cpu?.data || {};
        const gpuData = auditData.gpu?.data || [];
        const mainboardData = auditData.mainboard?.data || {};
        const memoryData = auditData.ram?.data || [];

        // --- BƯỚC 1: TẠO HTML HOÀN CHỈNH CHO TỪNG CARD ---

        const osCard = buildCard('hardware', 'Operating System', 'fa-brands fa-windows', 
            Object.entries(osData).map(([k, v]) => renderKeyValue(k, v)).join('')
        );

        const desiredProcessorOrder = [
            'Brand', 'Architecture', 'Bits', 'Logical Cores', 'Physical Cores',
            'Machine', 'Platform', 'System', 'Version'
        ];

        const processorCardContent = desiredProcessorOrder
            .map(key => {
                // Chỉ render nếu key tồn tại trong dữ liệu
                if (processorData.hasOwnProperty(key)) {
                    return renderKeyValue(key, processorData[key]);
                }
                return ''; // Bỏ qua nếu key không tồn tại
            })
            .join('');

        const processorCard = buildCard('hardware', 'Processor', 'fa-microchip', processorCardContent);
        
        let mainboardCardContent = '';
        if (mainboardData.BaseBoard || mainboardData.BIOS) {
            const baseboardHtml = mainboardData.BaseBoard ? `<div><h3><i class="fa-solid fa-microchip"></i> BaseBoard</h3>${Object.entries(mainboardData.BaseBoard).map(([k, v]) => renderKeyValue(k, v)).join('')}</div>` : '<div></div>';
            const biosHtml = mainboardData.BIOS ? `<div><h3><i class="fa-solid fa-bookmark"></i> BIOS</h3>${Object.entries(mainboardData.BIOS).map(([k, v]) => renderKeyValue(k, v)).join('')}</div>` : '<div></div>';
            mainboardCardContent = `<div class="column-layout grid-cols-2">${baseboardHtml}${biosHtml}</div>`;
        } else {
            mainboardCardContent = '<p>No Mainboard or BIOS data available.</p>';
        }
        const mainboardCard = buildCard('hardware', 'Mainboard & BIOS', 'fa-sitemap', mainboardCardContent);
        
        // --- BẮT ĐẦU KHỐI CODE THAY THẾ ---

        let memoryCardContent = '';
        if (memoryData.length > 0 && !memoryData[0].Error) {
            const ramBlocksHtml = memoryData.map(ram => {
                // --- LOGIC MỚI ĐỂ TẠO TITLE ĐỘNG VÀ SỬA LỖI SPEED ---

                // 1. Lấy các giá trị cần thiết
                const slotName = ram.Slot || 'RAM Stick';
                const manufacturer = ram.Manufacturer || '';
                const memoryType = ram.MemoryType || ram.SMBIOSMemoryType || '';
                const capacity = formatBytes(ram.Capacity || 0);

                // 2. Tìm và tính toán tốc độ chính xác
                const speedKeys = ['ConfiguredClockSpeed', 'Speed', 'BusSpeed'];
                let clockSpeed;
                for (const key of speedKeys) {
                    if (ram[key]) {
                        clockSpeed = Number(ram[key]);
                        break; // Dừng lại khi tìm thấy key đầu tiên
                    }
                }
                const effectiveSpeedMhz = clockSpeed ? (clockSpeed * (String(memoryType).toUpperCase().includes('DDR') ? 2 : 1)) : null;
                const speedForTitle = effectiveSpeedMhz ? ` bus ${effectiveSpeedMhz} MHz` : 'MHz';
                
                // 3. Tạo title động theo yêu cầu
                // Ví dụ: "DIMM4: Corsair DDR3 4.00 GB 1600 MHz"
                const title = `${slotName}: ${manufacturer} ${memoryType} ${capacity} ${speedForTitle}`.replace(/\s+/g, ' ').trim();

                // 4. Xử lý các cặp key-value, ngăn `Speed` được render sai
                // Thêm tất cả các key tốc độ vào danh sách bỏ qua
                const handledKeys = ['Slot', ...speedKeys];

                // Render tất cả các key khác ngoại trừ những key đã xử lý
                const detailsHtml = Object.entries(ram)
                    .filter(([key]) => !handledKeys.includes(key))
                    .map(([key, value]) => renderKeyValue(key, value))
                    .join('');

                // Thêm lại dòng 'Speed' đã được định dạng đúng ở cuối
                const finalDetailsHtml = detailsHtml + (effectiveSpeedMhz ? renderKeyValue('Speed', `${effectiveSpeedMhz}`) : 'MHz');

                // 5. Trả về HTML cho một thanh RAM
                return `<div><h3><i class="fa-solid fa-memory"></i> ${title}</h3>${finalDetailsHtml}</div>`;

            }).join('');

            const gridClass = memoryData.length > 1 ? 'grid-cols-2' : 'grid-cols-1';
            const gridSplit = memoryData.length === 1 ? 'grid-split-1' : 'grid-split-2';
            memoryCardContent = `<div class="column-layout ${gridClass} ${gridSplit}">${ramBlocksHtml}</div>`;
        } else {
            memoryCardContent = '<p>No memory data available.</p>';
        }
        const memoryCard = buildCard('hardware', 'Memory (RAM)', 'fa-memory', memoryCardContent);

        // --- KẾT THÚC KHỐI CODE THAY THẾ ---


        let gpuCard = '';
        if (Array.isArray(gpuData) && gpuData.length > 0 && !gpuData[0]?.Error) {
            const gpuBlocksHtml = gpuData.map(gpu => {
                const gpuDetails = { ...gpu };
                const title = gpuDetails.Name || 'GPU';
                delete gpuDetails.Name;
                return `<div><h3><i class="fa-solid fa-display"></i> ${title}</h3>${
                    Object.entries(gpuDetails).map(([k, v]) => renderKeyValue(k, v)).join('')
                }</div>`;
            }).join('');

            const gridClass = gpuData.length === 1 ? 'grid-cols-1' : 'grid-cols-2';
            const gridSplit = gpuData.length === 1 ? 'grid-split-1' : 'grid-split-2';
            const gpuCardContent = `<div class="column-layout ${gridClass} ${gridSplit}">${gpuBlocksHtml}</div>`;
            gpuCard = buildCard('hardware', 'Graphics (GPU)', 'fa-tv', gpuCardContent);
        } else {
            gpuCard = buildCard('hardware', 'Graphics (GPU)', 'fa-tv', '<p>No GPU data available.</p>');
        }

        

        // --- BƯỚC 2: LOGIC SẮP XẾP VÀ RENDER ĐỘNG ---

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

        // --- 1. Xử lý PHYSICAL DISKS với layout đã thống nhất ---
        const physicalDisks = diskData.PhysicalDisks || [];
        if (physicalDisks.length > 0 && !physicalDisks[0].Error) {
            const physicalDisksRows = physicalDisks.map((disk, i) => {
                const physicalInfo = { ...disk };
                delete physicalInfo.Partitions;
                delete physicalInfo.DeviceID;
                delete physicalInfo.Model;
                const physicalCardContent = `
                    <div class="pie-chart-container">
                        <canvas id="diskPieChart-${i}"></canvas>
                    </div>
                    ${Object.entries(physicalInfo).map(([k, v]) => renderKeyValue(k, v)).join('')}
                `;
                const physicalCard = buildCard('disk', disk.Model || `Physical Disk ${i}`, 'fa-hard-drive', physicalCardContent);

                const logicalDisks = (disk.Partitions || []).flatMap(p => p.LogicalDisks || []);
                let logicalCardContent = '';
                if (logicalDisks.length > 0) {
                    logicalCardContent = logicalDisks.map(ld => {
                        const ldInfo = {...ld};
                        const ldTitle = ldInfo.DeviceID || 'Logical Partition';
                        delete ldInfo.DeviceID;
                        return `
                            <h3><i class="fa-solid fa-folder-open"></i> ${ldTitle} (${ldInfo.VolumeName || 'No Name'})</h3>
                            ${Object.entries(ldInfo).map(([k,v]) => renderKeyValue(k,v)).join('')}
                        `;
                    }).join('<hr class="item-separator">');
                } else {
                    logicalCardContent = '<p>No logical partitions found on this drive.</p>';
                }
                const logicalCard = `
                    <div class="info-card scrollable-card">
                        <div class="card-content">
                            ${logicalCardContent}
                        </div>
                    </div>
                `;

                return `
                    <div class="_info-card"> 
                        <div class="card-content">
                            <div class="content-grid grid-cols-2">
                                ${physicalCard}
                                ${logicalCard}
                            </div>
                        </div>
                    </div>`;
            }).join('');
            finalHtml += `<div class="content-grid grid-cols-1">${physicalDisksRows}</div>`;
        }

        // --- 2. Xử lý NETWORK DRIVES (giữ nguyên) ---
        const networkDrives = diskData.NetworkDrives || [];
        if (networkDrives.length > 0) {
            const networkDrivesContent = networkDrives.map((drive, i) => {
                const driveDetailsHtml = renderKeyValue('Provider Name', drive.ProviderName);
                const title = drive.DeviceID || `Network Drive ${i}`;
                return buildCard('disk', title, 'fa-server', driveDetailsHtml);
            }).join('');
            
            finalHtml += `
                <div class="info-card">
                     <h2><i class="fa-solid fa-network-wired"></i> Network Drives</h2>
                     <div class="card-content">
                        <div class="content-grid grid-cols-2">
                            ${networkDrivesContent}
                        </div>
                    </div>
                </div>`;
        }

        // 3. Render ra DOM
        if (finalHtml.trim() === '') {
            diskTab.innerHTML = buildCard('disk', 'Storage Devices', 'fa-hdd', '<p>No disk data available.</p>');
        } else {
            diskTab.innerHTML = finalHtml;
        }

        // --- 4. TẠO BIỂU ĐỒ - LOGIC ĐÃ SỬA LỖI ---
        physicalDisks.forEach((disk, i) => {
            // Lấy danh sách phẳng tất cả các logical disks của ổ đĩa vật lý này
            const logicalDisks = (disk.Partitions || []).flatMap(p => p.LogicalDisks || []);
            
            // Nếu không có phân vùng nào thì không vẽ
            if (logicalDisks.length === 0) return;

            const labels = [];
            const dataPoints = [];
            let totalAllocatedSpace = 0;

            // Lặp qua TỪNG phân vùng logic (C:, D:, E:...)
            logicalDisks.forEach(ld => {
                const size = ld.Size || 0;
                const free = ld.FreeSpace || 0;
                const used = size - free;

                // Thêm 2 phần vào biểu đồ cho mỗi phân vùng
                labels.push(`${ld.DeviceID} Used (${formatBytes(used)})`);
                dataPoints.push(used);
                
                labels.push(`${ld.DeviceID} Free (${formatBytes(free)})`);
                dataPoints.push(free);
                
                // Tính tổng dung lượng đã được cấp phát
                totalAllocatedSpace += size;
            });
            
            // Tính toán và thêm phần dung lượng chưa cấp phát (unallocated)
            const totalDiskSize = disk.Size || 0;
            const unallocatedSpace = totalDiskSize - totalAllocatedSpace;
            
            // Chỉ thêm vào biểu đồ nếu lớn hơn 1MB để tránh các sai số nhỏ
            if (unallocatedSpace > 1024 * 1024) { 
                labels.push(`Unallocated (${formatBytes(unallocatedSpace)})`); 
                dataPoints.push(unallocatedSpace); 
            }

            // Gọi hàm tạo biểu đồ với dữ liệu đã tổng hợp
            createPieChart(`diskPieChart-${i}`, labels, dataPoints);
        });
    }
    
    // Thay thế hàm renderNetwork cũ trong file detail.js của bạn

    function renderNetwork() {
        const networkAdapters = auditData.network?.data || [];
        const networkTab = document.getElementById('network');

        if (networkAdapters.length === 0 || (networkAdapters.length > 0 && networkAdapters[0].Error)) {
            networkTab.innerHTML = buildCard('network', 'Network Adapters', 'fa-ethernet', '<p>No network data available.</p>');
            return;
        }

        const content = networkAdapters.map(adapter => {
            const adapterDetails = {...adapter};

            // 1. Tạo tiêu đề động
            const name = adapterDetails.NetConnectionID || adapterDetails.Description || 'Network Adapter';
            let titleHtml = `<div class="network-card-title"><span>${name}</span>`;

            // 2. Thêm badge nếu Status là "Connected"
            if (adapterDetails.Status && adapterDetails.Status.toLowerCase() === 'connected') {
                titleHtml += `<span class="status-badge connected">Connected</span>`;
            }
            titleHtml += `</div>`;
            
            // 3. Xóa các trường đã dùng trong tiêu đề để không bị lặp lại
            delete adapterDetails.NetConnectionID;
            delete adapterDetails.Description;
            // Có thể giữ lại Status để xem chi tiết, hoặc xóa đi nếu chỉ cần badge
            // delete adapterDetails.Status; 

            const detailsHtml = Object.entries(adapterDetails).map(([k,v]) => renderKeyValue(k,v)).join('');
            
            // 4. Gọi buildCard với title là HTML đã được định dạng
            return buildCard('network', titleHtml, 'fa-ethernet', detailsHtml);
        }).join('');

        networkTab.innerHTML = `<div class="content-grid grid-cols-2">${content}</div>`;
    }

    function renderPeripherals() {
        const printers = auditData.printers?.data || [];
        if (printers.length === 0 || (printers.length > 0 && printers[0].Error)) {
             document.getElementById('peripherals').innerHTML = buildCard('peripherals', 'Printers & Peripherals', 'fa-print', '<p>No printer data available.</p>');
             return;
        }
        const content = printers.map(p => {
            const printerDetails = {...p};
            let titleHtml = `<i class="fa-solid fa-print"></i> <span class="printer-name">${printerDetails['Printer Name'] || 'Unknown Printer'}</span>`;
            if (printerDetails.Default) {
                titleHtml += `<span class="printer-badge status-badge default">Default</span>`;
            }
            if (printerDetails.hasOwnProperty('Attributes Array')) {
                printerDetails.Attributes = printerDetails['Attributes Array'].join(', ');
            }
            delete printerDetails['Attributes Array'];
            delete printerDetails['Printer Name'];
            delete printerDetails.Default;
            const detailsHtml = Object.entries(printerDetails).map(([k,v]) => renderKeyValue(k,v)).join('');
            return buildCard('peripherals', titleHtml, null, detailsHtml);
        }).join('');
        document.getElementById('peripherals').innerHTML = `<div class="content-grid grid-cols-2">${content}</div>`;
    }

    function renderSecurity() {
        const credentials = auditData.credentials?.data || {};
        const content = Object.entries(credentials).map(([group, items]) => createGrid(group, items)).join('<hr class="item-separator">');
        document.getElementById('security').innerHTML = buildCard('security', 'Stored Credentials', 'fa-key', content);
    }

    function renderUsers() {
        const users = auditData.users?.data || {};
        let content = '';
        if (users && users.CurrentUser) content += renderKeyValue('Current User', users.CurrentUser, true);
        if (users && Array.isArray(users.LocalUsers)) {
            const processedUsers = users.LocalUsers.map(user => ({ Name: user.Name, FullName: user.FullName, AccountDomain: user.SID?.AccountDomainSid, SID_Value: user.SID?.Value, Enabled: user.Enabled }));
            content += createGrid('Local Users', processedUsers);
        }
        document.getElementById('users').innerHTML = buildCard('users', 'User Accounts', 'fa-users', content);
    }

    function renderSoftware() {
        const software = auditData.software?.data || {};
        if (Object.keys(software).length === 0 || software.Error) { document.getElementById('software').innerHTML = buildCard('software', 'Software', 'fa-cubes', '<p>No data.</p>'); return; }
        const content = Object.entries(software).map(([group, items]) => buildCard('software', group, 'fa-cubes', createGrid(null, items), 'scrollable-card')).join('');
        document.getElementById('software').innerHTML = `<div class="content-grid grid-cols-1">${content}</div>`;
    }

    function renderRuntime() {
        const processes = auditData.processes?.data || {};
        if (Object.keys(processes).length === 0 || processes.Error) { document.getElementById('runtime').innerHTML = buildCard('runtime', 'Processes', 'fa-cogs', '<p>No data.</p>'); return; }
        const content = Object.entries(processes).map(([group, items]) => buildCard('runtime', `User: ${group}`, 'fa-cogs', createGrid(null, items), 'runtime-card')).join('');
        document.getElementById('runtime').innerHTML = `<div class="content-grid grid-cols-1">${content}</div>`;
    }

    function renderServices() {
        const services = auditData.services?.data || {};
        if (Object.keys(services).length === 0 || services.Error) { document.getElementById('services').innerHTML = buildCard('services', 'Services', 'fa-concierge-bell', '<p>No data.</p>'); return; }
        const content = Object.entries(services).map(([group, items]) => buildCard('services', `State: ${group}`, 'fa-concierge-bell', createGrid(null, items), 'runtime-card')).join('');
        document.getElementById('services').innerHTML = `<div class="content-grid grid-cols-1">${content}</div>`;
    }

    function renderLogs() {
        const logs = auditData.event_log?.data || [];
        document.getElementById('logs').innerHTML = buildCard('logs', 'Event Logs', 'fa-clipboard-list', createGrid('System Log (Last 25)', logs), 'scrollable-card');
    }

    function renderHistory() {
        const history = auditData.web_history?.data || {};
        if (Object.keys(history).length === 0) { document.getElementById('history').innerHTML = buildCard('history', 'Web History', 'fa-globe', '<p>No data.</p>'); return; }
        const content = Object.entries(history).map(([browser, profiles]) => {
            if (profiles.Info || Object.keys(profiles).length === 0) return buildCard('history', browser, 'fa-globe', `<p>${profiles.Info || 'No profiles.'}</p>`);
            const profilesHtml = Object.entries(profiles).map(([profile, items]) => `<h3 class="toggle-header">${profile}</h3><div class="toggle-content">${createGrid(null, items)}</div>`).join('');
            return buildCard('history', browser, 'fa-globe', profilesHtml);
        }).join('');
        document.getElementById('history').innerHTML = `<div class="content-grid grid-cols-1">${content}</div>`;
    }

    // --- Main Fetch and Render Call ---
    function fetchDataAndRender() {
        fetch(`/api/client_audit_data/${CLIENT_GUID}`).then(res => res.json()).then(data => {
            auditData = data;
            renderBasicInfo(); renderPerformance(); renderHardware(); renderDisk(); renderNetwork(); renderPeripherals();
            renderSecurity(); renderUsers(); renderSoftware(); renderRuntime(); renderServices(); renderLogs(); renderHistory();
        }).catch(err => {
            console.error("Failed to fetch audit data:", err);
            document.querySelector('.tabs-container').innerHTML = `<p style="color:red;text-align:center;">Error loading client details. The client may be offline or data is not available.</p>`;
        });
    }

    // --- Initialization ---
    fetchDataAndRender();
    updateServerStatus();
    setInterval(updateServerStatus, SERVER_STATUS_INTERVAL);
    setInterval(updateRealtimeMetrics, REALTIME_METRICS_INTERVAL);
    setInterval(updatePerformanceCharts, REALTIME_METRICS_INTERVAL);
});