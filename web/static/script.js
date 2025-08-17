document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const appState = { douban_ready: false, imdb_ready: false };

    const ui = {
        doubanStatus: document.getElementById('douban-status'),
        imdbStatus: document.getElementById('imdb-status'),
        doubanPreviewCard: document.getElementById('douban-preview-card'),
        imdbPreviewCard: document.getElementById('imdb-preview-card'),
        doubanSummary: document.getElementById('douban-summary'),
        imdbSummary: document.getElementById('imdb-summary'),
        doubanPreview: document.getElementById('douban-preview'),
        imdbPreview: document.getElementById('imdb-preview'),
        dataPreviewsContainer: document.getElementById('data-previews-container'),
        mergedPreviewCard: document.getElementById('merged-preview-card'),
        mergedSummary: document.getElementById('merged-summary'),
        mergedPreview: document.getElementById('merged-preview'),
        initialPreviews: document.getElementById('initial-previews'),
        mergedDataCard: document.getElementById('merged-data-card'),
        mergedSummary: document.getElementById('merged-summary'),
        mergedPreview: document.getElementById('merged-preview'),
        doubanDownloadBtn: document.getElementById('douban-download-btn'),
        imdbDownloadBtn: document.getElementById('imdb-download-btn'),
        syncPreviewCard: document.getElementById('sync-preview-card'),
        syncPreviewList: document.getElementById('sync-preview-list'),
        syncFailedCard: document.getElementById('sync-failed-card'),
        syncFailedList: document.getElementById('sync-failed-list'),
        previewBtn: document.getElementById('preview-btn'),
        syncBtn: document.getElementById('sync-btn'),
        fetchDoubanBtn: document.getElementById('fetch-douban-btn'),
        fetchImdbBtn: document.getElementById('fetch-imdb-btn'),
        progressCard: document.getElementById('progress-card'),
        progressBar: document.querySelector('.progress-bar'),
        progressText: document.querySelector('.progress-text'),
        logOutput: document.getElementById('log-output'),
        modal: document.getElementById('help-modal'),
        modalTitle: document.getElementById('modal-title'),
        modalBody: document.getElementById('modal-body'),
        modalClose: document.querySelector('.modal-close'),
        saveConfigBtn: document.getElementById('save-config-btn'),
    };

    const helpContent = { /* ... same as before ... */ };

    socket.on('connect', () => {
        log('✅ 已连接到后端。', 'success');
        socket.emit('get_config');
    });
    socket.on('config_loaded', (config) => {
        log('ℹ️ 已加载本地配置。', 'info');
        if(config.douban_user_id) document.getElementById('douban-user-id').value = config.douban_user_id;
        if(config.douban_cookie) document.getElementById('douban-cookie').value = config.douban_cookie;
        if(config.imdb_user_id) document.getElementById('imdb-user-id').value = config.imdb_user_id;
        if(config.imdb_cookie) document.getElementById('imdb-cookie').value = config.imdb_cookie;
        // After loading config, check for local data files
        socket.emit('check_local_data', config);
    });
    socket.on('log', (data) => log(data.message, data.type));
    socket.on('progress', (data) => updateProgress(data));
    socket.on('fetch_complete', (data) => handleFetchComplete(data));
    socket.on('merged_data_preview', (data) => renderMergedDataPreview(data));
    socket.on('sync_preview', (data) => renderSyncPreview(data.movies));
    socket.on('sync_item_failed', (data) => renderFailedItem(data));
    socket.on('finished', () => handleTaskFinished('sync'));
    socket.on('disconnect', () => {
        log('❌ 与后端断开连接。', 'error');
        // Reset state on disconnect to prevent stale UI
        appState.douban_ready = false;
        appState.imdb_ready = false;
        setButtonsState(true); // Disable all buttons
        ui.doubanStatus.textContent = "等待获取"; ui.doubanStatus.className = 'status';
        ui.imdbStatus.textContent = "等待获取"; ui.imdbStatus.className = 'status';
    });

    document.querySelectorAll('.help-btn').forEach(btn => btn.addEventListener('click', e => showHelpModal(e.target.dataset.helpFor)));
    ui.modalClose.addEventListener('click', hideHelpModal);
    ui.modal.addEventListener('click', e => { if (e.target === ui.modal) hideHelpModal(); });
    ui.fetchDoubanBtn.addEventListener('click', () => triggerFetch('douban'));
    ui.fetchImdbBtn.addEventListener('click', () => triggerFetch('imdb'));
    ui.previewBtn.addEventListener('click', () => triggerSync(true));
    ui.syncBtn.addEventListener('click', () => triggerSync(false));
    ui.saveConfigBtn.addEventListener('click', () => {
        const configData = {
            douban_user_id: document.getElementById('douban-user-id').value,
            douban_cookie: document.getElementById('douban-cookie').value,
            imdb_user_id: document.getElementById('imdb-user-id').value,
            imdb_cookie: document.getElementById('imdb-cookie').value,
        };
        socket.emit('save_config', configData);
    });

    function log(message, type = 'info') {
        const p = document.createElement('p');
        p.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        p.className = type;
        ui.logOutput.appendChild(p);
        ui.logOutput.scrollTop = ui.logOutput.scrollHeight;
        if (ui.logOutput.querySelector('.placeholder')) ui.logOutput.querySelector('.placeholder').remove();
    }

    function updateProgress(data) {
        ui.progressCard.style.display = 'block';
        const percent = data.total > 0 ? (data.current / data.total) * 100 : 0;
        ui.progressBar.style.width = `${percent}%`;
        ui.progressText.textContent = `${data.step} ${data.current} / ${data.total}`;
    }

    function showHelpModal(platform) { /* ... same as before ... */ }
    function hideHelpModal() { /* ... same as before ... */ }

    function setButtonsState(busy) {
        [ui.fetchDoubanBtn, ui.fetchImdbBtn, ui.previewBtn, ui.syncBtn].forEach(btn => btn.disabled = busy);
        if (!busy) {
            ui.previewBtn.disabled = !(appState.douban_ready && appState.imdb_ready);
            ui.syncBtn.disabled = !(appState.douban_ready && appState.imdb_ready);
        }
    }
    
    function renderDataSample(platform, data) {
        const previewCard = platform === 'douban' ? ui.doubanPreviewCard : ui.imdbPreviewCard;
        const summaryEl = platform === 'douban' ? ui.doubanSummary : ui.imdbSummary;
        const previewEl = platform === 'douban' ? ui.doubanPreview : ui.imdbPreview;
        
        if (!data.sample || data.sample.length === 0) {
            summaryEl.innerHTML = '';
            previewEl.innerHTML = '<p class="placeholder">未找到可供预览的数据。</p>';
            previewCard.style.display = 'block';
            return;
        }
        
        // Render summary
        summaryEl.innerHTML = `总计: <span>${data.total_count}</span> 条 | 表头: <span>${data.headers.slice(0, 4).join(', ')}...</span>`;

        // Render table preview
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
        // This function is now the single source of truth for a successful sync.
        // It handles both showing the card and rendering the data.
        ui.initialPreviews.style.display = 'none';
        ui.mergedDataCard.style.display = 'block';

        if (!data.sample || data.sample.length === 0) {
            ui.mergedSummary.innerHTML = '';
            ui.mergedPreview.innerHTML = '<p class="placeholder">未能生成合并预览。</p>';
            return;
        }

        // Render summary - show all headers for merged view
        ui.mergedSummary.innerHTML = `总计: <span>${data.total_count}</span> 条`;

        // Render table preview
        let html = '<table><thead><tr>';
        data.headers.forEach(h => { html += `<th>${h}</th>`; });
        html += '</tr></thead><tbody>';

        data.sample.forEach(movie => {
            html += '<tr>';
            const movieUrlDouban = movie['URL_douban'] || '#';
            const movieUrlImdb = movie['URL_imdb'] || '#';
            
            data.headers.forEach(h => {
                let value = movie[h] !== null && movie[h] !== undefined ? movie[h] : '-';
                // Make titles and specific URLs clickable
                if (h === 'Title' && movieUrlDouban !== '#') {
                    value = `<a href="${movieUrlDouban}" target="_blank">${value}</a>`;
                } else if (h === 'URL_douban' && value !== '-') {
                     value = `<a href="${value}" target="_blank">🔗 Link</a>`;
                } else if (h === 'URL_imdb' && value !== '-') {
                     value = `<a href="${value}" target="_blank">🔗 Link</a>`;
                }
                html += `<td>${value}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table>';
        
        ui.mergedPreview.innerHTML = html;
    }

    function renderFailedItem(movie) {
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
                <p>你的评分: ${rating}</p>
            </div>
        `;
        ui.syncFailedList.appendChild(item);
    }

    function renderSyncPreview(movies) {
        if (!movies || movies.length === 0) {
            log('✅ 无需同步，平台数据已一致。', 'success');
            return;
        }
        ui.syncPreviewList.innerHTML = '';
        movies.forEach(movie => {
            const item = document.createElement('div');
            item.className = 'preview-item';
            const coverUrl = movie['Cover URL'] || '';
            const rating = movie['Your Rating'] || movie['YourRating_douban'] || movie['YourRating_imdb'];
            // FINAL FIX: Use the correct, specific URL field from the merged data
            const movieUrl = movie['URL_douban'] || movie['URL_imdb'] || movie['URL'] || '#';
            item.innerHTML = `
                <img src="${coverUrl}" class="preview-cover" alt="cover" onerror="this.style.display='none'">
                <div class="preview-info">
                    <h4><a href="${movieUrl}" target="_blank">${movie.Title} (${movie.Year})</a></h4>
                    <p>你的评分: ${rating}</p>
                </div>
            `;
            ui.syncPreviewList.appendChild(item);
        });
        ui.syncPreviewCard.style.display = 'block';
        log(`🔍 预览完成，发现 ${movies.length} 部电影可同步。`, 'info');
    }

    function handleFetchComplete(data) {
        const statusEl = data.platform === 'douban' ? ui.doubanStatus : ui.imdbStatus;
        if (data.error) {
            statusEl.textContent = "获取失败"; statusEl.className = 'status error';
        } else {
            statusEl.textContent = "数据已就绪"; statusEl.className = 'status ready';
            appState[`${data.platform}_ready`] = true;
            renderDataSample(data.platform, data); // Pass the whole data object
            
            // Activate the download button
            const downloadBtn = data.platform === 'douban' ? ui.doubanDownloadBtn : ui.imdbDownloadBtn;
            downloadBtn.href = `/download/${data.platform}`;
            downloadBtn.style.display = 'inline-block';
        }
        handleTaskFinished('fetch');
    }

    function handleTaskFinished(taskType) {
        log(`🏁 ${taskType === 'fetch' ? '抓取' : '同步'}完成。`, 'info');
        setButtonsState(false);
        ui.progressCard.style.display = 'none'; // Always hide progress on finish
    }

    function triggerFetch(platform) {
        const cookie = document.getElementById(`${platform}-cookie`).value;
        const userId = document.getElementById(`${platform}-user-id`).value; // Now works for both
        if (!cookie || !userId) {
            log(`错误: 请提供${platform.toUpperCase()}的 User ID 和 Cookie。`, 'error');
            return;
        }
        setButtonsState(true);
        ui.progressCard.style.display = 'none';
        // Show the original data previews and hide the merged one.
        ui.initialPreviews.style.display = 'block';
        ui.mergedDataCard.style.display = 'none';
        
        ui.syncPreviewCard.style.display = 'none';
        ui.syncFailedCard.style.display = 'none';
        log(`🚀 开始获取 ${platform.toUpperCase()} 数据...`, 'info');
        socket.emit('fetch_data', { platform, cookie, user_id: userId });
    }

    function triggerSync(isDryRun) {
        setButtonsState(true);
        ui.progressCard.style.display = 'none';
        // Show the original data previews and hide the merged one.
        ui.initialPreviews.style.display = 'block';
        ui.mergedDataCard.style.display = 'none';
        
        // Explicitly clear the content of previous sync previews and failures
        ui.syncPreviewList.innerHTML = '';
        ui.syncFailedList.innerHTML = '';
        ui.syncPreviewCard.style.display = 'none';
        ui.syncFailedCard.style.display = 'none';

        log(`🚀 开始${isDryRun ? '预览' : '执行'}同步...`, 'info');
        socket.emit('start_sync', {
            direction: document.getElementById('sync-direction').value,
            dry_run: isDryRun,
            douban_cookie: document.getElementById('douban-cookie').value,
            imdb_cookie: document.getElementById('imdb-cookie').value
        });
    }
});
