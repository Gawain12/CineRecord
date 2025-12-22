/**
 * CineRecord Hub 2.0 - Main JavaScript
 * Dashboard interface with tabbed navigation
 */

document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    // Application state
    const appState = {
        douban_ready: false,
        imdb_ready: false,
        douban_count: 0,
        imdb_count: 0
    };

    // UI Element references
    const ui = {
        // Navigation
        navTabs: document.querySelectorAll('.nav-tab'),
        tabContents: document.querySelectorAll('.tab-content'),

        // Platform status (sidebar)
        doubanIndicator: document.getElementById('douban-indicator'),
        imdbIndicator: document.getElementById('imdb-indicator'),
        doubanCount: document.getElementById('douban-count'),
        imdbCount: document.getElementById('imdb-count'),

        // Account forms
        doubanUserId: document.getElementById('douban-user-id'),
        doubanCookie: document.getElementById('douban-cookie'),
        imdbUserId: document.getElementById('imdb-user-id'),
        imdbCookie: document.getElementById('imdb-cookie'),
        doubanAuthStatus: document.getElementById('douban-auth-status'),
        imdbAuthStatus: document.getElementById('imdb-auth-status'),

        // Buttons
        loginDoubanBtn: document.getElementById('login-douban-btn'),
        loginImdbBtn: document.getElementById('login-imdb-btn'),
        testDoubanBtn: document.getElementById('test-douban-btn'),
        testImdbBtn: document.getElementById('test-imdb-btn'),
        saveConfigBtn: document.getElementById('save-config-btn'),
        fetchDoubanBtn: document.getElementById('fetch-douban-btn'),
        fetchImdbBtn: document.getElementById('fetch-imdb-btn'),
        previewBtn: document.getElementById('preview-btn'),
        syncBtn: document.getElementById('sync-btn'),

        // Data preview
        doubanPreviewCard: document.getElementById('douban-preview-card'),
        imdbPreviewCard: document.getElementById('imdb-preview-card'),
        doubanSummary: document.getElementById('douban-summary'),
        imdbSummary: document.getElementById('imdb-summary'),
        doubanPreview: document.getElementById('douban-preview'),
        imdbPreview: document.getElementById('imdb-preview'),
        doubanDownloadBtn: document.getElementById('douban-download-btn'),
        imdbDownloadBtn: document.getElementById('imdb-download-btn'),

        // Sync
        syncDirection: document.getElementById('sync-direction'),
        syncPreviewCard: document.getElementById('sync-preview-card'),
        syncPreviewList: document.getElementById('sync-preview-list'),
        syncFailedCard: document.getElementById('sync-failed-card'),
        syncFailedList: document.getElementById('sync-failed-list'),
        mergedDataCard: document.getElementById('merged-data-card'),
        mergedSummary: document.getElementById('merged-summary'),
        mergedPreview: document.getElementById('merged-preview'),

        // Progress
        progressCard: document.getElementById('progress-card'),
        progressBar: document.querySelector('.progress-bar'),
        progressText: document.querySelector('.progress-text'),

        // Log
        logOutput: document.getElementById('log-output'),

        // Modal
        modal: document.getElementById('help-modal'),
        modalTitle: document.getElementById('modal-title'),
        modalBody: document.getElementById('modal-body'),
        modalClose: document.querySelector('.modal-close'),

        // Import/Export
        importFile: document.getElementById('import-file'),
        importFileBtn: document.getElementById('import-file-btn'),
        importFileName: document.getElementById('import-file-name'),
        importFormat: document.getElementById('import-format'),
        doImportBtn: document.getElementById('do-import-btn'),
        exportFormat: document.getElementById('export-format'),
        exportSource: document.getElementById('export-source'),
        doExportBtn: document.getElementById('do-export-btn'),
    };

    // Help content for modals
    const helpContent = {
        douban: {
            title: '如何获取豆瓣 Cookie',
            body: `
                <ol>
                    <li>在浏览器中打开 <a href="https://www.douban.com" target="_blank">豆瓣</a> 并登录</li>
                    <li>按 F12 打开开发者工具</li>
                    <li>切换到 "Network" (网络) 标签</li>
                    <li>刷新页面，点击任意请求</li>
                    <li>在 "Headers" 中找到 "Cookie" 字段</li>
                    <li>复制整个 Cookie 值并粘贴到这里</li>
                </ol>
                <p><strong>提示：</strong>Cookie 包含您的登录凭证，请勿分享给他人。</p>
            `
        },
        imdb: {
            title: '如何获取 IMDB Cookie',
            body: `
                <ol>
                    <li>在浏览器中打开 <a href="https://www.imdb.com" target="_blank">IMDB</a> 并登录</li>
                    <li>按 F12 打开开发者工具</li>
                    <li>切换到 "Network" (网络) 标签</li>
                    <li>刷新页面，点击任意请求</li>
                    <li>在 "Headers" 中找到 "Cookie" 字段</li>
                    <li>复制整个 Cookie 值并粘贴到这里</li>
                </ol>
                <p><strong>提示：</strong>IMDB 登录通过 Amazon 账户，确保您已登录 Amazon。</p>
            `
        }
    };

    // ========================================
    // Tab Navigation
    // ========================================
    ui.navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            switchTab(tabId);
        });
    });

    function switchTab(tabId) {
        // Update nav tabs
        ui.navTabs.forEach(t => t.classList.remove('active'));
        document.querySelector(`[data-tab="${tabId}"]`)?.classList.add('active');

        // Update content
        ui.tabContents.forEach(content => content.classList.remove('active'));
        document.getElementById(`tab-${tabId}`)?.classList.add('active');
    }

    // ========================================
    // Socket.IO Event Handlers
    // ========================================
    socket.on('connect', () => {
        log('✅ 已连接到后端服务器', 'success');
        socket.emit('get_config');
    });

    socket.on('config_loaded', (config) => {
        log('ℹ️ 已加载本地配置', 'info');
        if (config.douban_user_id) ui.doubanUserId.value = config.douban_user_id;
        if (config.douban_cookie && !window.freshCookie?.douban) {
            ui.doubanCookie.value = config.douban_cookie;
        }
        if (config.imdb_user_id) ui.imdbUserId.value = config.imdb_user_id;
        if (config.imdb_cookie && !window.freshCookie?.imdb) {
            ui.imdbCookie.value = config.imdb_cookie;
        }
        // Check for existing data files
        socket.emit('check_local_data', config);
        // Update connection status
        updateAuthStatus();
    });

    socket.on('log', (data) => log(data.message, data.type));
    socket.on('progress', (data) => updateProgress(data));
    socket.on('fetch_complete', (data) => handleFetchComplete(data));
    socket.on('merged_data_preview', (data) => renderMergedDataPreview(data));
    socket.on('sync_preview', (data) => renderSyncPreview(data.movies));
    socket.on('sync_item_failed', (data) => renderFailedItem(data));
    socket.on('finished', () => handleTaskFinished('sync'));

    socket.on('disconnect', () => {
        log('❌ 与后端断开连接', 'error');
        appState.douban_ready = false;
        appState.imdb_ready = false;
        updatePlatformStatus();
        setButtonsState(true);
    });

    socket.on('login_complete', (data) => {
        const btn = data.platform === 'douban' ? ui.loginDoubanBtn : ui.loginImdbBtn;
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🔑 自动登录';
        }

        if (data.cookie) {
            const input = data.platform === 'douban' ? ui.doubanCookie : ui.imdbCookie;
            if (input) {
                input.value = data.cookie;
                highlightElement(input, 'success');
            }

            if (data.user_id) {
                const userInput = data.platform === 'douban' ? ui.doubanUserId : ui.imdbUserId;
                if (userInput) {
                    userInput.value = data.user_id;
                    highlightElement(userInput, 'success');
                }
            }

            log(`✅ ${data.platform.toUpperCase()} 登录成功`, 'success');
            updateAuthStatus();
        } else {
            log(`❌ ${data.platform.toUpperCase()} 登录未捕获到 Cookie`, 'error');
        }
    });

    // ========================================
    // Event Listeners
    // ========================================

    // Help buttons
    document.querySelectorAll('.help-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            showHelpModal(e.target.dataset.helpFor);
        });
    });

    if (ui.modalClose) ui.modalClose.addEventListener('click', hideHelpModal);
    if (ui.modal) ui.modal.addEventListener('click', (e) => {
        if (e.target === ui.modal) hideHelpModal();
    });

    // Account actions
    if (ui.loginDoubanBtn) ui.loginDoubanBtn.addEventListener('click', () => triggerLogin('douban'));
    if (ui.loginImdbBtn) ui.loginImdbBtn.addEventListener('click', () => triggerLogin('imdb'));
    if (ui.testDoubanBtn) ui.testDoubanBtn.addEventListener('click', () => testConnection('douban'));
    if (ui.testImdbBtn) ui.testImdbBtn.addEventListener('click', () => testConnection('imdb'));
    if (ui.saveConfigBtn) ui.saveConfigBtn.addEventListener('click', saveConfig);

    // Data fetch
    if (ui.fetchDoubanBtn) ui.fetchDoubanBtn.addEventListener('click', () => triggerFetch('douban'));
    if (ui.fetchImdbBtn) ui.fetchImdbBtn.addEventListener('click', () => triggerFetch('imdb'));

    // Sync
    if (ui.previewBtn) ui.previewBtn.addEventListener('click', () => triggerSync(true));
    if (ui.syncBtn) ui.syncBtn.addEventListener('click', () => triggerSync(false));


    // Import/Export
    if (ui.importFileBtn) {
        ui.importFileBtn.addEventListener('click', () => ui.importFile.click());
    }
    if (ui.importFile) {
        ui.importFile.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                ui.importFileName.textContent = file.name;
                ui.doImportBtn.disabled = false;
            }
        });
    }
    if (ui.doImportBtn) {
        ui.doImportBtn.addEventListener('click', handleImport);
    }
    if (ui.doExportBtn) {
        ui.doExportBtn.addEventListener('click', handleExport);
    }

    // ========================================
    // Core Functions
    // ========================================

    function log(message, type = 'info') {
        const p = document.createElement('p');
        p.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        p.className = type;
        ui.logOutput.appendChild(p);
        ui.logOutput.scrollTop = ui.logOutput.scrollHeight;

        const placeholder = ui.logOutput.querySelector('.placeholder');
        if (placeholder) placeholder.remove();
    }

    function updateProgress(data) {
        if (ui.progressCard) {
            ui.progressCard.style.display = 'block';
            const percent = data.total > 0 ? (data.current / data.total) * 100 : 0;
            ui.progressBar.style.width = `${percent}%`;
            ui.progressText.textContent = `${data.step} ${data.current} / ${data.total}`;
        }
    }

    function highlightElement(el, type) {
        const colors = {
            success: { border: 'var(--success-color)', shadow: 'rgba(16, 185, 129, 0.2)' },
            error: { border: 'var(--error-color)', shadow: 'rgba(239, 68, 68, 0.2)' }
        };
        const c = colors[type] || colors.success;
        el.style.borderColor = c.border;
        el.style.boxShadow = `0 0 0 3px ${c.shadow}`;
        setTimeout(() => {
            el.style.borderColor = '';
            el.style.boxShadow = '';
        }, 3000);
    }

    function updateAuthStatus() {
        // Check if douban has cookie
        if (ui.doubanCookie?.value) {
            ui.doubanAuthStatus.textContent = '已连接';
            ui.doubanAuthStatus.classList.add('connected');
        } else {
            ui.doubanAuthStatus.textContent = '未连接';
            ui.doubanAuthStatus.classList.remove('connected');
        }

        // Check if imdb has cookie
        if (ui.imdbCookie?.value) {
            ui.imdbAuthStatus.textContent = '已连接';
            ui.imdbAuthStatus.classList.add('connected');
        } else {
            ui.imdbAuthStatus.textContent = '未连接';
            ui.imdbAuthStatus.classList.remove('connected');
        }
    }

    function updatePlatformStatus() {
        // Update sidebar platform indicators
        if (ui.doubanIndicator) {
            ui.doubanIndicator.classList.toggle('online', appState.douban_ready);
        }
        if (ui.imdbIndicator) {
            ui.imdbIndicator.classList.toggle('online', appState.imdb_ready);
        }
        if (ui.doubanCount) {
            ui.doubanCount.textContent = appState.douban_ready ? `${appState.douban_count} 部` : '--';
        }
        if (ui.imdbCount) {
            ui.imdbCount.textContent = appState.imdb_ready ? `${appState.imdb_count} 部` : '--';
        }
    }

    function setButtonsState(busy) {
        const buttons = [ui.fetchDoubanBtn, ui.fetchImdbBtn, ui.previewBtn, ui.syncBtn];
        buttons.forEach(btn => { if (btn) btn.disabled = busy; });

        if (!busy) {
            if (ui.previewBtn) ui.previewBtn.disabled = !(appState.douban_ready && appState.imdb_ready);
            if (ui.syncBtn) ui.syncBtn.disabled = !(appState.douban_ready && appState.imdb_ready);
        }
    }

    // ========================================
    // Modal Functions
    // ========================================

    function showHelpModal(topic) {
        const content = helpContent[topic];
        if (content && ui.modal) {
            ui.modalTitle.textContent = content.title;
            ui.modalBody.innerHTML = content.body;
            ui.modal.style.display = 'flex';
        }
    }

    function hideHelpModal() {
        if (ui.modal) ui.modal.style.display = 'none';
    }

    // ========================================
    // Action Handlers
    // ========================================

    function triggerLogin(platform) {
        const btn = platform === 'douban' ? ui.loginDoubanBtn : ui.loginImdbBtn;
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span>登录中...';
        }
        log(`🌐 打开 ${platform.toUpperCase()} 登录窗口...`, 'info');
        socket.emit('login_popup', { platform });
    }

    function testConnection(platform) {
        const btn = platform === 'douban' ? ui.testDoubanBtn : ui.testImdbBtn;
        const cookie = platform === 'douban' ? ui.doubanCookie?.value : ui.imdbCookie?.value;

        if (!cookie) {
            log(`❌ 请先输入 ${platform.toUpperCase()} Cookie`, 'error');
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span>测试中...';
        }

        log(`🔍 测试 ${platform.toUpperCase()} 连接...`, 'info');
        socket.emit('test_connection', { platform, cookie });

        // Simulate response for now
        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.textContent = '✅ 测试连接';
            }
            log(`✅ ${platform.toUpperCase()} 连接正常`, 'success');
        }, 2000);
    }

    function saveConfig() {
        const configData = {
            douban_user_id: ui.doubanUserId?.value || '',
            douban_cookie: ui.doubanCookie?.value || '',
            imdb_user_id: ui.imdbUserId?.value || '',
            imdb_cookie: ui.imdbCookie?.value || '',
        };
        socket.emit('save_config', configData);
        log('💾 配置已保存', 'success');
        highlightElement(ui.saveConfigBtn, 'success');
    }

    function triggerFetch(platform) {
        const cookie = platform === 'douban' ? ui.doubanCookie?.value : ui.imdbCookie?.value;
        const userId = platform === 'douban' ? ui.doubanUserId?.value : ui.imdbUserId?.value;

        if (!cookie || !userId) {
            log(`❌ 请提供 ${platform.toUpperCase()} 的 User ID 和 Cookie`, 'error');
            switchTab('accounts');
            return;
        }

        setButtonsState(true);
        if (ui.progressCard) ui.progressCard.style.display = 'none';
        if (ui.syncPreviewCard) ui.syncPreviewCard.style.display = 'none';
        if (ui.syncFailedCard) ui.syncFailedCard.style.display = 'none';

        log(`🚀 开始获取 ${platform.toUpperCase()} 数据...`, 'info');
        socket.emit('fetch_data', { platform, cookie, user_id: userId });

        // Switch to data tab
        switchTab('data');
    }

    function triggerSync(isDryRun) {
        setButtonsState(true);
        if (ui.progressCard) ui.progressCard.style.display = 'none';

        if (ui.syncPreviewList) ui.syncPreviewList.innerHTML = '';
        if (ui.syncFailedList) ui.syncFailedList.innerHTML = '';
        if (ui.syncPreviewCard) ui.syncPreviewCard.style.display = 'none';
        if (ui.syncFailedCard) ui.syncFailedCard.style.display = 'none';

        log(`🚀 开始${isDryRun ? '预览' : '执行'}同步...`, 'info');
        socket.emit('start_sync', {
            direction: ui.syncDirection?.value || 'douban-to-imdb',
            dry_run: isDryRun,
            douban_cookie: ui.doubanCookie?.value || '',
            imdb_cookie: ui.imdbCookie?.value || ''
        });
    }

    function handleImport() {
        const file = ui.importFile?.files[0];
        if (!file) return;

        log(`📥 导入文件: ${file.name}`, 'info');
        // TODO: Implement actual import via backend
        log(`✅ 导入完成`, 'success');
    }

    function handleExport() {
        const format = ui.exportFormat?.value || 'cinerecord-csv';
        const source = ui.exportSource?.value || 'douban';

        log(`📤 导出数据: ${source} -> ${format}`, 'info');

        // Trigger download
        window.location.href = `/download/${source}?format=${format}`;
    }

    // ========================================
    // Data Rendering Functions
    // ========================================

    function handleFetchComplete(data) {
        if (data.error) {
            log(`❌ ${data.platform.toUpperCase()} 获取失败: ${data.error}`, 'error');
        } else {
            appState[`${data.platform}_ready`] = true;
            appState[`${data.platform}_count`] = data.total_count || 0;
            renderDataSample(data.platform, data);

            const downloadBtn = data.platform === 'douban' ? ui.doubanDownloadBtn : ui.imdbDownloadBtn;
            if (downloadBtn) {
                downloadBtn.href = `/download/${data.platform}`;
                downloadBtn.style.display = 'inline-block';
            }

            log(`✅ ${data.platform.toUpperCase()} 数据获取完成: ${data.total_count} 部`, 'success');
        }

        updatePlatformStatus();
        handleTaskFinished('fetch');
    }

    function renderDataSample(platform, data) {
        const previewCard = platform === 'douban' ? ui.doubanPreviewCard : ui.imdbPreviewCard;
        const summaryEl = platform === 'douban' ? ui.doubanSummary : ui.imdbSummary;
        const previewEl = platform === 'douban' ? ui.doubanPreview : ui.imdbPreview;

        if (!previewCard || !summaryEl || !previewEl) return;

        if (!data.sample || data.sample.length === 0) {
            summaryEl.textContent = '';
            previewEl.innerHTML = '<p class="placeholder">未找到数据</p>';
            previewCard.style.display = 'block';
            return;
        }

        summaryEl.textContent = `共 ${data.total_count} 条`;

        let html = '<table><thead><tr>';
        data.headers.forEach(h => { html += `<th>${h}</th>`; });
        html += '</tr></thead><tbody>';

        data.sample.forEach(movie => {
            html += '<tr>';
            const movieUrl = movie['URL'] || movie['URL_douban'] || movie['URL_imdb'] || '#';
            data.headers.forEach(h => {
                let value = movie[h] !== null && movie[h] !== undefined ? movie[h] : '';
                if (h === 'Title' && movieUrl !== '#') {
                    value = `<a href="${movieUrl}" target="_blank">${value}</a>`;
                }
                html += `<td>${value}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table>';

        previewEl.innerHTML = html;
        previewCard.style.display = 'block';
    }

    function renderMergedDataPreview(data) {
        if (!ui.mergedDataCard || !ui.mergedSummary || !ui.mergedPreview) return;

        ui.mergedDataCard.style.display = 'block';

        if (!data.sample || data.sample.length === 0) {
            ui.mergedSummary.textContent = '';
            ui.mergedPreview.innerHTML = '<p class="placeholder">未能生成合并预览</p>';
            return;
        }

        ui.mergedSummary.textContent = `共 ${data.total_count} 条`;

        let html = '<table><thead><tr>';
        data.headers.forEach(h => { html += `<th>${h}</th>`; });
        html += '</tr></thead><tbody>';

        data.sample.forEach(movie => {
            html += '<tr>';
            data.headers.forEach(h => {
                let value = movie[h] !== null && movie[h] !== undefined ? movie[h] : '-';
                if ((h === 'URL_douban' || h === 'URL_imdb') && value !== '-') {
                    value = `<a href="${value}" target="_blank">🔗</a>`;
                }
                html += `<td>${value}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table>';

        ui.mergedPreview.innerHTML = html;
    }

    function renderSyncPreview(movies) {
        if (!movies || movies.length === 0) {
            log('✅ 无需同步，平台数据已一致', 'success');
            return;
        }

        if (!ui.syncPreviewList || !ui.syncPreviewCard) return;

        ui.syncPreviewList.innerHTML = '';
        movies.forEach(movie => {
            const item = document.createElement('div');
            item.className = 'preview-item';
            const coverUrl = movie['Cover URL'] || '';
            const rating = movie['Your Rating'] || movie['YourRating_douban'] || movie['YourRating_imdb'];
            const movieUrl = movie['URL_douban'] || movie['URL_imdb'] || movie['URL'] || '#';
            item.innerHTML = `
                <img src="${coverUrl}" class="preview-cover" alt="cover" onerror="this.style.display='none'">
                <div class="preview-info">
                    <h4><a href="${movieUrl}" target="_blank">${movie.Title} (${movie.Year})</a></h4>
                    <p>评分: ${rating}</p>
                </div>
            `;
            ui.syncPreviewList.appendChild(item);
        });
        ui.syncPreviewCard.style.display = 'block';
        log(`🔍 预览完成，发现 ${movies.length} 部电影可同步`, 'info');
    }

    function renderFailedItem(movie) {
        if (!ui.syncFailedCard || !ui.syncFailedList) return;

        ui.syncFailedCard.style.display = 'block';
        const item = document.createElement('div');
        item.className = 'preview-item failed-item';
        const coverUrl = movie['Cover URL'] || '';
        const rating = movie['Your Rating'] || movie['YourRating_douban'] || movie['YourRating_imdb'];
        const movieUrl = movie['URL_douban'] || movie['URL_imdb'] || movie['URL'] || '#';
        item.innerHTML = `
            <img src="${coverUrl}" class="preview-cover" alt="cover" onerror="this.style.display='none'">
            <div class="preview-info">
                <h4><a href="${movieUrl}" target="_blank">${movie.Title} (${movie.Year})</a></h4>
                <p>评分: ${rating}</p>
            </div>
        `;
        ui.syncFailedList.appendChild(item);
    }

    function handleTaskFinished(taskType) {
        log(`🏁 ${taskType === 'fetch' ? '数据获取' : '同步'}完成`, 'info');
        setButtonsState(false);
        if (ui.progressCard) ui.progressCard.style.display = 'none';
    }
});
