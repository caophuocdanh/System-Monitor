// static/js/common.js

document.addEventListener('DOMContentLoaded', () => {

    // --- LOGIC CẬP NHẬT GIAO DIỆN "THÔNG MINH" ---
    function populateThemeSwitcher() {
        const themeSwitcher = document.getElementById('theme-switcher');
        if (!themeSwitcher) return;

        // Lấy tất cả các quy tắc CSS đã được tải
        const styleSheets = document.styleSheets;
        const themeDefinitions = {};

        // Lặp qua từng file stylesheet
        for (const sheet of styleSheets) {
            try {
                // Lặp qua từng quy tắc trong stylesheet
                for (const rule of sheet.cssRules) {
                    // Chỉ quan tâm đến quy tắc :root
                    if (rule.selectorText === ':root' && rule.style) {
                        // Lặp qua các biến trong :root
                        for (let i = 0; i < rule.style.length; i++) {
                            const propName = rule.style[i];
                            // Nếu biến có dạng --theme-*-name
                            if (propName.startsWith('--theme-') && propName.endsWith('-name')) {
                                const themeKey = propName.replace('--theme-', '').replace('-name', '');
                                const themeDisplayName = rule.style.getPropertyValue(propName).trim().replace(/"/g, '');
                                
                                // 'default' là trường hợp đặc biệt, gán giá trị rỗng cho class
                                const themeClassName = (themeKey === 'default') ? '' : `theme-${themeKey}`;
                                
                                themeDefinitions[themeDisplayName] = themeClassName;
                            }
                        }
                    }
                }
            } catch (e) {
                // Bỏ qua lỗi CORS nếu load CSS từ domain khác
                console.warn("Could not read CSS rules from stylesheet, likely due to CORS policy:", e);
            }
        }
        
        // Tạo các thẻ <option> từ các theme đã tìm thấy
        for (const [displayName, className] of Object.entries(themeDefinitions)) {
            const option = document.createElement('option');
            option.value = className;
            option.textContent = displayName;
            themeSwitcher.appendChild(option);
        }
    }

    // Gọi hàm để điền các lựa chọn
    populateThemeSwitcher();
    // --- KẾT THÚC LOGIC MỚI ---
    
    // --- LOGIC CHUYỂN ĐỔI THEME CHUNG ---
    const themeSwitcher = document.getElementById('theme-switcher');
    const body = document.body;

    if (themeSwitcher) {
        // Áp dụng theme đã lưu từ localStorage khi trang tải
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            body.className = savedTheme;
            themeSwitcher.value = savedTheme;
        }

        // Lắng nghe sự kiện thay đổi theme
        themeSwitcher.addEventListener('change', (e) => {
            const selectedTheme = e.target.value;
            body.className = selectedTheme;
            localStorage.setItem('theme', selectedTheme);
        });
    }

    // --- LOGIC XÓA RECORDS CHUNG ---
    const clearRecordsBtn = document.getElementById('btn-clear-records');
    const pruneOfflineBtn = document.getElementById('btn-prune-offline');

    if (clearRecordsBtn) {
        clearRecordsBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to delete ALL metric records? This action cannot be undone.')) {
                fetch('/api/clear_records', { method: 'POST' })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'success') {
                            alert(data.message);
                            
                            // --- LOGIC CẬP NHẬT GIAO DIỆN "THÔNG MINH" ---
                            // Kiểm tra xem hàm `updateDashboard` có tồn tại không
                            if (typeof updateDashboard === 'function') {
                                updateDashboard(); // Nếu có, gọi nó (đang ở trang dashboard)
                            } else {
                                location.reload(); // Nếu không, chỉ cần tải lại trang
                            }
                            // --- KẾT THÚC LOGIC CẬP NHẬT ---

                        } else {
                            alert('Error: ' + data.message);
                        }
                    })
                    .catch(err => {
                        console.error('Error clearing records:', err);
                        alert('An error occurred while clearing records.');
                    });
            }
        });
    }
    if (pruneOfflineBtn) {
        pruneOfflineBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to delete ALL OFFLINE clients and all of their associated data (audits, metrics, etc)? This action is irreversible.')) {
                fetch('/api/prune_offline_clients', { method: 'POST' })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'success') {
                            alert(data.message);
                            if (typeof updateDashboard === 'function') {
                                updateDashboard();
                            } else {
                                location.reload();
                            }
                        } else {
                            alert('Error: ' + data.message);
                        }
                    })
                    .catch(err => {
                        console.error('Error pruning offline clients:', err);
                        alert('An error occurred while pruning offline clients.');
                    });
            }
        });
    }

});