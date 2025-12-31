/**
 * CineRecord Hub 2.0 - Main JavaScript
 * Dashboard interface with tabbed navigation
 */

document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    window.socket = socket; // Expose for debugging

    socket.on('connect', () => {
        console.log('[Socket] Connected with ID:', socket.id);
    });

    // Application state
    const appState = {
        douban_ready: false,
        imdb_ready: false,
        douban_count: 0,
        imdb_count: 0
    };

    // Helper function to proxy avatar URLs through our server
    // This bypasses anti-hotlinking protection (e.g., Douban's 418 error)
    function proxyAvatarUrl(url) {
        if (!url) return '';
        // Check if URL is from external domain that needs proxying
        if (url.includes('doubanio.com') || url.includes('douban.com')) {
            return `/proxy/avatar?url=${encodeURIComponent(url)}`;
        }
        return url;  // Return as-is for other URLs
    }

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
        logOutput: document.getElementById('log-container'),

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

        // Save session state when tab changes
        saveSessionState();
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
        // Store in appState for later use
        appState.douban_cookie = config.douban_cookie || '';
        appState.imdb_cookie = config.imdb_cookie || '';
        appState.douban_user_id = config.douban_user_id || '';
        appState.imdb_user_id = config.imdb_user_id || '';

        if (config.douban_user_id && ui.doubanUserId) ui.doubanUserId.value = config.douban_user_id;
        if (config.imdb_user_id && ui.imdbUserId) ui.imdbUserId.value = config.imdb_user_id;

        // Also populate settings page cookie fields if they exist
        const doubanCookieConfig = document.getElementById('douban-cookie-config');
        const imdbCookieConfig = document.getElementById('imdb-cookie-config');
        const doubanUserIdConfig = document.getElementById('douban-user-id-config');
        const imdbUserIdConfig = document.getElementById('imdb-user-id-config');
        if (doubanCookieConfig && config.douban_cookie) doubanCookieConfig.value = config.douban_cookie;
        if (imdbCookieConfig && config.imdb_cookie) imdbCookieConfig.value = config.imdb_cookie;
        if (doubanUserIdConfig && config.douban_user_id) doubanUserIdConfig.value = config.douban_user_id;
        if (imdbUserIdConfig && config.imdb_user_id) imdbUserIdConfig.value = config.imdb_user_id;

        // Check for existing data files
        socket.emit('check_local_data', config);
        // Request session check from backend
        socket.emit('check_session', {});
        // Update connection status
        updateAuthStatus();
        // Update button states based on config
        updateButtonsBasedOnConnection();

        // Populate Trakt credentials if saved
        const traktClientIdInput = document.getElementById('trakt-client-id');
        const traktClientSecretInput = document.getElementById('trakt-client-secret');
        if (traktClientIdInput && config.trakt_client_id) {
            traktClientIdInput.value = config.trakt_client_id;
        }
        if (traktClientSecretInput && config.trakt_client_secret) {
            traktClientSecretInput.value = config.trakt_client_secret;
        }

        // If Trakt is already authorized (has access token), test the connection
        if (config.trakt_access_token) {
            socket.emit('trakt_test_connection', {});
        }

        // Restore session state from localStorage
        restoreSessionState();
    });

    socket.on('log', (data) => log(data.message, data.type));
    socket.on('progress', (data) => updateProgress(data));
    socket.on('fetch_complete', (data) => {
        handleFetchComplete(data);
        // Refresh unified library after any fetch
        socket.emit('get_unified_library', { page: 1, page_size: 20, platform: 'all' });
    });
    socket.on('page_data', (data) => handlePageData(data));  // Pagination handler
    socket.on('merged_data_preview', (data) => renderMergedDataPreview(data));
    socket.on('sync_preview', (data) => renderSyncPreview(data.movies));
    socket.on('sync_item_failed', (data) => renderFailedItem(data));
    socket.on('sync_unrated', (data) => renderUnratedMovies(data));
    socket.on('finished', () => handleTaskFinished('sync'));

    // Unified Library handler
    socket.on('unified_library', (data) => {
        console.log('[Library] socket.on unified_library received:', data.filter, 'movies:', data.movies?.length);
        renderUnifiedLibrary(data);
    });

    // Letterboxd upload complete handler
    socket.on('letterboxd_upload_complete', (data) => {
        // Update appState
        appState.letterboxd_ready = true;
        appState.letterboxd_count = data.total_count || 0;
        appState.letterboxd_rated = data.rated_count || 0;

        // Update sidebar summary card
        const letterboxdStatusDot = document.getElementById('letterboxd-status-dot');
        const letterboxdStats = document.getElementById('letterboxd-summary-stats');
        if (letterboxdStatusDot) {
            letterboxdStatusDot.className = 'status-dot connected';
        }
        if (letterboxdStats) {
            letterboxdStats.textContent = `${data.total_count} 部`;
        }

        // Update Letterboxd account card to connected state
        const letterboxdNotConnected = document.getElementById('letterboxd-not-connected');
        const letterboxdConnected = document.getElementById('letterboxd-connected');
        const letterboxdStatusBadge = document.getElementById('letterboxd-status-badge');
        const letterboxdWatchedCount = document.getElementById('letterboxd-watched-count');
        const letterboxdRatedCount = document.getElementById('letterboxd-rated-count');

        if (letterboxdNotConnected) letterboxdNotConnected.style.display = 'none';
        if (letterboxdConnected) letterboxdConnected.style.display = 'block';
        if (letterboxdStatusBadge) {
            letterboxdStatusBadge.textContent = '● 已导入';
            letterboxdStatusBadge.className = 'status-badge connected';
        }
        if (letterboxdWatchedCount) letterboxdWatchedCount.textContent = data.total_count;
        if (letterboxdRatedCount) letterboxdRatedCount.textContent = data.rated_count;

        // Render data preview in Data tab
        renderLetterboxdDataSample(data);

        // Save session state
        saveSessionState();
    });

    // Trakt OAuth Device Flow handlers
    socket.on('trakt_auth_started', (data) => {
        // Show device code area
        const codeArea = document.getElementById('trakt-device-code-area');
        const userCodeEl = document.getElementById('trakt-user-code');
        const verifyUrlEl = document.getElementById('trakt-verify-url');
        const statusText = document.getElementById('trakt-auth-status-text');

        if (codeArea) codeArea.style.display = 'block';
        if (userCodeEl) userCodeEl.textContent = data.user_code;
        if (verifyUrlEl) {
            verifyUrlEl.href = data.verification_url;
            verifyUrlEl.textContent = data.verification_url;
        }
        if (statusText) statusText.textContent = '等待授权中...';

        // Start polling for authorization
        appState.traktPollingInterval = setInterval(() => {
            socket.emit('trakt_poll_auth', {});
        }, (data.interval || 5) * 1000);

        // Set timeout to stop polling after expiration
        appState.traktPollingTimeout = setTimeout(() => {
            if (appState.traktPollingInterval) {
                clearInterval(appState.traktPollingInterval);
                appState.traktPollingInterval = null;
            }
            if (statusText) statusText.textContent = '授权已过期，请重试';
        }, data.expires_in * 1000);
    });

    socket.on('trakt_auth_result', (data) => {
        const statusText = document.getElementById('trakt-auth-status-text');

        if (data.status === 'success') {
            // Stop polling
            if (appState.traktPollingInterval) {
                clearInterval(appState.traktPollingInterval);
                appState.traktPollingInterval = null;
            }
            if (appState.traktPollingTimeout) {
                clearTimeout(appState.traktPollingTimeout);
                appState.traktPollingTimeout = null;
            }

            // Update UI to connected state
            appState.trakt_ready = true;
            updateTraktConnectedState(data.profile);
            saveSessionState();

        } else if (data.status === 'pending') {
            // Still waiting
            if (statusText) statusText.textContent = '等待授权中...';
        } else if (data.status === 'slow_down') {
            // Need to slow down polling
            if (statusText) statusText.textContent = '请稍候...';
        } else {
            // Error or denied
            if (appState.traktPollingInterval) {
                clearInterval(appState.traktPollingInterval);
                appState.traktPollingInterval = null;
            }
            if (statusText) statusText.textContent = data.message || '授权失败';
        }
    });

    socket.on('trakt_test_result', (data) => {
        if (data.success) {
            appState.trakt_ready = true;
            updateTraktConnectedState(data.profile);
        } else {
            // Test failed - reset UI to disconnected state
            // This handles cases where localStorage cached 'connected' state
            // but backend tokens are invalid/missing
            appState.trakt_ready = false;
            appState.trakt_profile = null;

            const notConnected = document.getElementById('trakt-not-connected');
            const connected = document.getElementById('trakt-connected');
            const statusBadge = document.getElementById('trakt-status-badge');
            const authBtn = document.getElementById('trakt-auth-btn');
            const testBtn = document.getElementById('test-trakt-btn');
            const updateBtn = document.getElementById('update-trakt-btn');
            const logoutBtn = document.getElementById('logout-trakt-btn');

            if (notConnected) notConnected.style.display = 'block';
            if (connected) connected.style.display = 'none';
            if (statusBadge) {
                statusBadge.textContent = '● 未连接';
                statusBadge.className = 'status-badge disconnected';
            }
            if (authBtn) authBtn.disabled = false;
            if (testBtn) testBtn.style.display = 'none';
            if (updateBtn) updateBtn.style.display = 'none';
            if (logoutBtn) logoutBtn.style.display = 'none';

            // Update sidebar
            const sidebarDot = document.getElementById('trakt-status-dot');
            if (sidebarDot) sidebarDot.className = 'status-dot disconnected';

            saveSessionState();
        }
    });

    // Handle Trakt profile from session restore
    socket.on('trakt_profile', (profile) => {
        if (profile && profile.user_id) {
            appState.trakt_ready = true;
            appState.trakt_profile = profile;
            // Set trakt_count for sync compatibility
            if (!appState.trakt_count) {
                appState.trakt_count = profile.movies_watched || 0;
            }
            updateTraktConnectedState(profile);
            saveSessionState();
            log('🔄 Trakt 连接已恢复', 'info');
        }
    });

    // Helper function to update Trakt connected state
    function updateTraktConnectedState(profile) {
        const notConnected = document.getElementById('trakt-not-connected');
        const connected = document.getElementById('trakt-connected');
        const statusBadge = document.getElementById('trakt-status-badge');
        const displayName = document.getElementById('trakt-display-name');
        const userIdDisplay = document.getElementById('trakt-user-id-display');
        const avatar = document.getElementById('trakt-avatar');
        const watchedCount = document.getElementById('trakt-watched-count');
        const ratedCount = document.getElementById('trakt-rated-count');
        const profileLink = document.getElementById('trakt-profile-link');
        const testBtn = document.getElementById('test-trakt-btn');
        const updateBtn = document.getElementById('update-trakt-btn');
        const logoutBtn = document.getElementById('logout-trakt-btn');

        // Update sidebar
        const sidebarDot = document.getElementById('trakt-status-dot');
        const sidebarStats = document.getElementById('trakt-summary-stats');
        const sidebarId = document.getElementById('trakt-sidebar-id');
        if (sidebarDot) sidebarDot.className = 'status-dot connected';
        if (sidebarStats) sidebarStats.textContent = `${profile.movies_watched || 0} 已看`;
        if (sidebarId && profile.user_id) sidebarId.textContent = `@${profile.user_id}`;

        // Toggle states
        if (notConnected) notConnected.style.display = 'none';
        if (connected) connected.style.display = 'block';
        if (statusBadge) {
            statusBadge.textContent = '● 已连接';
            statusBadge.className = 'status-badge connected';
        }

        // Update profile info
        if (displayName) displayName.textContent = profile.display_name || profile.username || '用户';
        if (userIdDisplay) userIdDisplay.textContent = profile.user_id || '--';
        if (avatar && profile.avatar) avatar.src = proxyAvatarUrl(profile.avatar);
        if (watchedCount) watchedCount.textContent = profile.movies_watched || '--';
        if (ratedCount) ratedCount.textContent = profile.movies_rated || '--';
        if (profileLink && profile.profile_link) profileLink.href = profile.profile_link;

        // Update watched/rated stat links
        const userId = profile.user_id;
        if (userId) {
            const watchedLink = document.getElementById('link-trakt-watched');
            const ratedLink = document.getElementById('link-trakt-rated');
            if (watchedLink) watchedLink.href = `https://trakt.tv/users/${userId}/history/movies`;
            if (ratedLink) ratedLink.href = `https://trakt.tv/users/${userId}/ratings/movies`;
        }

        // Show action buttons
        if (testBtn) testBtn.style.display = 'inline-block';
        if (updateBtn) updateBtn.style.display = 'inline-block';
        if (logoutBtn) logoutBtn.style.display = 'inline-flex';

        // Store profile data for session persistence
        appState.trakt_profile = profile;
    }

    // Handle session restoration from backend
    // Validation-first approach: show "validating" until platform_validated event arrives
    socket.on('session_restored', (data) => {
        // Handle platforms with pending validation
        if (data.platforms_pending && Object.keys(data.platforms_pending).length > 0) {
            Object.keys(data.platforms_pending).forEach(platform => {
                const pending = data.platforms_pending[platform];
                // Show validating state
                showValidatingState(platform, pending.user_id || pending.username);
            });
        }

        // Handle cached data - load data but don't mark as "connected" yet
        if (data.cached_data && Object.keys(data.cached_data).length > 0) {
            Object.keys(data.cached_data).forEach(platform => {
                const cached = data.cached_data[platform];
                if (cached.has_data) {
                    // Set data counts (data != connection state)
                    appState[`${platform}_count`] = cached.count;
                    appState[`${platform}_user_id`] = cached.user_id;

                    // Update sidebar count display (data available, not connection status)
                    let countEl = null;
                    if (platform === 'douban') countEl = ui.doubanCount;
                    else if (platform === 'imdb') countEl = ui.imdbCount;
                    else if (platform === 'trakt') countEl = document.getElementById('trakt-summary-stats');

                    if (countEl) {
                        countEl.textContent = `${cached.count} 部`;
                    }

                    log(`📚 已加载缓存 ${platform.toUpperCase()} 数据: ${cached.count} 部`, 'info');

                    // Request first page of data to render in data tab
                    socket.emit('get_page', { platform, page: 1, page_size: 10 });
                }
            });

            updatePlatformStatus();
        }

        // Store config items
        if (data.config) {
            appState.douban_cookie = data.config.douban_cookie || '';
            appState.imdb_cookie = data.config.imdb_cookie || '';
        }
    });

    // Handle validation results for each platform
    socket.on('platform_validated', (data) => {
        const platform = data.platform;

        if (data.valid) {
            // Validation successful - show connected state
            log(`✅ ${platform.toUpperCase()} 验证成功`, 'success');

            if (platform === 'douban' || platform === 'imdb') {
                appState[`${platform}_ready`] = true;
                appState[`${platform}_user_id`] = data.user_id;
                updateProfileCardState(platform, true, { user_id: data.user_id });

                // Update sidebar indicator
                const indicator = platform === 'douban' ? ui.doubanIndicator : ui.imdbIndicator;
                if (indicator) {
                    indicator.classList.add('online', 'connected');
                    indicator.classList.remove('disconnected', 'validating');
                }

                // Update sidebar ID
                const sidebarId = document.getElementById(`${platform}-sidebar-id`);
                if (sidebarId && data.user_id) {
                    sidebarId.textContent = `@${data.user_id}`;
                }

            } else if (platform === 'trakt') {
                appState.trakt_ready = true;
                appState.trakt_profile = data.profile;
                appState.trakt_count = data.profile?.movies_watched || appState.trakt_count || 0;
                updateTraktConnectedState(data.profile);

            } else if (platform === 'tmdb') {
                appState.tmdb_ready = true;
                updateTMDBConnectedState(data.account);
            }
        } else {
            // Validation failed - show disconnected state
            log(`❌ ${platform.toUpperCase()} ${data.error || '验证失败'}`, 'error');

            if (platform === 'douban' || platform === 'imdb') {
                appState[`${platform}_ready`] = false;
                updateProfileCardState(platform, false);

                // Update sidebar indicator to disconnected
                const indicator = platform === 'douban' ? ui.doubanIndicator : ui.imdbIndicator;
                if (indicator) {
                    indicator.classList.remove('online', 'connected', 'validating');
                    indicator.classList.add('disconnected');
                }

            } else if (platform === 'trakt') {
                appState.trakt_ready = false;
                appState.trakt_profile = null;
                updateTraktDisconnectedState();

            } else if (platform === 'tmdb') {
                appState.tmdb_ready = false;
                updateTMDBDisconnectedState();
            }
        }

        saveSessionState();
    });

    // Helper: Show validating state for a platform
    function showValidatingState(platform, userId) {
        if (platform === 'douban' || platform === 'imdb') {
            const statusBadge = document.getElementById(`${platform}-status-badge`);
            if (statusBadge) {
                statusBadge.textContent = '● 验证中...';
                statusBadge.className = 'status-badge validating';
            }

            const indicator = platform === 'douban' ? ui.doubanIndicator : ui.imdbIndicator;
            if (indicator) {
                indicator.classList.add('validating');
                indicator.classList.remove('connected', 'disconnected');
            }

            const sidebarId = document.getElementById(`${platform}-sidebar-id`);
            if (sidebarId && userId) {
                sidebarId.textContent = `@${userId}`;
            }

        } else if (platform === 'trakt') {
            const statusBadge = document.getElementById('trakt-status-badge');
            if (statusBadge) {
                statusBadge.textContent = '● 验证中...';
                statusBadge.className = 'status-badge validating';
            }
            const sidebarDot = document.getElementById('trakt-status-dot');
            if (sidebarDot) sidebarDot.className = 'status-dot validating';
            const sidebarId = document.getElementById('trakt-sidebar-id');
            if (sidebarId && userId) sidebarId.textContent = `@${userId}`;

        } else if (platform === 'tmdb') {
            const statusBadge = document.getElementById('tmdb-status-badge');
            if (statusBadge) {
                statusBadge.textContent = '● 验证中...';
                statusBadge.className = 'status-badge validating';
            }
            const statusDot = document.getElementById('tmdb-status-dot');
            if (statusDot) statusDot.className = 'status-dot validating';
        }
    }

    // Helper: Update Trakt to disconnected state
    function updateTraktDisconnectedState() {
        const notConnected = document.getElementById('trakt-not-connected');
        const connected = document.getElementById('trakt-connected');
        const statusBadge = document.getElementById('trakt-status-badge');
        const sidebarDot = document.getElementById('trakt-status-dot');

        if (notConnected) notConnected.style.display = 'block';
        if (connected) connected.style.display = 'none';
        if (statusBadge) {
            statusBadge.textContent = '● 未连接';
            statusBadge.className = 'status-badge disconnected';
        }
        if (sidebarDot) sidebarDot.className = 'status-dot disconnected';
    }

    // Helper: Update TMDB connected state
    function updateTMDBConnectedState(account) {
        const statusBadge = document.getElementById('tmdb-status-badge');
        const displayName = document.getElementById('tmdb-display-name');
        const sidebarId = document.getElementById('tmdb-sidebar-id');
        const statusDot = document.getElementById('tmdb-status-dot');
        const notConnected = document.getElementById('tmdb-not-connected');
        const connected = document.getElementById('tmdb-connected');
        const ratedCount = document.getElementById('tmdb-rated-count');
        const watchlistCount = document.getElementById('tmdb-watchlist-count');

        if (statusBadge) {
            statusBadge.textContent = '● 已授权';
            statusBadge.className = 'status-badge connected';
        }
        if (notConnected) notConnected.style.display = 'none';
        if (connected) connected.style.display = 'block';
        if (displayName && account?.username) displayName.textContent = account.username;
        if (sidebarId && account?.username) sidebarId.textContent = account.username;
        if (statusDot) statusDot.className = 'status-dot connected';
        if (ratedCount) ratedCount.textContent = account?.rated_count || '0';
        if (watchlistCount) watchlistCount.textContent = account?.watchlist_count || '0';

        // Show action buttons
        const updateBtn = document.getElementById('update-tmdb-btn');
        const logoutBtn = document.getElementById('logout-tmdb-btn');
        if (updateBtn) updateBtn.style.display = 'inline-block';
        if (logoutBtn) logoutBtn.style.display = 'inline-block';
    }

    // Helper: Update TMDB to disconnected state
    function updateTMDBDisconnectedState() {
        const statusBadge = document.getElementById('tmdb-status-badge');
        const statusDot = document.getElementById('tmdb-status-dot');
        const notConnected = document.getElementById('tmdb-not-connected');
        const connected = document.getElementById('tmdb-connected');

        if (statusBadge) {
            statusBadge.textContent = '● 未授权';
            statusBadge.className = 'status-badge disconnected';
        }
        if (statusDot) statusDot.className = 'status-dot disconnected';
        if (notConnected) notConnected.style.display = 'block';
        if (connected) connected.style.display = 'none';
    }

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
            btn.textContent = data.platform === 'douban' ? '🔑 自动登录豆瓣' : '🔑 自动登录 IMDB';
        }

        if (data.cookie) {
            // Save to appState
            appState[`${data.platform}_cookie`] = data.cookie;

            // Update Settings page cookie field
            const cookieInput = document.getElementById(`${data.platform}-cookie-config`);
            if (cookieInput) {
                cookieInput.value = data.cookie;
            }

            if (data.user_id) {
                // Save user ID to appState
                appState[`${data.platform}_user_id`] = data.user_id;

                // Also update Settings page
                const settingsUserInput = document.getElementById(`${data.platform}-user-id-config`);
                if (settingsUserInput) settingsUserInput.value = data.user_id;

                // Update sidebar ID display
                const sidebarIdEl = document.getElementById(`${data.platform}-sidebar-id`);
                if (sidebarIdEl) {
                    sidebarIdEl.textContent = `@${data.user_id}`;
                }
            }

            // Update profile card with user data
            if (data.profile) {
                updateProfileCard(data.platform, data.profile);
            }

            // Switch to connected state
            updateProfileCardState(data.platform, true, data.profile);

            // Update sidebar summary card
            updateSidebarSummary(data.platform, true, data.profile);

            log(`✅ ${data.platform.toUpperCase()} 登录成功`, 'success');
            updateAuthStatus();

            // Auto-save config after successful login
            saveConfig();
        } else {
            log(`❌ ${data.platform.toUpperCase()} 登录未捕获到 Cookie`, 'error');
        }
    });

    // Handle browser-based OAuth-style auth completion
    socket.on('browser_auth_complete', (data) => {
        if (data.success && data.user_id) {
            log(`✅ ${data.platform.toUpperCase()} 浏览器授权成功: ${data.user_id}`, 'success');

            // Update app state
            appState[`${data.platform}_user_id`] = data.user_id;
            appState[`${data.platform}_ready`] = false; // Will be set true when data is fetched

            // Update sidebar
            const sidebarIdEl = document.getElementById(`${data.platform}-sidebar-id`);
            if (sidebarIdEl) {
                sidebarIdEl.textContent = `@${data.user_id}`;
            }

            // Update profile card
            updateProfileCardState(data.platform, true, { user_id: data.user_id });

            // Update sidebar indicator
            const indicator = data.platform === 'douban' ? ui.doubanIndicator : ui.imdbIndicator;
            if (indicator) {
                indicator.classList.add('online', 'connected');
                indicator.classList.remove('disconnected', 'validating');
            }

            // Auto-save
            saveConfig();
        } else {
            log(`❌ ${data.platform.toUpperCase()} 浏览器授权失败`, 'error');
        }
    });

    // Handle auth URL for manual click (fallback when browser doesn't open)
    socket.on('browser_auth_url', (data) => {
        const { platform, url, opened } = data;
        const platformName = platform === 'douban' ? '豆瓣' : 'IMDB';

        // Always show the modal - subprocess.Popen may report success even when browser didn't open
        showAuthLinkModal(platformName, url, opened);

        // Also add to log for reference
        const logContainer = document.getElementById('log-container');
        if (logContainer) {
            const p = document.createElement('p');
            p.className = 'log-entry info';
            p.innerHTML = `🔗 <a href="${url}" target="_blank" style="color: #60a5fa; text-decoration: underline;">点击打开授权页面</a>`;
            logContainer.appendChild(p);
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    });

    // Show auth link modal when browser can't open
    function showAuthLinkModal(platformName, url, browserOpened) {
        // Remove existing modal if any
        let existingModal = document.getElementById('auth-link-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'auth-link-modal';
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8); display: flex; align-items: center;
            justify-content: center; z-index: 10000;
        `;

        const title = browserOpened ? '授权页面已打开' : '请打开授权页面';
        const subtitle = browserOpened
            ? `如果浏览器没有自动打开，请点击下方链接：`
            : `请点击下方链接手动打开${platformName}授权页面：`;

        modal.innerHTML = `
            <div style="background: #1e1e2e; border-radius: 16px; padding: 32px; 
                max-width: 420px; text-align: center; border: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 3rem; margin-bottom: 16px;">${browserOpened ? '🌐' : '🔗'}</div>
                <h3 style="color: #fff; margin-bottom: 12px;">${title}</h3>
                <p style="color: #a1a1aa; margin-bottom: 24px;">${subtitle}</p>
                <a href="${url}" target="_blank" 
                    style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #6366f1, #8b5cf6);
                    color: white; text-decoration: none; border-radius: 12px; font-weight: 600;
                    margin-bottom: 16px;">
                    打开${platformName}授权页面 →
                </a>
                <br>
                <button onclick="this.closest('#auth-link-modal').remove()" 
                    style="background: transparent; border: 1px solid rgba(255,255,255,0.2);
                    color: #a1a1aa; padding: 10px 24px; border-radius: 8px; cursor: pointer; margin-top: 8px;">
                    关闭
                </button>
            </div>
        `;
        document.body.appendChild(modal);

        // Auto-close after clicking link
        modal.querySelector('a').addEventListener('click', () => {
            setTimeout(() => modal.remove(), 500);
        });
    }

    // Update profile card UI elements with fetched data
    function updateProfileCard(platform, profile) {
        if (!profile) return;

        // Update avatar with proxy for external domains
        const avatarEl = document.getElementById(`${platform}-avatar`);
        if (avatarEl && profile.avatar) {
            // Use proxy for external avatar URLs to bypass anti-hotlinking
            const avatarUrl = proxyAvatarUrl(profile.avatar);
            avatarEl.src = avatarUrl;
        }

        // Update display name
        const nameEl = document.getElementById(`${platform}-display-name`);
        if (nameEl && profile.display_name) {
            nameEl.textContent = profile.display_name;
        }

        // Update user ID display
        const idEl = document.getElementById(`${platform}-user-id-display`);
        if (idEl && profile.user_id) {
            idEl.textContent = profile.user_id;
        }

        // Update join date
        const joinEl = document.getElementById(`${platform}-join-date`);
        if (joinEl && profile.join_date) {
            joinEl.textContent = `加入时间: ${profile.join_date}`;
        }

        // Update stats - handle different ID patterns per platform
        // Douban: watched-count, wish-count, doing-count
        // IMDB: ratings-count, watchlist-count, lists-count
        const watchedEl = document.getElementById(`${platform}-watched-count`) ||
            document.getElementById(`${platform}-ratings-count`);
        if (watchedEl && (profile.watched !== undefined || profile.ratings !== undefined)) {
            watchedEl.textContent = profile.watched || profile.ratings;
        }

        const wishEl = document.getElementById(`${platform}-wish-count`) ||
            document.getElementById(`${platform}-watchlist-count`);
        if (wishEl && (profile.wish !== undefined || profile.watchlist !== undefined)) {
            wishEl.textContent = profile.wish || profile.watchlist || 0;
        }

        const doingEl = document.getElementById(`${platform}-doing-count`) ||
            document.getElementById(`${platform}-lists-count`);
        if (doingEl && (profile.doing !== undefined || profile.lists !== undefined)) {
            doingEl.textContent = profile.doing || profile.lists || 0;
        }

        // Update profile link
        const linkEl = document.getElementById(`${platform}-profile-link`);
        if (linkEl && profile.profile_link) {
            linkEl.href = profile.profile_link;
        }

        // Update stats links  
        if (profile.user_id) {
            if (platform === 'douban') {
                const baseUrl = `https://movie.douban.com/people/${profile.user_id}/`;
                const watchedLinkEl = document.getElementById('link-douban-watched');
                if (watchedLinkEl) watchedLinkEl.href = baseUrl + 'collect';
                const wishLinkEl = document.getElementById('link-douban-wish');
                if (wishLinkEl) wishLinkEl.href = baseUrl + 'wish';
                const doingLinkEl = document.getElementById('link-douban-doing');
                if (doingLinkEl) doingLinkEl.href = baseUrl + 'do';
            } else if (platform === 'imdb') {
                const baseUrl = `https://www.imdb.com/user/${profile.user_id}/`;
                const ratingsLinkEl = document.getElementById('link-imdb-ratings');
                if (ratingsLinkEl) ratingsLinkEl.href = baseUrl + 'ratings';
                const watchlistLinkEl = document.getElementById('link-imdb-watchlist');
                if (watchlistLinkEl) watchlistLinkEl.href = baseUrl + 'watchlist';
                const listsLinkEl = document.getElementById('link-imdb-lists');
                if (listsLinkEl) listsLinkEl.href = baseUrl + 'lists';
            }
        }
    }

    // Handle test connection result - auto connect on success
    socket.on('test_result', (data) => {
        const platform = data.platform;
        const btn = platform === 'douban' ? ui.testDoubanBtn : ui.testImdbBtn;
        const updateBtn = document.getElementById(`update-${platform}-btn`);

        if (btn) {
            btn.disabled = false;
            btn.textContent = data.success ? '✅ 已连接' : '❌ 重新测试';
        }

        if (data.success && data.profile) {
            // Show Update button on successful connection
            if (updateBtn) updateBtn.style.display = 'inline-block';

            // Save user ID to appState
            if (data.profile.user_id) {
                appState[`${platform}_user_id`] = data.profile.user_id;

                // Update sidebar ID display
                const sidebarIdEl = document.getElementById(`${platform}-sidebar-id`);
                if (sidebarIdEl) {
                    sidebarIdEl.textContent = `@${data.profile.user_id}`;
                }
            }

            // Update profile card with fetched data
            updateProfileCard(platform, data.profile);

            // Switch to connected state
            updateProfileCardState(platform, true, data.profile);

            // Update sidebar summary card
            updateSidebarSummary(platform, true, data.profile);

            // Update auth status and buttons
            updateAuthStatus();
            updateButtonsBasedOnConnection();
        } else {
            // Hide Update button on failed connection
            if (updateBtn) updateBtn.style.display = 'none';
            // Update sidebar to show disconnected
            updateSidebarSummary(platform, false, null);
            // Clear sidebar ID
            const sidebarIdEl = document.getElementById(`${platform}-sidebar-id`);
            if (sidebarIdEl) {
                sidebarIdEl.textContent = '';
            }
        }
    });

    // Update sidebar summary card status
    function updateSidebarSummary(platform, connected, profile) {
        const statusDot = document.getElementById(`${platform}-status-dot`);
        const statsEl = document.getElementById(`${platform}-summary-stats`);

        if (statusDot) {
            statusDot.className = 'status-dot ' + (connected ? 'connected' : 'disconnected');
        }

        if (statsEl && profile) {
            let statsText = '';
            if (profile.watched !== undefined) {
                statsText = `${profile.watched} 已评`;
            }
            if (profile.wish !== undefined) {
                statsText += statsText ? ` / ${profile.wish} 想看` : `${profile.wish} 想看`;
            }
            if (profile.ratings !== undefined && !statsText) {
                statsText = `${profile.ratings} 评分`;
            }
            statsEl.textContent = statsText || (connected ? '已连接' : '--');
        } else if (statsEl) {
            statsEl.textContent = connected ? '已连接' : '--';
        }
        // Save session state whenever we update sidebar
        saveSessionState();
    }

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

    // Settings page test buttons
    const testDoubanSettingsBtn = document.getElementById('test-douban-settings-btn');
    const testImdbSettingsBtn = document.getElementById('test-imdb-settings-btn');
    if (testDoubanSettingsBtn) testDoubanSettingsBtn.addEventListener('click', () => testConnection('douban'));
    if (testImdbSettingsBtn) testImdbSettingsBtn.addEventListener('click', () => testConnection('imdb'));

    // Data fetch
    if (ui.fetchDoubanBtn) ui.fetchDoubanBtn.addEventListener('click', () => triggerFetch('douban'));
    if (ui.fetchImdbBtn) ui.fetchImdbBtn.addEventListener('click', () => triggerFetch('imdb'));

    // Account card update buttons (trigger same fetch function)
    const updateDoubanBtn = document.getElementById('update-douban-btn');
    const updateImdbBtn = document.getElementById('update-imdb-btn');
    if (updateDoubanBtn) updateDoubanBtn.addEventListener('click', () => triggerFetch('douban'));
    if (updateImdbBtn) updateImdbBtn.addEventListener('click', () => triggerFetch('imdb'));

    // Trakt buttons
    const traktAuthBtn = document.getElementById('trakt-auth-btn');
    const testTraktBtn = document.getElementById('test-trakt-btn');
    const updateTraktBtn = document.getElementById('update-trakt-btn');
    const traktClientIdInput = document.getElementById('trakt-client-id');
    const traktClientSecretInput = document.getElementById('trakt-client-secret');

    if (traktAuthBtn) {
        traktAuthBtn.addEventListener('click', () => {
            // Credentials are optional - backend has embedded defaults
            const clientId = traktClientIdInput?.value?.trim() || '';
            const clientSecret = traktClientSecretInput?.value?.trim() || '';

            traktAuthBtn.disabled = true;
            traktAuthBtn.textContent = '正在授权...';

            socket.emit('trakt_start_auth', {
                client_id: clientId,
                client_secret: clientSecret
            });
        });
    }


    if (testTraktBtn) {
        testTraktBtn.addEventListener('click', () => {
            socket.emit('trakt_test_connection', {});
        });
    }

    if (updateTraktBtn) {
        updateTraktBtn.addEventListener('click', () => {
            socket.emit('fetch_trakt_data', {});
        });
    }

    // Trakt logout handler
    const logoutTraktBtn = document.getElementById('logout-trakt-btn');
    if (logoutTraktBtn) {
        logoutTraktBtn.addEventListener('click', () => {
            // Emit logout event to backend
            socket.emit('trakt_logout', {});

            // Reset UI immediately
            const notConnected = document.getElementById('trakt-not-connected');
            const connected = document.getElementById('trakt-connected');
            const statusBadge = document.getElementById('trakt-status-badge');
            const authBtn = document.getElementById('trakt-auth-btn');
            const codeArea = document.getElementById('trakt-device-code-area');

            if (notConnected) notConnected.style.display = 'block';
            if (connected) connected.style.display = 'none';
            if (statusBadge) {
                statusBadge.textContent = '● 未连接';
                statusBadge.className = 'status-badge disconnected';
            }
            if (authBtn) {
                authBtn.disabled = false;
                authBtn.textContent = '🔐 授权 Trakt';
            }
            if (codeArea) codeArea.style.display = 'none';

            // Hide action buttons
            const testBtn = document.getElementById('test-trakt-btn');
            const updateBtn = document.getElementById('update-trakt-btn');
            if (testBtn) testBtn.style.display = 'none';
            if (updateBtn) updateBtn.style.display = 'none';
            logoutTraktBtn.style.display = 'none';

            // Update sidebar
            const sidebarDot = document.getElementById('trakt-status-dot');
            const sidebarStats = document.getElementById('trakt-summary-stats');
            const sidebarId = document.getElementById('trakt-sidebar-id');
            if (sidebarDot) sidebarDot.className = 'status-dot disconnected';
            if (sidebarStats) sidebarStats.textContent = '--';
            if (sidebarId) sidebarId.textContent = '';

            // Reset links
            const watchedLink = document.getElementById('link-trakt-watched');
            const ratedLink = document.getElementById('link-trakt-rated');
            if (watchedLink) watchedLink.href = '#';
            if (ratedLink) ratedLink.href = '#';

            // Clear session state for Trakt
            appState.trakt_ready = false;
            appState.trakt_profile = null;
            saveSessionState();

            log('🚪 已退出 Trakt', 'info');
        });
    }

    // Douban logout handler
    const logoutDoubanBtn = document.getElementById('logout-douban-btn');
    if (logoutDoubanBtn) {
        logoutDoubanBtn.addEventListener('click', () => {
            socket.emit('platform_logout', { platform: 'douban' });

            // Reset UI
            updateProfileCardState('douban', false);

            // Update sidebar
            const sidebarDot = document.getElementById('douban-status-dot');
            const sidebarStats = document.getElementById('douban-summary-stats');
            const sidebarId = document.getElementById('douban-sidebar-id');
            if (sidebarDot) sidebarDot.className = 'status-dot disconnected';
            if (sidebarStats) sidebarStats.textContent = '--';
            if (sidebarId) sidebarId.textContent = '';

            // Clear state
            appState.douban_ready = false;
            appState.douban_cookie = '';
            appState.douban_user_id = '';
            saveSessionState();

            log('🚪 已退出豆瓣', 'info');
        });
    }

    // IMDB logout handler
    const logoutImdbBtn = document.getElementById('logout-imdb-btn');
    if (logoutImdbBtn) {
        logoutImdbBtn.addEventListener('click', () => {
            socket.emit('platform_logout', { platform: 'imdb' });

            // Reset UI
            updateProfileCardState('imdb', false);

            // Update sidebar
            const sidebarDot = document.getElementById('imdb-status-dot');
            const sidebarStats = document.getElementById('imdb-summary-stats');
            const sidebarId = document.getElementById('imdb-sidebar-id');
            if (sidebarDot) sidebarDot.className = 'status-dot disconnected';
            if (sidebarStats) sidebarStats.textContent = '--';
            if (sidebarId) sidebarId.textContent = '';

            // Clear state
            appState.imdb_ready = false;
            appState.imdb_cookie = '';
            appState.imdb_user_id = '';
            saveSessionState();

            log('🚪 已退出 IMDB', 'info');
        });
    }

    // ==================== TMDB Handlers ====================
    const tmdbConnectBtn = document.getElementById('tmdb-connect-btn');
    const tmdbApiKeyInput = document.getElementById('tmdb-api-key');
    const tmdbAuthSessionBtn = document.getElementById('tmdb-auth-session-btn');
    const updateTmdbBtn = document.getElementById('update-tmdb-btn');
    const logoutTmdbBtn = document.getElementById('logout-tmdb-btn');

    if (tmdbConnectBtn) {
        tmdbConnectBtn.addEventListener('click', () => {
            const apiKey = tmdbApiKeyInput?.value?.trim() || '';
            if (!apiKey) {
                log('❌ 请输入 TMDB API Key', 'error');
                return;
            }
            tmdbConnectBtn.disabled = true;
            tmdbConnectBtn.textContent = '连接中...';
            socket.emit('tmdb_connect', { api_key: apiKey });
        });
    }

    if (tmdbAuthSessionBtn) {
        tmdbAuthSessionBtn.addEventListener('click', () => {
            tmdbAuthSessionBtn.disabled = true;
            tmdbAuthSessionBtn.textContent = '授权中...';
            socket.emit('tmdb_start_auth', {});
        });
    }

    if (updateTmdbBtn) {
        updateTmdbBtn.addEventListener('click', () => {
            socket.emit('fetch_tmdb_data', {});
        });
    }

    if (logoutTmdbBtn) {
        logoutTmdbBtn.addEventListener('click', () => {
            socket.emit('tmdb_logout', {});

            // Reset UI
            const notConnected = document.getElementById('tmdb-not-connected');
            const connected = document.getElementById('tmdb-connected');
            const statusBadge = document.getElementById('tmdb-status-badge');

            if (notConnected) notConnected.style.display = 'block';
            if (connected) connected.style.display = 'none';
            if (statusBadge) {
                statusBadge.textContent = '● 未连接';
                statusBadge.className = 'status-badge disconnected';
            }
            if (updateTmdbBtn) updateTmdbBtn.style.display = 'none';
            logoutTmdbBtn.style.display = 'none';

            // Clear input
            if (tmdbApiKeyInput) tmdbApiKeyInput.value = '';

            log('🚪 已断开 TMDB 连接', 'info');
        });
    }

    // TMDB socket event handlers
    socket.on('tmdb_connected', (data) => {
        const connectBtn = document.getElementById('tmdb-connect-btn');
        if (connectBtn) {
            connectBtn.disabled = false;
            connectBtn.textContent = '🔗 连接 TMDB';
        }

        if (data.success) {
            const notConnected = document.getElementById('tmdb-not-connected');
            const connected = document.getElementById('tmdb-connected');
            const statusBadge = document.getElementById('tmdb-status-badge');
            const sessionSection = document.getElementById('tmdb-session-section');

            if (notConnected) notConnected.style.display = 'none';
            if (connected) connected.style.display = 'block';
            if (statusBadge) {
                statusBadge.textContent = '● API 已连接';
                statusBadge.className = 'status-badge info';
            }
            if (sessionSection) sessionSection.style.display = 'block';
            if (logoutTmdbBtn) logoutTmdbBtn.style.display = 'inline-block';
        }
    });

    socket.on('tmdb_auth_url', (data) => {
        if (data.url) {
            window.open(data.url, '_blank');
            log('🔗 已打开 TMDB 授权页面，请在浏览器中完成授权', 'info');

            // Show confirmation button instead of auto-confirm
            const authBtn = document.getElementById('tmdb-auth-session-btn');
            if (authBtn) {
                authBtn.textContent = '✅ 我已完成授权';
                authBtn.disabled = false;
                authBtn.onclick = () => {
                    authBtn.disabled = true;
                    authBtn.textContent = '验证中...';
                    socket.emit('tmdb_complete_auth', {});
                };
            }
        }
    });

    socket.on('tmdb_auth_complete', (data) => {
        const authBtn = document.getElementById('tmdb-auth-session-btn');
        if (authBtn) {
            authBtn.disabled = false;
            authBtn.textContent = '🔐 授权同步评分';
        }

        if (data.success) {
            // Set app state
            appState.tmdb_ready = true;

            const statusBadge = document.getElementById('tmdb-status-badge');
            const sessionSection = document.getElementById('tmdb-session-section');
            const displayName = document.getElementById('tmdb-display-name');
            const userId = document.getElementById('tmdb-user-id-display');
            const sidebarId = document.getElementById('tmdb-sidebar-id');
            const statusDot = document.getElementById('tmdb-status-dot');

            // Stats elements
            const ratedCount = document.getElementById('tmdb-rated-count');
            const watchlistCount = document.getElementById('tmdb-watchlist-count');
            const ratedLink = document.getElementById('link-tmdb-rated');
            const watchlistLink = document.getElementById('link-tmdb-watchlist');
            const profileLink = document.getElementById('tmdb-profile-link');

            if (statusBadge) {
                statusBadge.textContent = '● 已授权';
                statusBadge.className = 'status-badge connected';
            }
            if (sessionSection) sessionSection.style.display = 'none';
            if (updateTmdbBtn) updateTmdbBtn.style.display = 'inline-block';

            if (displayName && data.username) displayName.textContent = data.username;
            if (userId && data.account_id) userId.textContent = data.account_id;
            if (sidebarId && data.username) sidebarId.textContent = data.username;
            if (statusDot) statusDot.className = 'status-dot connected';

            // Update stats and links
            if (ratedCount) ratedCount.textContent = data.rated_count || '0';
            if (watchlistCount) watchlistCount.textContent = data.watchlist_count || '0';
            if (ratedLink && data.rated_link) ratedLink.href = data.rated_link;
            if (watchlistLink && data.watchlist_link) watchlistLink.href = data.watchlist_link;
            if (profileLink && data.profile_link) profileLink.href = data.profile_link;
        }
    });

    socket.on('tmdb_disconnected', (data) => {
        log('✅ TMDB 已断开', 'success');
    });

    // Handle TMDB stats update (from fetch_tmdb_data)
    socket.on('tmdb_stats_updated', (data) => {
        const ratedCount = document.getElementById('tmdb-rated-count');
        const watchlistCount = document.getElementById('tmdb-watchlist-count');
        const ratedLink = document.getElementById('link-tmdb-rated');
        const watchlistLink = document.getElementById('link-tmdb-watchlist');
        const profileLink = document.getElementById('tmdb-profile-link');

        if (ratedCount) ratedCount.textContent = data.rated_count || '0';
        if (watchlistCount) watchlistCount.textContent = data.watchlist_count || '0';
        if (ratedLink && data.rated_link) ratedLink.href = data.rated_link;
        if (watchlistLink && data.watchlist_link) watchlistLink.href = data.watchlist_link;
        if (profileLink && data.profile_link) profileLink.href = data.profile_link;

        log(`📊 TMDB 统计已更新: ${data.rated_count} 已评分, ${data.watchlist_count} 想看`, 'info');
    });

    // Sidebar summary card clicks - navigate to platform and test connection
    document.querySelectorAll('.account-summary-card').forEach(card => {
        card.addEventListener('click', () => {
            const platform = card.id.replace('-summary-card', '');
            switchTab('accounts');
            // Scroll to platform card
            const fullCard = document.getElementById(`${platform}-card`);
            if (fullCard) {
                fullCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            // Auto test connection if we have cookie
            const cookie = appState[`${platform}_cookie`];
            if (cookie && (platform === 'douban' || platform === 'imdb')) {
                testConnection(platform);
            }
        });
    });
    // Sync - use direct DOM query to ensure buttons are found
    const previewBtn = document.getElementById('preview-btn');
    const syncBtn = document.getElementById('sync-btn');
    if (previewBtn) {
        previewBtn.addEventListener('click', () => triggerSync(true));
    }
    if (syncBtn) {
        syncBtn.addEventListener('click', () => triggerSync(false));
    }


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

    // Letterboxd file upload
    const uploadLetterboxdBtn = document.getElementById('upload-letterboxd-btn');
    const letterboxdFileInput = document.getElementById('letterboxd-file-input');
    const fetchLetterboxdBtn = document.getElementById('fetch-letterboxd-btn');

    if (uploadLetterboxdBtn && letterboxdFileInput) {
        uploadLetterboxdBtn.addEventListener('click', () => {
            letterboxdFileInput.click();
        });

        letterboxdFileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                log(`📁 正在读取文件: ${file.name}`, 'info');
                const reader = new FileReader();
                reader.onload = (event) => {
                    const content = event.target.result;
                    socket.emit('upload_letterboxd_csv', {
                        content: content,
                        filename: file.name
                    });
                };
                reader.onerror = () => {
                    log('❌ 文件读取失败', 'error');
                };
                reader.readAsText(file);
                // Reset file input for re-upload
                letterboxdFileInput.value = '';
            }
        });
    }

    // Data tab Letterboxd button - also trigger file picker
    if (fetchLetterboxdBtn && letterboxdFileInput) {
        fetchLetterboxdBtn.addEventListener('click', () => {
            letterboxdFileInput.click();
        });
    }

    // Data tab Trakt button - trigger data fetch
    const fetchTraktBtn = document.getElementById('fetch-trakt-btn');
    if (fetchTraktBtn) {
        fetchTraktBtn.addEventListener('click', () => {
            socket.emit('fetch_trakt_data', {});
        });
    }

    // Cookie config buttons - jump to settings page
    const configDoubanBtn = document.getElementById('config-douban-btn');
    const configImdbBtn = document.getElementById('config-imdb-btn');

    if (configDoubanBtn) {
        configDoubanBtn.addEventListener('click', () => {
            switchTab('settings');
            log('💡 请在设置页面配置豆瓣 Cookie', 'info');
            // Scroll to Douban cookie section
            setTimeout(() => {
                const doubanCookieConfig = document.getElementById('douban-cookie-config');
                if (doubanCookieConfig) {
                    doubanCookieConfig.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    doubanCookieConfig.focus();
                }
            }, 300);
        });
    }

    if (configImdbBtn) {
        configImdbBtn.addEventListener('click', () => {
            switchTab('settings');
            log('💡 请在设置页面配置 IMDB Cookie', 'info');
            // Scroll to IMDB cookie section
            setTimeout(() => {
                const imdbCookieConfig = document.getElementById('imdb-cookie-config');
                if (imdbCookieConfig) {
                    imdbCookieConfig.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    imdbCookieConfig.focus();
                }
            }, 300);
        });
    }

    // Sync to Letterboxd button - export CSV and open import page
    const syncToLetterboxdBtn = document.getElementById('sync-to-letterboxd-btn');
    if (syncToLetterboxdBtn) {
        syncToLetterboxdBtn.addEventListener('click', async () => {
            log('🔄 正在生成 Letterboxd 格式文件...', 'info');
            syncToLetterboxdBtn.disabled = true;
            syncToLetterboxdBtn.innerHTML = '<span class="loading-spinner"></span> 处理中...';

            try {
                // Request the Letterboxd format CSV from server
                const response = await fetch('/download/merged?format=letterboxd-csv');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'cinerecord_for_letterboxd.csv';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();

                log('✅ CSV 文件已下载', 'success');

                // Open Letterboxd import page in new tab
                setTimeout(() => {
                    window.open('https://letterboxd.com/import/', '_blank');
                    log('🌐 已打开 Letterboxd 导入页面，请上传刚下载的 CSV 文件', 'info');
                }, 500);

            } catch (error) {
                log(`❌ 导出失败: ${error.message}`, 'error');
            } finally {
                syncToLetterboxdBtn.disabled = false;
                syncToLetterboxdBtn.innerHTML = '🔄 同步到 Letterboxd';
            }
        });
    }

    // ========================================
    // Core Functions
    // ========================================

    function log(message, type = 'info') {
        // Use direct DOM query to ensure element is found (ui.logOutput might be null)
        const logOutput = document.getElementById('log-container');
        if (!logOutput) return;
        const p = document.createElement('p');
        p.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        p.className = type;
        logOutput.appendChild(p);
        logOutput.scrollTop = logOutput.scrollHeight;

        const placeholder = logOutput.querySelector('.placeholder');
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
            if (ui.doubanAuthStatus) {
                ui.doubanAuthStatus.textContent = '已连接';
                ui.doubanAuthStatus.classList.add('connected');
            }
        } else {
            if (ui.doubanAuthStatus) {
                ui.doubanAuthStatus.textContent = '未连接';
                ui.doubanAuthStatus.classList.remove('connected');
            }
        }

        // Check if imdb has cookie
        if (ui.imdbCookie?.value) {
            if (ui.imdbAuthStatus) {
                ui.imdbAuthStatus.textContent = '已连接';
                ui.imdbAuthStatus.classList.add('connected');
            }
        } else {
            if (ui.imdbAuthStatus) {
                ui.imdbAuthStatus.textContent = '未连接';
                ui.imdbAuthStatus.classList.remove('connected');
            }
        }
    }

    function updateButtonsBasedOnConnection() {
        // Disable update buttons if not connected (no cookie)
        const updateDoubanBtn = document.getElementById('update-douban-btn');
        const updateImdbBtn = document.getElementById('update-imdb-btn');

        const doubanConnected = !!(appState.douban_cookie && appState.douban_user_id);
        const imdbConnected = !!(appState.imdb_cookie && appState.imdb_user_id);

        if (updateDoubanBtn) {
            updateDoubanBtn.disabled = !doubanConnected;
            if (!doubanConnected) {
                updateDoubanBtn.title = '请先登录';
            } else {
                updateDoubanBtn.title = '';
            }
        }
        if (updateImdbBtn) {
            updateImdbBtn.disabled = !imdbConnected;
            if (!imdbConnected) {
                updateImdbBtn.title = '请先登录';
            } else {
                updateImdbBtn.title = '';
            }
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
        const buttons = [ui.fetchDoubanBtn, ui.fetchImdbBtn, ui.syncBtn];
        buttons.forEach(btn => { if (btn) btn.disabled = busy; });

        if (!busy) {
            // Preview button is always enabled - it will check data availability when clicked
            // Sync button only enabled after preview
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
            btn.innerHTML = '<span class="loading-spinner"></span>正在打开登录窗口...';
        }
        log(`🌐 正在打开 ${platform.toUpperCase()} 登录窗口...`, 'info');

        // Use webview-based login (seamless experience)
        socket.emit('login_popup', { platform });

        // Re-enable button after a delay (for timeout or manual close)
        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.textContent = platform === 'douban' ? '🔑 自动登录豆瓣' : '🔑 自动登录 IMDB';
            }
        }, 10000); // 10 seconds to allow login process
    }

    function testConnection(platform) {
        const btn = platform === 'douban' ? ui.testDoubanBtn : ui.testImdbBtn;
        const cookie = appState[`${platform}_cookie`] ||
            document.getElementById(`${platform}-cookie-config`)?.value || '';

        if (!cookie) {
            log(`❌ 请先在设置中配置 ${platform.toUpperCase()} Cookie`, 'error');
            switchTab('settings');
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span>测试中...';
        }

        log(`🔍 测试 ${platform.toUpperCase()} 连接...`, 'info');
        socket.emit('test_connection', { platform, cookie });
    }

    function saveConfig() {
        const configData = {
            douban_user_id: appState.douban_user_id || document.getElementById('douban-user-id-config')?.value || '',
            douban_cookie: document.getElementById('douban-cookie-config')?.value || appState.douban_cookie || '',
            imdb_user_id: appState.imdb_user_id || document.getElementById('imdb-user-id-config')?.value || '',
            imdb_cookie: document.getElementById('imdb-cookie-config')?.value || appState.imdb_cookie || '',
        };
        // Update appState
        appState.douban_cookie = configData.douban_cookie;
        appState.imdb_cookie = configData.imdb_cookie;

        socket.emit('save_config', configData);
        log('💾 配置已保存', 'success');
        highlightElement(ui.saveConfigBtn, 'success');
    }

    function triggerFetch(platform) {
        // Get userId from appState (set during login) or settings page
        const userId = appState[`${platform}_user_id`] ||
            document.getElementById(`${platform}-user-id-config`)?.value || '';
        // Get cookie from settings tab (fallback to appState)
        const cookieEl = document.getElementById(`${platform}-cookie-config`);
        const cookie = cookieEl?.value || appState[`${platform}_cookie`] || '';

        if (!userId) {
            log(`❌ 请先登录 ${platform.toUpperCase()} 账号`, 'error');
            return;
        }

        if (!cookie) {
            log(`⚠️ 未配置 Cookie，尝试获取公开数据...`, 'info');
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
        // Use direct DOM query instead of cached ui reference (ui.syncDirection may be null)
        const syncDirEl = document.getElementById('sync-direction');
        const direction = syncDirEl?.value || 'douban-to-imdb';


        // Validate based on sync direction
        if (direction === 'douban-to-imdb' || direction === 'imdb-to-douban') {
            if (!appState.douban_ready && !appState.imdb_ready) {
                log('❌ 请先在"数据"标签页获取豆瓣和IMDB数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.douban_ready) {
                log('❌ 请先获取豆瓣数据', 'error');
                return;
            }
            if (!appState.imdb_ready) {
                log('❌ 请先获取IMDB数据', 'error');
                return;
            }
        } else if (direction === 'trakt-to-douban') {
            // Need Trakt cached data and Douban cookie
            // Note: trakt_count is set when cached data is loaded, even if token is expired
            if (!appState.trakt_count) {
                log('❌ 请先获取 Trakt 数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.douban_cookie) {
                log('❌ 请先登录豆瓣账号', 'error');
                switchTab('account');
                return;
            }
            // Use socket event for trakt-to-douban
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} Trakt → 豆瓣 同步...`, 'info');
            socket.emit('sync_trakt_to_douban', {
                with_ratings: true,
                is_dry_run: isDryRun
            });
            return;
        } else if (direction === 'imdb-to-trakt') {
            // Need IMDB data and Trakt auth
            if (!appState.imdb_ready || !appState.imdb_count) {
                log('❌ 请先获取 IMDB 数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.trakt_ready) {
                log('❌ 请先授权 Trakt 账号', 'error');
                switchTab('account');
                return;
            }
            // Use socket event for imdb-to-trakt
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} IMDB → Trakt 同步...`, 'info');
            socket.emit('sync_imdb_to_trakt', {
                is_dry_run: isDryRun
            });
            return;
        } else if (direction === 'imdb-to-tmdb') {
            // Need IMDB data and TMDB auth
            if (!appState.imdb_ready || !appState.imdb_count) {
                log('❌ 请先获取 IMDB 数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.tmdb_ready) {
                log('❌ 请先授权 TMDB 账号', 'error');
                switchTab('accounts');
                return;
            }
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} IMDB → TMDB 同步...`, 'info');
            socket.emit('sync_imdb_to_tmdb', {
                is_dry_run: isDryRun
            });
            return;
        } else if (direction === 'trakt-to-tmdb') {
            // Need Trakt cached data and TMDB auth
            // Note: trakt_count is set when cached data is loaded, even if token is expired
            if (!appState.trakt_count) {
                log('❌ 请先获取 Trakt 数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.tmdb_ready) {
                log('❌ 请先授权 TMDB 账号', 'error');
                switchTab('accounts');
                return;
            }
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} Trakt → TMDB 同步...`, 'info');
            socket.emit('sync_trakt_to_tmdb', {
                is_dry_run: isDryRun
            });
            return;
        }

        setButtonsState(true);
        if (ui.progressCard) ui.progressCard.style.display = 'none';

        if (ui.syncPreviewList) ui.syncPreviewList.innerHTML = '';
        if (ui.syncFailedList) ui.syncFailedList.innerHTML = '';
        if (ui.syncPreviewCard) ui.syncPreviewCard.style.display = 'none';
        if (ui.syncFailedCard) ui.syncFailedCard.style.display = 'none';

        log(`🚀 开始${isDryRun ? '预览' : '执行'}同步...`, 'info');
        socket.emit('start_sync', {
            direction: direction,
            is_dry_run: isDryRun,
            douban_cookie: appState.douban_cookie || '',
            imdb_cookie: appState.imdb_cookie || ''
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
        const source = ui.exportSource?.value || 'merged';
        log(`📤 导出数据: ${source} -> CSV`, 'info');

        // Use hidden iframe to trigger browser download
        const downloadUrl = `/download/${source}?format=cinerecord-csv&t=${Date.now()}`;

        // Create hidden iframe to trigger download
        let iframe = document.getElementById('download-iframe');
        if (!iframe) {
            iframe = document.createElement('iframe');
            iframe.id = 'download-iframe';
            iframe.style.display = 'none';
            document.body.appendChild(iframe);
        }
        iframe.src = downloadUrl;

        log(`✅ 下载已开始: ${source}_ratings.csv`, 'success');
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
            // Store the movie data in appState for session persistence
            appState[`${data.platform}_data`] = data.sample || [];
            renderDataSample(data.platform, data);

            // Handle download button for all platforms including Trakt
            let downloadBtn;
            if (data.platform === 'douban') downloadBtn = ui.doubanDownloadBtn;
            else if (data.platform === 'imdb') downloadBtn = ui.imdbDownloadBtn;
            else if (data.platform === 'trakt') downloadBtn = document.getElementById('trakt-download-btn');
            else if (data.platform === 'letterboxd') downloadBtn = document.getElementById('letterboxd-download-btn');

            if (downloadBtn) {
                downloadBtn.href = `/download/${data.platform}`;
                downloadBtn.style.display = 'inline-block';
            }

            log(`✅ ${data.platform.toUpperCase()} 数据获取完成: ${data.total_count} 部`, 'success');
        }

        updatePlatformStatus();
        handleTaskFinished('fetch');

        // Save session state after data fetch completes
        saveSessionState();
    }

    function renderDataSample(platform, data) {
        // Handle all platforms dynamically using getElementById
        const previewCard = document.getElementById(`${platform}-preview-card`);
        const summaryEl = document.getElementById(`${platform}-summary`);
        const previewEl = document.getElementById(`${platform}-preview`);

        if (!previewCard || !summaryEl || !previewEl) {
            console.warn(`Preview elements not found for platform: ${platform}`);
            return;
        }

        if (!data.sample || data.sample.length === 0) {
            summaryEl.textContent = '';
            previewEl.innerHTML = '<p class="placeholder">未找到数据</p>';
            previewCard.style.display = 'block';
            return;
        }

        summaryEl.textContent = `共 ${data.total_count} 条`;

        // Render movie list with covers
        let html = '<div class="movie-list-preview">';
        data.sample.forEach(movie => {
            const movieUrl = movie['URL'] || movie['URL_douban'] || movie['URL_imdb'] || '#';
            const coverUrl = movie['Cover URL'] || movie['CoverURL'] || '';
            const title = movie['Title'] || movie['title'] || '未知标题';
            const year = movie['Year'] || movie['year'] || '';
            const myRating = movie['Your Rating'] || movie['YourRating_douban'] || movie['YourRating_imdb'] || '';
            const dateWatched = movie['Date Watched'] || movie['Date Rated'] || '';
            const directors = movie['Directors'] || '';
            const genres = movie['Genres'] || '';
            // Platform ratings
            const doubanRating = movie['Douban Rating'] || '';
            const imdbRating = movie['IMDb Rating'] || '';
            const numVotes = movie['Num Votes'] || movie['Num Votes_douban'] || '';

            // Public rating display (inline with title)
            let publicRatingHtml = '';
            if (doubanRating) publicRatingHtml += `<span class="platform-rating douban">豆瓣 ${doubanRating}</span>`;
            if (imdbRating) publicRatingHtml += `<span class="platform-rating imdb">IMDb ${imdbRating}</span>`;

            html += `
                <div class="movie-item">
                    <img class="movie-cover" src="${coverUrl}" alt="${title}" onerror="this.style.display='none'">
                    <div class="movie-info">
                        <h4>
                            <a href="${movieUrl}" target="_blank">${title}</a>
                            ${publicRatingHtml}
                        </h4>
                        <p class="meta">${year}${numVotes ? ` <span class="vote-count">(${numVotes}人评价)</span>` : ''}${genres ? ' / ' + genres : ''}${directors ? ' / ' + directors : ''}</p>
                        <p class="user-rating-line">
                            ${dateWatched ? `<span>标注于 ${dateWatched}</span>` : ''}
                            ${myRating ? `<span class="my-score">★ 我的评分: ${myRating}</span>` : ''}
                        </p>
                    </div>
                </div>
            `;
        });
        html += '</div>';

        // Add pagination controls
        const currentPage = data.page || 1;
        const totalPages = data.total_pages || Math.ceil(data.total_count / 10);

        html += `
            <div class="pagination-controls" data-platform="${platform}" data-page="${currentPage}" data-total="${totalPages}">
                <button class="btn btn-outline btn-sm" onclick="changePage('${platform}', ${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''}>« 上一页</button>
                <span class="page-info">第 ${currentPage} / ${totalPages} 页 (共 ${data.total_count} 条)</span>
                <button class="btn btn-outline btn-sm" onclick="changePage('${platform}', ${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''}>下一页 »</button>
            </div>
        `;

        previewEl.innerHTML = html;
        previewCard.style.display = 'block';

        // Also update account card to connected state
        updateProfileCardState(platform, true, data);
    }

    // Render Letterboxd data sample (similar to Douban/IMDB format)
    function renderLetterboxdDataSample(data) {
        const previewCard = document.getElementById('letterboxd-preview-card');
        const summaryEl = document.getElementById('letterboxd-summary');
        const previewEl = document.getElementById('letterboxd-preview');
        const downloadBtn = document.getElementById('letterboxd-download-btn');

        if (!previewCard || !previewEl) return;

        if (!data.sample || data.sample.length === 0) {
            if (summaryEl) summaryEl.textContent = '';
            previewEl.innerHTML = '<p class="placeholder">未找到数据</p>';
            previewCard.style.display = 'block';
            return;
        }

        if (summaryEl) summaryEl.textContent = `共 ${data.total_count} 条 (${data.rated_count} 已评)`;

        // Render movie list (simpler format since Letterboxd has less metadata)
        let html = '<div class="movie-list-preview">';
        data.sample.forEach(movie => {
            const movieUrl = movie['URL'] || '#';
            const title = movie['Title'] || '未知标题';
            const year = movie['Year'] || '';
            const myRating = movie['Your Rating'] || '';
            const dateWatched = movie['Date Rated'] || '';

            html += `
                <div class="movie-item">
                    <div class="movie-cover-placeholder">🎞️</div>
                    <div class="movie-info">
                        <h4>
                            <a href="${movieUrl}" target="_blank">${title}</a>
                            ${year ? `<span class="year-tag">(${year})</span>` : ''}
                        </h4>
                        <p class="user-rating-line">
                            ${dateWatched ? `<span>观看于 ${dateWatched}</span>` : ''}
                            ${myRating ? `<span class="my-score">★ 我的评分: ${myRating}</span>` : '<span class="no-rating">未评分</span>'}
                        </p>
                    </div>
                </div>
            `;
        });
        html += '</div>';

        // Add pagination controls
        const currentPage = data.page || 1;
        const totalPages = data.total_pages || Math.ceil(data.total_count / 10);

        html += `
            <div class="pagination-controls" data-platform="letterboxd" data-page="${currentPage}" data-total="${totalPages}">
                <button class="btn btn-outline btn-sm" onclick="changePage('letterboxd', ${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''}>« 上一页</button>
                <span class="page-info">第 ${currentPage} / ${totalPages} 页 (共 ${data.total_count} 条)</span>
                <button class="btn btn-outline btn-sm" onclick="changePage('letterboxd', ${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''}>下一页 »</button>
            </div>
        `;

        previewEl.innerHTML = html;
        previewCard.style.display = 'block';

        // Show download button if data available
        if (downloadBtn) {
            downloadBtn.href = `/download/letterboxd`;
            downloadBtn.style.display = 'inline-block';
        }
    }

    // Handle page data from pagination request
    function handlePageData(data) {
        if (data.platform === 'letterboxd') {
            renderLetterboxdDataSample(data);
        } else {
            renderDataSample(data.platform, data);
        }

    }

    // Global function for pagination button clicks
    window.changePage = function (platform, page) {
        if (page < 1) return;
        socket.emit('get_page', { platform, page, page_size: 10 });
        log(`📄 加载第 ${page} 页...`, 'info');
    };

    // Switch profile card between connected/not-connected states
    function updateProfileCardState(platform, isConnected, profileData = null) {
        const notConnectedEl = document.getElementById(`${platform}-not-connected`);
        const connectedEl = document.getElementById(`${platform}-connected`);
        const statusBadge = document.getElementById(`${platform}-status-badge`);
        const logoutBtn = document.getElementById(`logout-${platform}-btn`);

        if (!notConnectedEl || !connectedEl) return;

        if (isConnected) {
            notConnectedEl.style.display = 'none';
            connectedEl.style.display = 'block';
            if (logoutBtn) logoutBtn.style.display = 'inline-flex';

            if (statusBadge) {
                statusBadge.textContent = '● 已连接';
                statusBadge.className = 'status-badge connected';
            }

            // Update profile info if data provided
            if (profileData) {
                const displayNameEl = document.getElementById(`${platform}-display-name`);
                const userIdDisplayEl = document.getElementById(`${platform}-user-id-display`);
                const watchedCountEl = document.getElementById(`${platform}-watched-count`);

                if (displayNameEl && profileData.username) {
                    displayNameEl.textContent = profileData.username;
                }
                if (userIdDisplayEl && profileData.user_id) {
                    userIdDisplayEl.textContent = profileData.user_id;
                }
                if (watchedCountEl && profileData.total_count) {
                    watchedCountEl.textContent = profileData.total_count;
                }
            }
        } else {
            notConnectedEl.style.display = 'flex';
            connectedEl.style.display = 'none';
            if (logoutBtn) logoutBtn.style.display = 'none';

            if (statusBadge) {
                statusBadge.textContent = '● 未连接';
                statusBadge.className = 'status-badge disconnected';
            }
        }
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

    // Store sync preview data for pagination
    let syncPreviewData = [];
    let syncPreviewPage = 1;
    const syncPreviewPageSize = 10;

    function renderSyncPreview(movies) {
        if (!movies || movies.length === 0) {
            log('✅ 无需同步，平台数据已一致', 'success');
            setButtonsState(false);
            return;
        }

        // Store for pagination
        syncPreviewData = movies;
        syncPreviewPage = 1;

        renderSyncPreviewPage();

        // Enable sync button after successful preview
        if (ui.syncBtn && movies.length > 0) {
            ui.syncBtn.disabled = false;
        }

        log(`🔍 预览完成，发现 ${movies.length} 部电影可同步`, 'success');
        setButtonsState(false);
    }

    function renderSyncPreviewPage() {
        if (!ui.syncPreviewList || !ui.syncPreviewCard) return;

        const start = (syncPreviewPage - 1) * syncPreviewPageSize;
        const end = start + syncPreviewPageSize;
        const pageMovies = syncPreviewData.slice(start, end);
        const totalPages = Math.ceil(syncPreviewData.length / syncPreviewPageSize);

        // Build movie list HTML (similar to data tab format)
        let html = '<div class="movie-list-preview">';
        pageMovies.forEach(movie => {
            const coverUrl = movie['Cover URL'] || '';
            const rating = movie['Your Rating'] || movie['YourRating_douban'] || movie['YourRating_imdb'] || '';
            const movieUrl = movie['URL_douban'] || movie['URL_imdb'] || movie['URL'] || '#';
            const title = movie['Title'] || movie.title || '未知';
            const year = movie['Year'] || movie.year || '';
            const directors = movie['Directors'] || '';
            const genres = movie['Genres'] || '';
            const doubanRating = movie['Douban Rating'] || '';
            const imdbRating = movie['IMDb Rating'] || '';

            let publicRatingHtml = '';
            if (doubanRating) publicRatingHtml += `<span class="platform-rating douban">豆瓣 ${doubanRating}</span>`;
            if (imdbRating) publicRatingHtml += `<span class="platform-rating imdb">IMDb ${imdbRating}</span>`;

            html += `
                <div class="movie-item">
                    <img class="movie-cover" src="${coverUrl}" alt="${title}" onerror="this.style.display='none'">
                    <div class="movie-info">
                        <h4>
                            <a href="${movieUrl}" target="_blank">${title}${year ? ` (${year})` : ''}</a>
                            ${publicRatingHtml}
                        </h4>
                        <p class="meta">${genres}${directors ? ' / ' + directors : ''}</p>
                        <p class="user-rating-line">
                            ${rating ? `<span class="my-score">★ 我的评分: ${rating}</span>` : ''}
                        </p>
                    </div>
                </div>
            `;
        });
        html += '</div>';

        // Add pagination controls
        html += `
            <div class="pagination-controls" style="margin-top: 16px; display: flex; justify-content: center; align-items: center; gap: 12px;">
                <button class="btn btn-outline btn-sm" onclick="window.changeSyncPreviewPage(${syncPreviewPage - 1})" ${syncPreviewPage <= 1 ? 'disabled' : ''}>« 上一页</button>
                <span class="page-info">第 ${syncPreviewPage} / ${totalPages} 页 (共 ${syncPreviewData.length} 条)</span>
                <button class="btn btn-outline btn-sm" onclick="window.changeSyncPreviewPage(${syncPreviewPage + 1})" ${syncPreviewPage >= totalPages ? 'disabled' : ''}>下一页 »</button>
            </div>
        `;

        ui.syncPreviewList.innerHTML = html;
        ui.syncPreviewCard.style.display = 'block';

        // Update summary
        const summaryEl = document.getElementById('sync-preview-summary');
        if (summaryEl) {
            summaryEl.textContent = `共 ${syncPreviewData.length} 条待同步`;
        }
    }

    // Global function for sync preview pagination
    window.changeSyncPreviewPage = function (page) {
        const totalPages = Math.ceil(syncPreviewData.length / syncPreviewPageSize);
        if (page < 1 || page > totalPages) return;
        syncPreviewPage = page;
        renderSyncPreviewPage();
    };

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

    function renderUnratedMovies(data) {
        // Display unrated movies that cannot sync to IMDb
        const unratedCard = document.getElementById('sync-unrated-card');
        const unratedList = document.getElementById('sync-unrated-list');
        const unratedSummary = document.getElementById('sync-unrated-summary');

        if (!unratedCard || !unratedList || !data.movies || data.movies.length === 0) {
            if (unratedCard) unratedCard.style.display = 'none';
            return;
        }

        unratedCard.style.display = 'block';
        if (unratedSummary) {
            unratedSummary.textContent = `${data.count} 部待评价`;
        }

        // Render movie list
        let html = '<div class="movie-list-preview">';
        data.movies.slice(0, 20).forEach(movie => {
            const coverUrl = movie['Cover URL'] || '';
            const title = movie['Title'] || movie.title || '未知';
            const year = movie['Year'] || movie.year || '';
            const movieUrl = movie['URL_douban'] || movie['URL'] || '#';

            html += `
                <div class="movie-item unrated-item">
                    <img class="movie-cover" src="${coverUrl}" alt="${title}" onerror="this.style.display='none'">
                    <div class="movie-info">
                        <h4>
                            <a href="${movieUrl}" target="_blank">${title}${year ? ` (${year})` : ''}</a>
                            <span class="no-rating-badge">待评价</span>
                        </h4>
                        <p class="help-text">请在豆瓣评分后再同步到 IMDb</p>
                    </div>
                </div>
            `;
        });
        if (data.movies.length > 20) {
            html += `<p class="help-text">... 还有 ${data.movies.length - 20} 部未显示</p>`;
        }
        html += '</div>';

        unratedList.innerHTML = html;
        log(`⚠️ ${data.count} 部电影无评分，无法同步到 IMDb`, 'info');
    }

    function handleTaskFinished(taskType) {
        log(`🏁 ${taskType === 'fetch' ? '数据获取' : '同步'}完成`, 'info');
        setButtonsState(false);
        if (ui.progressCard) ui.progressCard.style.display = 'none';
    }

    // ========================================
    // Session Persistence with localStorage
    // ========================================

    function saveSessionState() {
        try {
            const sessionData = {
                version: 3, // Version for future compatibility
                timestamp: Date.now(),
                appState: {
                    douban_user_id: appState.douban_user_id,
                    imdb_user_id: appState.imdb_user_id,
                    douban_ready: appState.douban_ready,
                    imdb_ready: appState.imdb_ready,
                    trakt_ready: appState.trakt_ready,
                    letterboxd_ready: appState.letterboxd_ready,
                    douban_count: appState.douban_count,
                    imdb_count: appState.imdb_count,
                    letterboxd_count: appState.letterboxd_count,
                    letterboxd_rated: appState.letterboxd_rated,
                },
                platforms: {},
                // NEW: Save logs (last 100 entries)
                logs: [],
                // NEW: Save active tab
                activeTab: document.querySelector('.nav-tab.active')?.dataset.tab || 'accounts',
                // NEW: Save movie data (first 50 entries per platform to limit size)
                movieData: {},
                // NEW: Save data preview card states
                dataPreviewStates: {}
            };

            // Save logs from log container (last 100)
            const logContainer = document.getElementById('log-container');
            if (logContainer) {
                const logEntries = logContainer.querySelectorAll('p');
                const logsArray = Array.from(logEntries).slice(-100).map(p => ({
                    text: p.textContent,
                    class: p.className
                }));
                sessionData.logs = logsArray;
            }

            // Save movie data (limited to first 50 entries per platform)
            if (appState.douban_data && appState.douban_data.length > 0) {
                sessionData.movieData.douban = appState.douban_data.slice(0, 50);
                sessionData.movieData.douban_total = appState.douban_data.length;
            }
            if (appState.imdb_data && appState.imdb_data.length > 0) {
                sessionData.movieData.imdb = appState.imdb_data.slice(0, 50);
                sessionData.movieData.imdb_total = appState.imdb_data.length;
            }
            if (appState.letterboxd_data && appState.letterboxd_data.length > 0) {
                sessionData.movieData.letterboxd = appState.letterboxd_data.slice(0, 50);
                sessionData.movieData.letterboxd_total = appState.letterboxd_data.length;
            }

            // Save data preview card visibility
            ['douban', 'imdb', 'letterboxd'].forEach(platform => {
                const previewCard = document.getElementById(`${platform}-preview-card`);
                const summary = document.getElementById(`${platform}-summary`);
                sessionData.dataPreviewStates[platform] = {
                    visible: previewCard?.style.display !== 'none',
                    summary: summary?.textContent || ''
                };
            });

            // Save platform status and profile data from DOM
            ['douban', 'imdb', 'letterboxd', 'trakt'].forEach(platform => {
                const statusDot = document.getElementById(`${platform}-status-dot`);
                const statsEl = document.getElementById(`${platform}-summary-stats`);
                const statusBadge = document.getElementById(`${platform}-status-badge`);
                const notConnected = document.getElementById(`${platform}-not-connected`);
                const connected = document.getElementById(`${platform}-connected`);
                const sidebarId = document.getElementById(`${platform}-sidebar-id`);

                sessionData.platforms[platform] = {
                    connected: statusDot?.classList.contains('connected') || false,
                    stats: statsEl?.textContent || '--',
                    statusBadge: statusBadge?.textContent || '',
                    notConnectedVisible: notConnected?.style.display !== 'none',
                    connectedVisible: connected?.style.display !== 'none',
                    sidebarId: sidebarId?.textContent || ''
                };

                // Save profile info for each platform (Douban/IMDB)
                if (platform === 'douban' || platform === 'imdb') {
                    const userIdDisplay = document.getElementById(`${platform}-user-id-display`);
                    const displayName = document.getElementById(`${platform}-display-name`);
                    const avatar = document.getElementById(`${platform}-avatar`);
                    const joinDate = document.getElementById(`${platform}-join-date`);
                    const watchedCount = document.getElementById(`${platform}-watched-count`);
                    const wishCount = document.getElementById(`${platform}-wish-count`);
                    const doingCount = document.getElementById(`${platform}-doing-count`);
                    const ratingsCount = document.getElementById(`${platform}-ratings-count`);
                    const watchlistCount = document.getElementById(`${platform}-watchlist-count`);
                    const listsCount = document.getElementById(`${platform}-lists-count`);
                    const profileLink = document.getElementById(`${platform}-profile-link`);
                    // Stat links
                    const watchedLink = document.getElementById(`link-${platform}-watched`);
                    const wishLink = document.getElementById(`link-${platform}-wish`);
                    const doingLink = document.getElementById(`link-${platform}-doing`);
                    const ratingsLink = document.getElementById(`link-${platform}-ratings`);
                    const watchlistLink = document.getElementById(`link-${platform}-watchlist`);
                    const listsLink = document.getElementById(`link-${platform}-lists`);

                    sessionData.platforms[platform].profile = {
                        userId: userIdDisplay?.textContent || '--',
                        displayName: displayName?.textContent || '用户名',
                        avatar: avatar?.src || '',
                        joinDate: joinDate?.textContent || '',
                        watched: watchedCount?.textContent || '--',
                        wish: wishCount?.textContent || '--',
                        doing: doingCount?.textContent || '--',
                        ratings: ratingsCount?.textContent || '--',
                        watchlist: watchlistCount?.textContent || '--',
                        lists: listsCount?.textContent || '--',
                        link: profileLink?.href || '#',
                        // Save stat link hrefs
                        watchedLink: watchedLink?.href || '#',
                        wishLink: wishLink?.href || '#',
                        doingLink: doingLink?.href || '#',
                        ratingsLink: ratingsLink?.href || '#',
                        watchlistLink: watchlistLink?.href || '#',
                        listsLink: listsLink?.href || '#'
                    };
                } else if (platform === 'trakt') {
                    const displayName = document.getElementById('trakt-display-name');
                    const userIdDisplay = document.getElementById('trakt-user-id-display');
                    const watchedCount = document.getElementById('trakt-watched-count');
                    const ratedCount = document.getElementById('trakt-rated-count');
                    const profileLink = document.getElementById('trakt-profile-link');
                    const avatar = document.getElementById('trakt-avatar');

                    sessionData.platforms[platform].profile = {
                        displayName: displayName?.textContent || '用户',
                        userId: userIdDisplay?.textContent || '--',
                        watched: watchedCount?.textContent || '--',
                        rated: ratedCount?.textContent || '--',
                        link: profileLink?.href || '#',
                        avatar: avatar?.src || ''
                    };
                } else if (platform === 'letterboxd') {
                    const watchedCount = document.getElementById('letterboxd-watched-count');
                    const ratedCount = document.getElementById('letterboxd-rated-count');

                    sessionData.platforms[platform].profile = {
                        watched: watchedCount?.textContent || '--',
                        rated: ratedCount?.textContent || '--'
                    };
                }
            });

            localStorage.setItem('cinerecord_session', JSON.stringify(sessionData));
        } catch (e) {
            console.error('Failed to save session state:', e);
        }
    }

    function restoreSessionState() {
        try {
            const savedData = localStorage.getItem('cinerecord_session');
            if (!savedData) return;

            const sessionData = JSON.parse(savedData);

            // Check if data is too old (24 hours)
            if (sessionData.timestamp && Date.now() - sessionData.timestamp > 24 * 60 * 60 * 1000) {
                localStorage.removeItem('cinerecord_session');
                return;
            }

            // Restore appState
            if (sessionData.appState) {
                Object.assign(appState, sessionData.appState);
            }

            // NEW: Restore logs
            if (sessionData.logs && sessionData.logs.length > 0) {
                const logContainer = document.getElementById('log-container');
                if (logContainer) {
                    logContainer.innerHTML = '';
                    sessionData.logs.forEach(logEntry => {
                        const p = document.createElement('p');
                        p.textContent = logEntry.text;
                        p.className = logEntry.class || '';
                        logContainer.appendChild(p);
                    });
                    // Scroll to bottom
                    logContainer.scrollTop = logContainer.scrollHeight;
                }
            }

            // NEW: Restore active tab
            if (sessionData.activeTab) {
                const targetTab = document.querySelector(`.nav-tab[data-tab="${sessionData.activeTab}"]`);
                const targetContent = document.getElementById(`tab-${sessionData.activeTab}`);
                if (targetTab && targetContent) {
                    // Switch tabs
                    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
                    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                    targetTab.classList.add('active');
                    targetContent.classList.add('active');
                }
            }

            // NEW: Restore movie data
            if (sessionData.movieData) {
                if (sessionData.movieData.douban) {
                    appState.douban_data = sessionData.movieData.douban;
                    // Note: limited data, show message about partial restore
                }
                if (sessionData.movieData.imdb) {
                    appState.imdb_data = sessionData.movieData.imdb;
                }
                if (sessionData.movieData.letterboxd) {
                    appState.letterboxd_data = sessionData.movieData.letterboxd;
                }
            }

            // NEW: Restore data preview card states
            if (sessionData.dataPreviewStates) {
                ['douban', 'imdb', 'letterboxd'].forEach(platform => {
                    const state = sessionData.dataPreviewStates[platform];
                    if (state && state.visible) {
                        const previewCard = document.getElementById(`${platform}-preview-card`);
                        const summary = document.getElementById(`${platform}-summary`);
                        const previewContainer = document.getElementById(`${platform}-preview`);

                        if (previewCard) previewCard.style.display = 'block';
                        if (summary) summary.textContent = state.summary;

                        // Re-render movie preview if we have data
                        // Use actual count from appState (set by session_restored) not movieData.length
                        const movieData = appState[`${platform}_data`];
                        const actualCount = appState[`${platform}_count`] || movieData?.length || 0;
                        if (previewContainer && movieData && movieData.length > 0) {
                            // Request full paginated data from backend for proper total count
                            socket.emit('get_page', { platform, page: 1, page_size: 10 });
                        }
                    }
                });
            }

            // Restore platform UI states
            if (sessionData.platforms) {
                Object.keys(sessionData.platforms).forEach(platform => {
                    const data = sessionData.platforms[platform];

                    // Restore sidebar status
                    const statusDot = document.getElementById(`${platform}-status-dot`);
                    const statsEl = document.getElementById(`${platform}-summary-stats`);
                    const sidebarId = document.getElementById(`${platform}-sidebar-id`);

                    if (statusDot && data.connected) {
                        statusDot.className = 'status-dot connected';
                    }
                    if (statsEl && data.stats && data.stats !== '--') {
                        statsEl.textContent = data.stats;
                    }
                    if (sidebarId && data.sidebarId) {
                        sidebarId.textContent = data.sidebarId;
                    }

                    // Restore account card state
                    const statusBadge = document.getElementById(`${platform}-status-badge`);
                    const notConnected = document.getElementById(`${platform}-not-connected`);
                    const connected = document.getElementById(`${platform}-connected`);

                    if (data.connected && data.connectedVisible) {
                        if (notConnected) notConnected.style.display = 'none';
                        if (connected) connected.style.display = 'block';
                        if (statusBadge) {
                            statusBadge.textContent = data.statusBadge || '● 已连接';
                            statusBadge.className = 'status-badge connected';
                        }

                        // Show action buttons and set proper text
                        const testBtn = document.getElementById(`test-${platform}-btn`);
                        const updateBtn = document.getElementById(`update-${platform}-btn`);
                        if (testBtn) {
                            testBtn.style.display = 'inline-block';
                            testBtn.textContent = '✅ 已连接';
                        }
                        if (updateBtn) updateBtn.style.display = 'inline-block';
                    }

                    // Restore profile info
                    if (data.profile) {
                        if (platform === 'douban' || platform === 'imdb') {
                            // Basic profile elements
                            const userIdDisplay = document.getElementById(`${platform}-user-id-display`);
                            const displayName = document.getElementById(`${platform}-display-name`);
                            const avatar = document.getElementById(`${platform}-avatar`);
                            const joinDate = document.getElementById(`${platform}-join-date`);
                            const profileLink = document.getElementById(`${platform}-profile-link`);

                            // Stat count elements
                            const watchedCount = document.getElementById(`${platform}-watched-count`);
                            const wishCount = document.getElementById(`${platform}-wish-count`);
                            const doingCount = document.getElementById(`${platform}-doing-count`);
                            const ratingsCount = document.getElementById(`${platform}-ratings-count`);
                            const watchlistCount = document.getElementById(`${platform}-watchlist-count`);
                            const listsCount = document.getElementById(`${platform}-lists-count`);

                            // Stat link elements
                            const watchedLink = document.getElementById(`link-${platform}-watched`);
                            const wishLink = document.getElementById(`link-${platform}-wish`);
                            const doingLink = document.getElementById(`link-${platform}-doing`);
                            const ratingsLink = document.getElementById(`link-${platform}-ratings`);
                            const watchlistLink = document.getElementById(`link-${platform}-watchlist`);
                            const listsLink = document.getElementById(`link-${platform}-lists`);

                            // Restore basic profile
                            if (userIdDisplay) userIdDisplay.textContent = data.profile.userId || '--';
                            if (displayName && data.profile.displayName) displayName.textContent = data.profile.displayName;
                            if (avatar && data.profile.avatar) avatar.src = data.profile.avatar;
                            if (joinDate && data.profile.joinDate) joinDate.textContent = data.profile.joinDate;
                            if (profileLink && data.profile.link && data.profile.link !== '#') profileLink.href = data.profile.link;

                            // Restore stat counts
                            if (watchedCount && data.profile.watched) watchedCount.textContent = data.profile.watched;
                            if (wishCount && data.profile.wish) wishCount.textContent = data.profile.wish;
                            if (doingCount && data.profile.doing) doingCount.textContent = data.profile.doing;
                            if (ratingsCount && data.profile.ratings) ratingsCount.textContent = data.profile.ratings;
                            if (watchlistCount && data.profile.watchlist) watchlistCount.textContent = data.profile.watchlist;
                            if (listsCount && data.profile.lists) listsCount.textContent = data.profile.lists;

                            // Restore stat links
                            if (watchedLink && data.profile.watchedLink && data.profile.watchedLink !== '#') watchedLink.href = data.profile.watchedLink;
                            if (wishLink && data.profile.wishLink && data.profile.wishLink !== '#') wishLink.href = data.profile.wishLink;
                            if (doingLink && data.profile.doingLink && data.profile.doingLink !== '#') doingLink.href = data.profile.doingLink;
                            if (ratingsLink && data.profile.ratingsLink && data.profile.ratingsLink !== '#') ratingsLink.href = data.profile.ratingsLink;
                            if (watchlistLink && data.profile.watchlistLink && data.profile.watchlistLink !== '#') watchlistLink.href = data.profile.watchlistLink;
                            if (listsLink && data.profile.listsLink && data.profile.listsLink !== '#') listsLink.href = data.profile.listsLink;
                        } else if (platform === 'trakt') {
                            const displayName = document.getElementById('trakt-display-name');
                            const userIdDisplay = document.getElementById('trakt-user-id-display');
                            const watchedCount = document.getElementById('trakt-watched-count');
                            const ratedCount = document.getElementById('trakt-rated-count');
                            const profileLink = document.getElementById('trakt-profile-link');
                            const avatar = document.getElementById('trakt-avatar');
                            const logoutBtn = document.getElementById('logout-trakt-btn');
                            const watchedLink = document.getElementById('link-trakt-watched');
                            const ratedLink = document.getElementById('link-trakt-rated');

                            if (displayName) displayName.textContent = data.profile.displayName;
                            if (userIdDisplay) userIdDisplay.textContent = data.profile.userId;
                            if (watchedCount) watchedCount.textContent = data.profile.watched;
                            if (ratedCount) ratedCount.textContent = data.profile.rated;
                            if (profileLink && data.profile.link) profileLink.href = data.profile.link;
                            if (avatar && data.profile.avatar) avatar.src = data.profile.avatar;

                            // Show logout button
                            if (logoutBtn) logoutBtn.style.display = 'inline-flex';

                            // Set stat links based on user ID
                            const userId = data.profile.userId;
                            if (userId) {
                                if (watchedLink) watchedLink.href = `https://trakt.tv/users/${userId}/history/movies`;
                                if (ratedLink) ratedLink.href = `https://trakt.tv/users/${userId}/ratings/movies`;
                            }
                        } else if (platform === 'letterboxd') {
                            const watchedCount = document.getElementById('letterboxd-watched-count');
                            const ratedCount = document.getElementById('letterboxd-rated-count');

                            if (watchedCount) watchedCount.textContent = data.profile.watched;
                            if (ratedCount) ratedCount.textContent = data.profile.rated;
                        }
                    }
                });
            }

            log('📦 已恢复会话状态', 'info');
        } catch (e) {
            console.error('Failed to restore session state:', e);
            // Don't delete session data on error - just log it
            // The user can manually clear if needed
            log('⚠️ 部分会话状态恢复失败', 'info');
        }
    }

    // Handle sync complete events from cross-platform sync
    socket.on('sync_complete', (data) => {
        log(`✅ 同步完成: ${data.source} → ${data.target}`, 'success');
        setButtonsState(false);  // Re-enable buttons
        // Disable sync button again until next preview
        if (ui.syncBtn) ui.syncBtn.disabled = true;
    });

    // Handle preview complete - enable Execute button and show preview in UI
    socket.on('sync_preview_complete', (data) => {
        log(`📋 预览完成: ${data.count} 部电影待同步，点击"执行"开始同步`, 'success');
        setButtonsState(false);  // Re-enable buttons
        // Enable the sync (execute) button after preview
        if (ui.syncBtn) ui.syncBtn.disabled = false;

        // Render preview in the sync preview card
        if (data.movies && data.movies.length > 0) {
            renderSyncPreview(data.movies);
        }
    });

    // Platform timestamp clear buttons (using data-clear-ts attribute)
    document.querySelectorAll('[data-clear-ts]').forEach(btn => {
        btn.addEventListener('click', () => {
            const key = btn.dataset.clearTs;
            socket.emit('clear_sync_timestamp', { key });
            log(`🗑️ 正在清除 ${key} 时间戳...`, 'info');
        });
    });

    // Update platform timestamp display when config is loaded
    socket.on('config_loaded', (config) => {
        updatePlatformTimestampDisplay(config);
    });

    socket.on('sync_timestamp_cleared', (data) => {
        // Update display to show "未获取"
        const platform = data.key.replace('_latest_record_ts', '');
        const el = document.getElementById(`${platform}-latest-ts-display`);
        if (el) el.textContent = '未获取';
        log(`✅ ${platform} 时间戳已清除`, 'success');
    });

    function updatePlatformTimestampDisplay(config) {
        // Update each platform's timestamp display
        ['douban', 'imdb', 'trakt', 'tmdb'].forEach(platform => {
            const el = document.getElementById(`${platform}-latest-ts-display`);
            if (el) {
                const ts = config[`${platform}_latest_record_ts`];
                el.textContent = ts ? String(ts).substring(0, 10) : '未获取';
            }
        });
    }

    // Request config on load to display timestamps
    socket.emit('get_config', {});

    // Request unified library on load
    socket.emit('get_unified_library', { page: 1, page_size: 20, platform: 'all' });
});

// =============================================================================
// Unified Library View
// =============================================================================

// Modular platform config - easy to add new platforms
const PLATFORMS = {
    douban: { emoji: '🎬', name: '豆瓣', color: '#00aa77' },
    imdb: { emoji: '⭐', name: 'IMDB', color: '#f5c518' },
    trakt: { emoji: '🎯', name: 'Trakt', color: '#ed1c24' },
    letterboxd: { emoji: '🎞️', name: 'Letterboxd', color: '#ff8000' },
    tmdb: { emoji: '🎬', name: 'TMDB', color: '#01b4e4' }
};

let libraryState = {
    currentPage: 1,
    pageSize: 20,
    filter: 'all',
    totalPages: 0
};

function renderUnifiedLibrary(data) {
    console.log('[Library] renderUnifiedLibrary called, filter:', data.filter, 'movies:', data.movies?.length);
    const { movies, total_count, page, page_size, total_pages, platform_counts, filter } = data;

    libraryState.currentPage = page;
    libraryState.totalPages = total_pages;
    libraryState.filter = filter;

    // Update filter counts - use platform_counts for stable counts
    const countAll = document.getElementById('count-all');
    if (countAll) countAll.textContent = platform_counts.shared || 0;

    Object.keys(PLATFORMS).forEach(platform => {
        const countEl = document.getElementById(`count-${platform}`);
        if (countEl) countEl.textContent = platform_counts[platform] || 0;
    });

    // Update active filter tab
    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.filter === filter);
    });

    // Show/hide empty state
    const libraryEmpty = document.getElementById('library-empty');
    const libraryList = document.getElementById('library-list');
    const libraryPagination = document.getElementById('library-pagination');

    if (movies.length === 0) {
        if (libraryEmpty) libraryEmpty.style.display = 'block';
        if (libraryList) libraryList.style.display = 'none';
        if (libraryPagination) libraryPagination.style.display = 'none';
        return;
    }

    if (libraryEmpty) libraryEmpty.style.display = 'none';
    if (libraryList) libraryList.style.display = 'block';
    if (libraryPagination) libraryPagination.style.display = total_pages > 1 ? 'flex' : 'none';

    // Render movie list with rich metadata
    let html = '';
    movies.forEach(movie => {
        // Platform badges - next to title
        let platformBadgesHtml = '';

        const sourceCount = movie.sources ? movie.sources.length : 0;
        const isShared = sourceCount >= 2;

        const buildBadge = (platform, url, rating, votes, label, forceShow = false) => {
            // For shared movies: show all available platform links
            // For exclusive movies: only show the source platform
            if (!isShared && !movie.sources.includes(platform)) return '';
            // For shared movies, show if forceShow is true OR if platform is in sources
            if (isShared && !forceShow && !movie.sources.includes(platform)) return '';

            const voteText = votes ? formatVotes(votes) : '';
            return `
                <a href="${url}" target="_blank" class="badge-v3 ${platform}" title="${label}">
                    <span class="badge-logo">${label}</span>
                    <span class="badge-score">${rating || '↗'}</span>
                    ${voteText ? `<span class="badge-extra">${voteText}</span>` : ''}
                </a>`;
        }

        // IMDb
        if (movie.imdb_id || movie.imdb_url) {
            const url = movie.imdb_url || `https://www.imdb.com/title/${movie.imdb_id}/`;
            platformBadgesHtml += buildBadge('imdb', url, movie.imdb_rating, movie.imdb_votes, 'IMDb', true);
        }

        // Douban
        if (movie.douban_id || movie.douban_url) {
            const url = movie.douban_url || `https://movie.douban.com/subject/${movie.douban_id}/`;
            platformBadgesHtml += buildBadge('douban', url, movie.douban_rating, movie.douban_votes, '豆瓣', true);
        }

        // Trakt
        if (movie.trakt_id || movie.trakt_url || movie.sources.includes('trakt')) {
            const url = movie.trakt_url || '#';
            platformBadgesHtml += buildBadge('trakt', url, '', '', 'Trakt', true);
        }

        // Letterboxd - for shared movies, always show if we have imdb_id
        if (movie.letterboxd_url || (isShared && movie.imdb_id) || movie.sources.includes('letterboxd')) {
            const url = movie.letterboxd_url || `https://letterboxd.com/imdb/${movie.imdb_id}/`;
            platformBadgesHtml += buildBadge('letterboxd', url, '', '', 'LB', true);
        }

        // TMDB
        if (movie.tmdb_id || movie.tmdb_url) {
            const url = movie.tmdb_url || `https://www.themoviedb.org/movie/${movie.tmdb_id}`;
            platformBadgesHtml += buildBadge('tmdb', url, movie.tmdb_rating, '', 'TMDB', true);
        }

        // Cover image
        const posterUrl = movie.poster_url || '';
        const coverHtml = posterUrl
            ? `<div class="movie-cover-wrapper"><img class="movie-cover-large" src="${posterUrl}" alt="" loading="lazy" onerror="this.onerror=null; this.src=''; this.parentNode.classList.add('error');"></div>`
            : `<div class="movie-cover-wrapper"><div class="movie-cover-placeholder large">🎬</div></div>`;

        // User's rating and date
        const userRating = movie.rating ? `<div class="rating-main"><span class="rating-label">评分</span><span class="rating-value">${movie.rating}</span></div>` : '';
        const dateText = movie.date_rated || movie.latest_date || '';
        const dateDisplay = dateText ? `<div class="rating-date"><span class="date-label">最后操作于</span><span class="date-value">${dateText.substring(0, 10)}</span></div>` : '';

        html += `
            <div class="movie-item">
                ${coverHtml}
                <div class="movie-info">
                    <div class="movie-title-row">
                        <div class="movie-title">
                            ${movie.title || '未知标题'} <span class="movie-year">${movie.year || ''}</span>
                        </div>
                        <div class="platform-badges-inline">
                            ${platformBadgesHtml}
                        </div>
                    </div>
                    
                    <div class="movie-metadata-grid">
                        ${movie.directors ? `<div class="meta-item"><span class="meta-icon">🎬</span><span class="meta-text" title="${movie.directors}">${movie.directors}</span></div>` : ''}
                        ${movie.actors ? `<div class="meta-item"><span class="meta-icon">🎭</span><span class="meta-text" title="${movie.actors}">${movie.actors}</span></div>` : ''}
                        ${movie.genres ? `<div class="meta-item"><span class="meta-icon">🏷️</span><span class="meta-text">${movie.genres}</span></div>` : ''}
                        ${movie.runtime ? `<div class="meta-item"><span class="meta-icon">⏱️</span><span class="meta-text">${movie.runtime}</span></div>` : ''}
                    </div>

                    <div class="movie-bottom">
                        <div class="score-display">
                            ${userRating}
                            ${dateDisplay}
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    // Helper function to format vote counts
    function formatVotes(num) {
        if (!num) return '';
        const n = parseInt(num);
        if (n >= 10000) return (n / 10000).toFixed(1) + '万';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
        return n.toString();
    }

    if (libraryList) libraryList.innerHTML = html;

    // Update pagination
    const pageInfo = document.getElementById('lib-page-info');
    const prevBtn = document.getElementById('lib-prev-btn');
    const nextBtn = document.getElementById('lib-next-btn');

    if (pageInfo) pageInfo.textContent = `${page} / ${total_pages}`;
    if (prevBtn) prevBtn.disabled = page <= 1;
    if (nextBtn) nextBtn.disabled = page >= total_pages;
}

// Filter tab click handlers - use window.socket
document.addEventListener('DOMContentLoaded', function () {
    // Wait for socket to be ready
    const initFilterHandlers = () => {
        document.querySelectorAll('.filter-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                const filter = tab.dataset.filter;
                console.log('[Library] Filter clicked:', filter);
                libraryState.filter = filter;
                libraryState.currentPage = 1;

                // Update active state immediately
                document.querySelectorAll('.filter-tab').forEach(t => {
                    t.classList.toggle('active', t.dataset.filter === filter);
                });

                // Use fetch API instead of socket to bypass reconnection issues
                console.log('[Library] Fetching via API:', filter);
                fetch(`/api/library?page=1&page_size=${libraryState.pageSize}&platform=${filter}`)
                    .then(res => res.json())
                    .then(data => {
                        console.log('[Library] API response received:', data.filter, 'movies:', data.movies?.length);
                        renderUnifiedLibrary(data);
                    })
                    .catch(err => {
                        console.error('[Library] API fetch error:', err);
                    });
            });
        });

        // Pagination buttons
        const prevBtn = document.getElementById('lib-prev-btn');
        const nextBtn = document.getElementById('lib-next-btn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (libraryState.currentPage > 1 && window.socket) {
                    window.socket.emit('get_unified_library', {
                        page: libraryState.currentPage - 1,
                        page_size: libraryState.pageSize,
                        platform: libraryState.filter
                    });
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (libraryState.currentPage < libraryState.totalPages && window.socket) {
                    window.socket.emit('get_unified_library', {
                        page: libraryState.currentPage + 1,
                        page_size: libraryState.pageSize,
                        platform: libraryState.filter
                    });
                }
            });
        }

        console.log('[Library] Filter handlers initialized');

        // Register unified_library listener on window.socket to ensure same socket receives responses
        if (window.socket) {
            window.socket.on('unified_library', (data) => {
                console.log('[Library] window.socket received unified_library:', data.filter);
                renderUnifiedLibrary(data);
            });
        }
    };

    // Initialize after a small delay to ensure socket is ready
    setTimeout(initFilterHandlers, 100);
});
