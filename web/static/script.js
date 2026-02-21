/**
 * CineRecord Hub 2.0 - Main JavaScript
 * Dashboard interface with tabbed navigation
 */

const DEFAULT_DOWNLOAD_SITES = [
    { id: 'ptp', label: 'PTP', template: 'https://passthepopcorn.me/torrents.php?searchstr={imdbid}' },
    { id: 'kg', label: 'KG', template: 'https://karagarga.in/browse.php?search={imdbid}&search_type=imdb' },
    { id: 'hdroute', label: '路', template: 'http://hdroute.org/browse.php?dp=0&add=0&action=s&or=1&imdb={imdbno}' },
    { id: 'tik', label: 'Tik', template: 'https://www.cinematik.net/torrents?imdbid={imdbno}&perPage=25&imdbId={imdbno}' },
    { id: 'in', label: 'IN', template: 'https://nzbs.in/search?query=imdb:{imdbid}' },
    { id: 'hdb', label: 'HDB', template: 'https://hdbits.org/browse.php?search={imdbid}' },
    { id: 'i2', label: 'I2', template: 'https://nzbs.in/search?query={search_name}' },
    { id: 'imdb', label: 'IMDB', template: 'https://www.imdb.com/title/{imdbid}/' },
    { id: 'btn', label: '妞', template: 'https://broadcasthe.net/torrents.php?action=advanced&imdb={imdbid}' },
    { id: 'omg', label: 'OMG', template: 'https://omgwtfnzbs.org/browse?search={imdbid}&cat=default&sort=3' },
    { id: 'fl', label: 'FL', template: 'https://filelist.io/browse.php?search={imdbid}' },
    { id: 'bhd', label: 'BHD', template: 'https://beyond-hd.me/torrents?imdb={imdbid}' },
    { id: 'blu', label: 'BLU', template: 'https://blutopia.cc/torrents?imdbid={imdbno}&perPage=25&imdbId={imdbno}' },
    { id: 'cg', label: 'CG', template: 'http://cinemageddon.net/browse.php?search={imdbid}&proj=0&descr=1' },
    { id: 'mt', label: 'MT', template: 'https://kp.m-team.cc/browse?keyword={search_name}&search_area=4&search_mode=0' },
    { id: 'sc', label: 'SC', template: 'https://secret-cinema.pw/torrents.php?action=advanced&searchsubmit=1&filter_cat=1&cataloguenumber={imdbid}' },
    { id: 'ttg', label: '套', template: 'https://totheglory.im/browse.php?search_field=imdb{imdbno}&c=M' },
    { id: 'nc', label: 'nC', template: 'https://ncore.pro/torrents.php?mire={imdbid}&miben=imdb&tipus=all_own' },
    { id: 'hdt', label: 'HDT', template: 'https://hd-torrents.org/torrents.php?&search={imdbid}&active=0' },
    { id: 'douban', label: '豆', template: 'https://search.douban.com/movie/subject_search?search_text={imdbid}' },
    { id: 'zmk', label: 'ZMK', template: 'http://so.zimuku.org/search?q={imdbid}' },
    { id: 'op', label: 'OP', template: 'https://www.opensubtitles.org/en/search2/sublanguageid-eng/moviename-{search_name}' },
    { id: 'sh', label: 'SH', template: 'https://subhd.tv/search/{imdbid}' },
    { id: 'ops', label: 'OPS', template: 'https://orpheus.network/torrents.php?searchstr={search_name}' },
    { id: 'bm', label: 'BM', template: 'https://www.blu-ray.com/search/?quicksearch=1&quicksearch_country=all&quicksearch_keyword={search_name}&section=bluraymovies' },
    { id: 'lb', label: 'LB', template: 'https://letterboxd.com/imdb/{imdbid}' },
    { id: 'of', label: 'OF', template: 'https://www.ofdb.de/suchergebnis/?{search_name}' },
    { id: 'az', label: 'AZ', template: 'https://avistaz.to/torrents?in=1&search={search_name}' },
    { id: 'tb', label: 'TB', template: 'https://thetvdb.com/search?query={search_name}' },
    { id: 'ade', label: 'ADE', template: 'https://audiences.me/torrents.php?incldead=0&spstate=0&inclbookmarked=0&search={imdbid}&search_area=4&search_mode=0' }
];

const downloadSiteState = {
    enabledIds: new Set(),
    customSites: []
};

let downloadSitesInitialized = false;
let downloadSiteSaveTimer = null;

function normalizeImdbId(rawValue) {
    if (!rawValue) return '';
    const value = String(rawValue).trim();
    if (!value) return '';
    if (value.startsWith('tt')) return value;
    if (/^\d+$/.test(value)) return `tt${value}`;
    return value;
}

function buildDownloadSiteUrl(template, tokens) {
    if (!template) return '';
    let url = template;
    if (url.includes('{imdbid}')) {
        if (!tokens.imdbid) return '';
        url = url.split('{imdbid}').join(encodeURIComponent(tokens.imdbid));
    }
    if (url.includes('{imdbno}')) {
        if (!tokens.imdbno) return '';
        url = url.split('{imdbno}').join(encodeURIComponent(tokens.imdbno));
    }
    if (url.includes('{search_name}')) {
        if (!tokens.search_name) return '';
        url = url.split('{search_name}').join(encodeURIComponent(tokens.search_name));
    }
    return url;
}

function getDownloadTokens(movie) {
    const rawImdb = movie.Const || movie.imdb_id || movie['IMDb ID'] || movie['IMDB ID'] || '';
    const imdbid = normalizeImdbId(rawImdb);
    const imdbno = imdbid.startsWith('tt') ? imdbid.slice(2) : (/^\d+$/.test(imdbid) ? imdbid : '');
    const title = movie.Title || movie.title || '';
    const year = movie.Year || movie.year || '';
    const search_name = [title, year].filter(Boolean).join(' ').trim();

    return { imdbid, imdbno, search_name };
}

function getActiveDownloadSites() {
    const enabledDefaults = DEFAULT_DOWNLOAD_SITES.filter(site => downloadSiteState.enabledIds.has(site.id));
    const enabledCustoms = Array.isArray(downloadSiteState.customSites)
        ? downloadSiteState.customSites.filter(site => site.label && site.template && site.enabled !== false)
        : [];
    return [...enabledDefaults, ...enabledCustoms];
}

function buildDownloadSiteLinks(movie) {
    const tokens = getDownloadTokens(movie);
    const activeSites = getActiveDownloadSites();
    return activeSites.map(site => {
        const url = buildDownloadSiteUrl(site.template, tokens);
        if (!url) return null;
        return { label: site.label, url };
    }).filter(Boolean);
}

function renderDownloadSiteSettings() {
    const grid = document.getElementById('download-sites-default');
    if (!grid) return;

    let html = '';

    // Render Default Sites
    const activeDefaults = DEFAULT_DOWNLOAD_SITES.filter(site => !downloadSiteState.deletedDefaults?.has(site.id));
    activeDefaults.forEach(site => {
        html += `
            <label class="download-site-item" style="position: relative; padding-right: 32px;">
                <input type="checkbox" class="site-checkbox" data-type="default" data-site-id="${site.id}" ${downloadSiteState.enabledIds.has(site.id) ? 'checked' : ''}>
                <div class="download-site-info">
                    <span class="download-site-name">${site.label}</span>
                    <span class="download-site-template" title="${site.template}">${site.template}</span>
                </div>
                <button type="button" class="delete-site-btn btn-ghost" data-type="default" data-id="${site.id}" style="position: absolute; top: 8px; right: 8px; border: none; font-size: 16px; padding: 0 4px; line-height: 1;" title="删除">✕</button>
            </label>
        `;
    });

    // Render Custom Sites
    if (Array.isArray(downloadSiteState.customSites)) {
        downloadSiteState.customSites.forEach((site, index) => {
            html += `
                <label class="download-site-item custom" style="position: relative; padding-right: 32px; border-color: rgba(var(--accent-rgb), 0.5); background: rgba(var(--accent-rgb), 0.05);">
                    <input type="checkbox" class="site-checkbox" data-type="custom" data-index="${index}" ${site.enabled !== false ? 'checked' : ''}>
                    <div class="download-site-info">
                        <span class="download-site-name">${site.label}</span>
                        <span class="download-site-template" title="${site.template}">${site.template}</span>
                    </div>
                    <button type="button" class="delete-site-btn btn-ghost" data-type="custom" data-index="${index}" style="position: absolute; top: 8px; right: 8px; border: none; font-size: 16px; padding: 0 4px; line-height: 1;" title="删除">✕</button>
                </label>
            `;
        });
    }

    grid.innerHTML = html;

    // Attach listeners for delete buttons
    grid.querySelectorAll('.delete-site-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault(); // Stop checkbox toggle
            e.stopPropagation();
            if (!confirm('确定要删除此站点吗？')) return;

            const type = btn.getAttribute('data-type');
            if (type === 'default') {
                const id = btn.getAttribute('data-id');
                if (!downloadSiteState.deletedDefaults) {
                    downloadSiteState.deletedDefaults = new Set();
                }
                downloadSiteState.deletedDefaults.add(id);
                downloadSiteState.enabledIds.delete(id);
            } else if (type === 'custom') {
                const index = parseInt(btn.getAttribute('data-index'), 10);
                downloadSiteState.customSites.splice(index, 1);
            }
            syncDownloadSiteStateFromUI({ persist: true });
            renderDownloadSiteSettings();
        });
    });

    // Attach listeners for checkboxes validation update
    grid.querySelectorAll('.site-checkbox').forEach(cb => {
        cb.addEventListener('change', () => {
            syncDownloadSiteStateFromUI({ persist: true });
        });
    });
}

function filterDownloadSites(query) {
    const normalized = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('#download-sites-default .download-site-item');

    items.forEach(item => {
        const name = item.querySelector('.download-site-name')?.textContent || '';
        const template = item.querySelector('.download-site-template')?.textContent || '';
        const matches = !normalized ||
            name.toLowerCase().includes(normalized) ||
            template.toLowerCase().includes(normalized);
        item.style.display = matches ? '' : 'none';
    });
}

function initDownloadSiteSettings(config) {
    const defaultContainer = document.getElementById('download-sites-default');
    if (!defaultContainer) return;

    const enabled = Array.isArray(config.download_sites_enabled) ? config.download_sites_enabled : [];
    downloadSiteState.enabledIds = new Set(enabled);
    downloadSiteState.customSites = Array.isArray(config.download_sites_custom) ? config.download_sites_custom : [];
    downloadSiteState.deletedDefaults = new Set(Array.isArray(config.download_sites_deleted) ? config.download_sites_deleted : []);

    renderDownloadSiteSettings();

    if (!downloadSitesInitialized) {
        const addBtn = document.getElementById('add-custom-site-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                const nameInput = document.getElementById('new-custom-site-name');
                const templateInput = document.getElementById('new-custom-site-template');
                const label = nameInput?.value.trim() || '';
                const template = templateInput?.value.trim() || '';
                if (label && template) {
                    downloadSiteState.customSites.push({ label, template, enabled: true });
                    if (nameInput) nameInput.value = '';
                    if (templateInput) templateInput.value = '';
                    syncDownloadSiteStateFromUI({ persist: true });
                    renderDownloadSiteSettings();
                } else {
                    log('⚠️ 请填写站点名称和链接模板', 'warning');
                }
            });
        }

        // Add site search filter
        const siteSearchInput = document.getElementById('download-site-search');
        if (siteSearchInput) {
            siteSearchInput.addEventListener('input', (e) => {
                filterDownloadSites(e.target.value);
            });
        }

        downloadSitesInitialized = true;
    }
}

function collectDownloadSiteConfig() {
    const enabledIds = Array.from(
        document.querySelectorAll('#download-sites-default .site-checkbox[data-type="default"]:checked')
    ).map(cb => cb.dataset.siteId);

    // Update custom sites enabled status based on DOM, but keep label/template from state
    const customSites = [];
    document.querySelectorAll('#download-sites-default .site-checkbox[data-type="custom"]').forEach(cb => {
        const index = parseInt(cb.dataset.index, 10);
        const site = downloadSiteState.customSites[index];
        if (site) {
            customSites.push({
                label: site.label,
                template: site.template,
                enabled: cb.checked
            });
        }
    });

    return {
        enabledIds,
        customSites,
        deletedDefaults: Array.from(downloadSiteState.deletedDefaults || [])
    };
}

function syncDownloadSiteStateFromUI({ persist = false } = {}) {
    const config = collectDownloadSiteConfig();
    downloadSiteState.enabledIds = new Set(config.enabledIds);
    downloadSiteState.customSites = config.customSites;
    // deletedDefaults does not change from UI checkboxes so no need to redefine here

    if (typeof wishlistState !== 'undefined' && wishlistState.items.length > 0) {
        renderWishlistPage(wishlistState.currentPage);
    }

    if (persist) {
        if (downloadSiteSaveTimer) clearTimeout(downloadSiteSaveTimer);
        downloadSiteSaveTimer = setTimeout(() => {
            const saveConfig = () => {
                if (!window.socket) { setTimeout(saveConfig, 100); return; }
                window.socket.emit('save_config', {
                    download_sites_enabled: config.enabledIds,
                    download_sites_custom: config.customSites,
                    download_sites_deleted: config.deletedDefaults
                });
            };
            saveConfig();
        }, 400);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    window.socket = socket; // Expose for debugging

    socket.on('connect', () => {
        console.log('[Socket] Connected with ID:', socket.id);
    });

    // Initialize i18n system
    if (typeof i18n !== 'undefined') {
        i18n.init();

        // Connect language button
        const langBtn = document.getElementById('lang-btn');
        if (langBtn) {
            langBtn.addEventListener('click', () => i18n.toggleLanguage());
        }
    }

    // Theme Manager
    class ThemeManager {
        constructor() {
            this.themeBtn = document.getElementById('theme-btn');
            this.currentTheme = localStorage.getItem('theme') || 'dark';
            this.init();
        }

        init() {
            this.applyTheme(this.currentTheme);
            if (this.themeBtn) {
                this.themeBtn.addEventListener('click', () => this.toggleTheme());
            }
        }

        toggleTheme() {
            this.currentTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('theme', this.currentTheme);
            this.applyTheme(this.currentTheme);
        }

        applyTheme(theme) {
            if (theme === 'light') {
                document.body.classList.add('light-mode');
                if (this.themeBtn) this.themeBtn.innerText = '☀️';
            } else {
                document.body.classList.remove('light-mode');
                if (this.themeBtn) this.themeBtn.innerText = '🌙';
            }
        }
    }

    // Initialize Managers
    new ThemeManager();

    // Global constants for other scripts - use official logos
    window.platformIcons = {
        'douban': '<img src="/static/images/platforms/douban.png" alt="豆瓣" style="width:20px;height:20px;vertical-align:middle;border-radius:3px;">',
        'imdb': '<img src="/static/images/platforms/imdb.svg" alt="IMDB" style="width:20px;height:20px;vertical-align:middle;border-radius:3px;">',
        'trakt': '<img src="/static/images/platforms/trakt.png" alt="Trakt" style="width:20px;height:20px;vertical-align:middle;border-radius:3px;">',
        'tmdb': '<img src="/static/images/platforms/tmdb.png" alt="TMDB" style="width:20px;height:20px;vertical-align:middle;border-radius:3px;">',
        'letterboxd': '<img src="/static/images/platforms/letterboxd.png" alt="Letterboxd" style="width:20px;height:20px;vertical-align:middle;border-radius:3px;">'
    };
    // Keep emoji fallback for compatibility
    window.platformEmoji = {
        'douban': '🎬',
        'imdb': '⭐',
        'trakt': '🎯',
        'tmdb': '🎬',
        'letterboxd': '🎞️'
    };

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
        saveSettingsBtn: document.getElementById('save-settings-btn'),
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

        // Progress (enhanced)
        progressCard: document.getElementById('progress-card'),
        progressStepText: document.getElementById('progress-step-text'),
        progressPercent: document.getElementById('progress-percent'),
        progressBar: document.getElementById('progress-bar-fill'),
        progressCurrent: document.getElementById('progress-current'),
        progressTotal: document.getElementById('progress-total'),

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
    const TAB_ALIASES = {
        accounts: 'settings',
        account: 'settings',
        backups: 'settings',
        config: 'settings'
    };

    const TAB_GROUPS = {
        dashboard: ['tab-dashboard'],
        data: ['tab-data'],
        sync: ['tab-sync'],
        wishlist: ['tab-wishlist']
    };

    let currentSettingsSection = 'tab-settings';

    function normalizeTabId(tabId) {
        if (!tabId) return 'dashboard';
        const normalized = String(tabId).toLowerCase().trim();
        return TAB_ALIASES[normalized] || normalized;
    }

    // Navigation Tabs Logic (Shared. Handles both top-nav and bottom-nav)
    ui.navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            switchTab(tabId);
        });
    });

    function showSettingsSection(targetId) {
        const settingsTargets = ['tab-settings', 'tab-backups', 'tab-config'];
        const normalizedTarget = settingsTargets.includes(targetId) ? targetId : 'tab-settings';
        settingsTargets.forEach(id => document.getElementById(id)?.classList.remove('active'));
        document.getElementById(normalizedTarget)?.classList.add('active');
        currentSettingsSection = normalizedTarget;

        document.querySelectorAll('.settings-sub-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.settingsTarget === normalizedTarget);
        });

        // Lazy init for backups when the section is shown
        if (normalizedTarget === 'tab-backups') {
            loadMyFilesList();
            initBackupSubTabs();
        }
    }

    function openSettingsSection(targetId) {
        currentSettingsSection = targetId || 'tab-settings';
        switchTab('settings');
    }

    // Mobile Hamburger Menu Logic
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const mobileOverlay = document.getElementById('mobile-sidebar-overlay');
    const mainSidebar = document.getElementById('main-layout-sidebar');

    function closeMobileSidebar() {
        if (mainSidebar && mainSidebar.classList.contains('open')) {
            mainSidebar.classList.remove('open');
            if (mobileOverlay) mobileOverlay.classList.remove('visible');
        }
    }

    if (mobileMenuBtn && mobileOverlay && mainSidebar) {
        mobileMenuBtn.addEventListener('click', () => {
            const isOpen = mainSidebar.classList.contains('open');
            if (isOpen) {
                closeMobileSidebar();
            } else {
                mainSidebar.classList.add('open');
                mobileOverlay.classList.add('visible');
            }
        });

        mobileOverlay.addEventListener('click', () => {
            closeMobileSidebar();
        });
    }

    function switchTab(tabId) {
        const rawTab = String(tabId || '').toLowerCase().trim();
        if (rawTab === 'backups') currentSettingsSection = 'tab-backups';
        if (rawTab === 'config') currentSettingsSection = 'tab-config';
        if (rawTab === 'accounts' || rawTab === 'account') currentSettingsSection = 'tab-settings';

        let normalized = normalizeTabId(tabId);
        let targets = TAB_GROUPS[normalized] || [`tab-${normalized}`];
        const hasTarget = targets.some(targetId => document.getElementById(targetId));
        if (!hasTarget && normalized !== 'settings') {
            normalized = 'dashboard';
            targets = TAB_GROUPS[normalized];
        }

        // Update ALL nav tabs (both top and bottom nav)
        ui.navTabs.forEach(t => {
            if (t.dataset.tab === normalized) {
                t.classList.add('active');
            } else {
                t.classList.remove('active');
            }
        });

        // Update content panes
        ui.tabContents.forEach(content => content.classList.remove('active'));

        if (normalized === 'settings') {
            showSettingsSection(currentSettingsSection);
        } else {
            targets.forEach(targetId => {
                document.getElementById(targetId)?.classList.add('active');
            });
        }

        // Close mobile sidebar if open when switching tabs
        closeMobileSidebar();

        // Load data for dynamic tabs
        if (normalized === 'wishlist') {
            loadWishlistLibrary();
            updateWishlistViewToggle();
        }

        // Save session state when tab changes
        saveSessionState();
    }

    function initSettingsSubTabs() {
        document.querySelectorAll('.settings-sub-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.dataset.settingsTarget;
                if (target) {
                    openSettingsSection(target);
                }
            });
        });
    }

    initSettingsSubTabs();
    window.switchTab = switchTab;
    window.openSettingsSection = openSettingsSection;


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

        const mediaServerUrl = document.getElementById('media-server-url');
        const mediaServerApiKey = document.getElementById('media-server-api-key');
        if (mediaServerUrl) mediaServerUrl.value = config.media_server_url || '';
        if (mediaServerApiKey) mediaServerApiKey.value = config.media_server_api_key || '';
        const serverUsername = document.getElementById('server-username');
        const serverPassword = document.getElementById('server-password');
        if (serverUsername) serverUsername.value = config.server_username || 'cinerecord';
        if (serverPassword && config.server_password) serverPassword.value = config.server_password;
        const cinepersonaUrl = document.getElementById('cinepersona-url');
        const cinepersonaBaseUrl = document.getElementById('cinepersona-base-url');
        const cinepersonaApiKey = document.getElementById('cinepersona-api-key');
        const cinepersonaCookie = document.getElementById('cinepersona-session-cookie');
        const cinepersonaConsent = document.getElementById('cinepersona-consent');
        const cinepersonaAutoSync = document.getElementById('cinepersona-auto-sync');
        // Legacy field still present for backward compat
        if (cinepersonaUrl) cinepersonaUrl.value = config.cinepersona_url || '';
        // New API-key-based fields
        if (cinepersonaBaseUrl) cinepersonaBaseUrl.value = config.cinepersona_base_url || 'https://film.133339.xyz';
        if (cinepersonaApiKey && config.cinepersona_api_key) cinepersonaApiKey.value = config.cinepersona_api_key;
        if (cinepersonaCookie && config.cinepersona_session_cookie) cinepersonaCookie.value = config.cinepersona_session_cookie;
        if (cinepersonaConsent) cinepersonaConsent.checked = !!config.cinepersona_consent;
        if (cinepersonaAutoSync) cinepersonaAutoSync.checked = !!config.cinepersona_auto_sync;

        const cpBase = (config.cinepersona_base_url || config.cinepersona_url || 'https://film.133339.xyz').replace(/\/+$/, '');
        const cinepersonaLink = document.getElementById('cinepersona-link');
        const cinepersonaImportLink = document.getElementById('cinepersona-import-link');
        const cinepersonaLinkSettings = document.getElementById('cinepersona-link-settings');
        const cinepersonaImportLinkSettings = document.getElementById('cinepersona-import-link-settings');
        if (cinepersonaLink) cinepersonaLink.href = cpBase;
        if (cinepersonaImportLink) cinepersonaImportLink.href = `${cpBase}/import`;
        if (cinepersonaLinkSettings) cinepersonaLinkSettings.href = cpBase;
        if (cinepersonaImportLinkSettings) cinepersonaImportLinkSettings.href = `${cpBase}/import`;

        // Populate platform card inputs
        const cpCardBase = document.getElementById('cp-card-base-url');
        const cpCardKey = document.getElementById('cp-card-api-key');
        if (cpCardBase) cpCardBase.value = cpBase;
        if (cpCardKey && config.cinepersona_api_key) cpCardKey.value = config.cinepersona_api_key;

        // If API key already configured, show connected state with stored info
        if (config.cinepersona_api_key) {
            _setCpConnected({
                username: config.cinepersona_username || '',
                email: config.cinepersona_email || ''
            });
        }

        // Sidebar stats: count local merged data
        const cpStatEl = document.getElementById('cinepersona-summary-stats');
        if (cpStatEl) {
            const localCount = (appState.merged_count || 0);
            cpStatEl.textContent = localCount ? `${localCount} 部` : '--';
        }

        // Profile link
        const cpProfileLink = document.getElementById('cp-profile-link');
        if (cpProfileLink) cpProfileLink.href = cpBase;

        // Check for existing data files
        socket.emit('check_local_data', config);
        // Request session check from backend
        socket.emit('check_session', {});
        // Update connection status
        updateAuthStatus();
        // Update button states based on config
        updateButtonsBasedOnConnection();

        initDownloadSiteSettings(config);

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

    // CinePersona Export & Import Logic
    const cinepersonaExportBtn = document.getElementById('cinepersona-export-import-btn');
    if (cinepersonaExportBtn) {
        cinepersonaExportBtn.addEventListener('click', () => {
            const cpUrl = document.getElementById('cinepersona-url')?.value || 'https://film.133339.xyz';
            const cpBase = cpUrl.replace(/\/+$/, '');

            // Trigger download
            const exportUrl = `/download/merged?format=cinepersona`;
            const a = document.createElement('a');
            a.href = exportUrl;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            log('✅ 已为您生成并下载合并数据包，即将前往导入页', 'success');

            // Open import page after 1.5 seconds to ensure download starts
            setTimeout(() => {
                window.open(`${cpBase}/import`, '_blank');
            }, 1500);
        });
    }

    // ============================================================
    // CinePersona Platform Card Controls
    // ============================================================

    // Read API key from card input (primary) or settings input (fallback)
    function getCinepersonaApiKey() {
        return document.getElementById('cp-card-api-key')?.value
            || document.getElementById('cinepersona-api-key')?.value
            || '';
    }
    function getCinepersonaBaseUrl() {
        return (document.getElementById('cp-card-base-url')?.value
            || document.getElementById('cinepersona-base-url')?.value
            || 'https://film.133339.xyz').replace(/\/+$/, '');
    }

    function _setCpConnected(info) {
        const badge = document.getElementById('cinepersona-status-badge');
        const dot = document.getElementById('cinepersona-status-dot');
        const notConn = document.getElementById('cinepersona-not-connected');
        const conn = document.getElementById('cinepersona-connected');
        if (badge) { badge.className = 'status-badge connected'; badge.textContent = '● 已连接'; }
        if (dot) { dot.className = 'status-dot connected'; }
        if (notConn) notConn.style.display = 'none';
        if (conn) conn.style.display = '';
        if (info?.username) {
            const el = document.getElementById('cp-display-name');
            if (el) el.textContent = info.username;
        }
        if (info?.email) {
            const el = document.getElementById('cp-email-display');
            if (el) el.textContent = info.email;
        }
        ['push-cp-btn', 'pull-cp-watchlist-btn', 'cp-trakt-connect-btn2', 'logout-cp-btn'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = '';
        });
        // Sync card description update
        const syncDesc = document.querySelector('#cp-sync-btn')?.parentElement?.previousElementSibling?.querySelector('span');
        if (syncDesc) syncDesc.textContent = `已连接 CinePersona，点击推送本地全部数据`;
    }

    function _setCpDisconnected() {
        const badge = document.getElementById('cinepersona-status-badge');
        const dot = document.getElementById('cinepersona-status-dot');
        const notConn = document.getElementById('cinepersona-not-connected');
        const conn = document.getElementById('cinepersona-connected');
        if (badge) { badge.className = 'status-badge disconnected'; badge.textContent = '● 未连接'; }
        if (dot) { dot.className = 'status-dot disconnected'; }
        if (notConn) notConn.style.display = '';
        if (conn) conn.style.display = 'none';
        ['push-cp-btn', 'pull-cp-watchlist-btn', 'cp-trakt-connect-btn2', 'logout-cp-btn'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
    }

    // test-cp-btn: test connection + auto-save on success
    document.getElementById('test-cp-btn')?.addEventListener('click', () => {
        const apiKey = getCinepersonaApiKey();
        const baseUrl = getCinepersonaBaseUrl();
        if (!apiKey) { log('⚠️ 请先填入 API Key', 'warning'); return; }
        const btn = document.getElementById('test-cp-btn');
        if (btn) { btn.disabled = true; btn.textContent = '测试中…'; }
        socket.emit('test_cinepersona', { base_url: baseUrl, api_key: apiKey });
    });

    // Old settings test button (still in settings system tab)
    const cpTestBtn = document.getElementById('cinepersona-test-btn');
    if (cpTestBtn) {
        cpTestBtn.addEventListener('click', () => {
            const apiKey = document.getElementById('cinepersona-api-key')?.value || '';
            const baseUrl = (document.getElementById('cinepersona-base-url')?.value || 'https://film.133339.xyz').replace(/\/+$/, '');
            if (!apiKey) { log('⚠️ 请先填入 CinePersona API Key', 'warning'); return; }
            cpTestBtn.disabled = true; cpTestBtn.textContent = '测试中…';
            socket.emit('test_cinepersona', { base_url: baseUrl, api_key: apiKey });
        });
    }

    socket.on('cinepersona_test_result', (data) => {
        // Restore test buttons
        const btn = document.getElementById('test-cp-btn');
        if (btn) { btn.disabled = false; btn.textContent = '✅ 测试连接'; }
        if (cpTestBtn) { cpTestBtn.disabled = false; cpTestBtn.textContent = '测试连接'; }

        // Old settings result row
        const row = document.getElementById('cinepersona-test-result-row');
        const el = document.getElementById('cinepersona-test-result');
        if (el && row) {
            row.style.display = '';
            el.style.background = data.ok ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)';
            el.style.color = data.ok ? '#4ade80' : '#f87171';
            el.textContent = data.ok
                ? `✅ 已连接：${data.username || ''} ${data.email ? '(' + data.email + ')' : ''}`
                : `❌ 连接失败：${data.error || '未知错误'}`;
        }

        if (data.ok) {
            _setCpConnected(data);
            log(`✅ CinePersona 连接成功：${data.username || ''}`, 'success');
            // Also sync inputs to settings fields
            const apiKey = getCinepersonaApiKey();
            const baseUrl = getCinepersonaBaseUrl();
            const settingsKey = document.getElementById('cinepersona-api-key');
            const settingsBase = document.getElementById('cinepersona-base-url');
            if (settingsKey && apiKey) settingsKey.value = apiKey;
            if (settingsBase && baseUrl) settingsBase.value = baseUrl;
        } else {
            log(`❌ CinePersona 连接失败：${data.error || ''}`, 'error');
        }
    });

    // logout-cp-btn
    document.getElementById('logout-cp-btn')?.addEventListener('click', () => {
        _setCpDisconnected();
        const cpCardKey = document.getElementById('cp-card-api-key');
        if (cpCardKey) cpCardKey.value = '';
        log('🔌 已断开 CinePersona 连接', 'info');
    });

    // Sync to CinePersona button (sync page)
    const cpSyncBtn = document.getElementById('cp-sync-btn');
    if (cpSyncBtn) {
        cpSyncBtn.addEventListener('click', () => {
            const apiKey = getCinepersonaApiKey();
            const baseUrl = getCinepersonaBaseUrl();
            if (!apiKey) {
                log('⚠️ 请先在账户页配置 CinePersona API Key 并测试连接', 'warning');
                openSettingsSection('tab-settings'); return;
            }
            cpSyncBtn.disabled = true;
            const statusEl = document.getElementById('cp-sync-status');
            if (statusEl) statusEl.textContent = '⏳ 正在准备数据…';
            socket.emit('sync_to_cinepersona', { base_url: baseUrl, api_key: apiKey });
        });
    }
    socket.on('cinepersona_sync_done', (data) => {
        if (cpSyncBtn) cpSyncBtn.disabled = false;
        const statusEl = document.getElementById('cp-sync-status');
        if (statusEl) statusEl.textContent = data.message || '';
        const cpLocalCount = document.getElementById('cp-local-count');
        if (cpLocalCount && data.synced) cpLocalCount.textContent = data.synced;
    });

    // push-cp-btn (accounts card)
    document.getElementById('push-cp-btn')?.addEventListener('click', () => {
        const apiKey = getCinepersonaApiKey();
        const baseUrl = getCinepersonaBaseUrl();
        if (!apiKey) { log('⚠️ 未配置 API Key', 'warning'); return; }
        const btn = document.getElementById('push-cp-btn');
        if (btn) { btn.disabled = true; btn.textContent = '推送中…'; }
        log('🚀 开始推送数据库到 CinePersona…', 'info');
        socket.emit('sync_to_cinepersona', { base_url: baseUrl, api_key: apiKey });
        socket.once('cinepersona_sync_done', () => {
            if (btn) { btn.disabled = false; btn.textContent = '🚀 推送数据库'; }
        });
    });

    // Trakt Bridge buttons
    document.getElementById('cp-trakt-connect-btn')?.addEventListener('click', () => {
        const apiKey = getCinepersonaApiKey();
        const baseUrl = getCinepersonaBaseUrl();
        if (!apiKey) { log('⚠️ 请先配置 CinePersona API Key', 'warning'); return; }
        socket.emit('cinepersona_trakt_connect', { base_url: baseUrl, api_key: apiKey });
    });
    document.getElementById('cp-trakt-connect-btn2')?.addEventListener('click', () => {
        const apiKey = getCinepersonaApiKey();
        const baseUrl = getCinepersonaBaseUrl();
        if (!apiKey) { log('⚠️ 请先配置 CinePersona API Key', 'warning'); return; }
        socket.emit('cinepersona_trakt_connect', { base_url: baseUrl, api_key: apiKey });
    });
    socket.on('cinepersona_trakt_url', (data) => {
        if (data.url) window.open(data.url, '_blank');
        else log(`❌ 获取 Trakt 授权链接失败：${data.error || ''}`, 'error');
    });

    document.getElementById('cp-trakt-status-btn')?.addEventListener('click', () => {
        const apiKey = getCinepersonaApiKey();
        const baseUrl = getCinepersonaBaseUrl();
        if (!apiKey) { log('⚠️ 请先配置 CinePersona API Key', 'warning'); return; }
        socket.emit('cinepersona_trakt_status', { base_url: baseUrl, api_key: apiKey });
    });
    socket.on('cinepersona_trakt_status_result', (data) => {
        if (data.connected) log(`✅ CinePersona Trakt 已连接：${data.username || ''}`, 'success');
        else log(`ℹ️ Trakt 尚未连接到 CinePersona：${data.message || ''}`, 'info');
    });

    document.getElementById('cp-trakt-sync-btn')?.addEventListener('click', () => {
        const apiKey = getCinepersonaApiKey();
        const baseUrl = getCinepersonaBaseUrl();
        if (!apiKey) { log('⚠️ 请先配置 CinePersona API Key', 'warning'); return; }
        socket.emit('cinepersona_trakt_sync', { base_url: baseUrl, api_key: apiKey });
    });

    socket.on('log', (data) => log(data.message, data.type));
    socket.on('progress', (data) => updateProgress(data));
    socket.on('fetch_complete', (data) => {
        handleFetchComplete(data);
        // Refresh unified library after any fetch
        refreshLibrary(1);
    });
    socket.on('page_data', (data) => handlePageData(data));  // Pagination handler
    socket.on('merged_data_preview', (data) => renderMergedDataPreview(data));
    socket.on('sync_preview', (data) => renderSyncPreview(data.movies));
    socket.on('sync_item_failed', (data) => renderFailedItem(data));
    socket.on('sync_unrated', (data) => renderUnratedMovies(data));
    socket.on('finished', () => handleTaskFinished('sync'));

    // Letterboxd upload complete handler
    socket.on('letterboxd_upload_complete', (data) => {
        // Update appState
        appState.letterboxd_ready = true;
        appState.letterboxd_count = data.total_count || 0;
        appState.letterboxd_rated = data.rated_count || 0;
        appState.letterboxd_data = data.sample || [];

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
        if (statusText) {
            statusText.textContent = window.i18n ? window.i18n.t('trakt.waiting_auth') : '等待授权中...';
        }

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
            if (statusText) {
                statusText.textContent = window.i18n ? window.i18n.t('trakt.waiting_auth') : '等待授权中...';
            }
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
                    else if (platform === 'letterboxd') countEl = document.getElementById('letterboxd-summary-stats');
                    else if (platform === 'tmdb') countEl = document.getElementById('tmdb-summary-stats');

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
            // log(`✅ ${platform.toUpperCase()} 验证成功`, 'success');

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
        const sidebarId = document.getElementById('trakt-sidebar-id');
        const sidebarStats = document.getElementById('trakt-summary-stats');

        if (notConnected) notConnected.style.display = 'block';
        if (connected) connected.style.display = 'none';
        if (statusBadge) {
            statusBadge.textContent = '● 未连接';
            statusBadge.className = 'status-badge disconnected';
        }
        if (sidebarDot) sidebarDot.className = 'status-dot disconnected';
        if (sidebarId) sidebarId.textContent = '';
        if (sidebarStats) sidebarStats.textContent = '--';
    }

    // Helper: Update TMDB connected state
    function updateTMDBConnectedState(account) {
        const statusBadge = document.getElementById('tmdb-status-badge');
        const displayName = document.getElementById('tmdb-display-name');
        const sidebarId = document.getElementById('tmdb-sidebar-id');
        const statusDot = document.getElementById('tmdb-status-dot');
        const sidebarStats = document.getElementById('tmdb-summary-stats');
        const notConnected = document.getElementById('tmdb-not-connected');
        const connected = document.getElementById('tmdb-connected');
        const ratedCount = document.getElementById('tmdb-rated-count');
        const watchlistCount = document.getElementById('tmdb-watchlist-count');
        const avatarEl = document.getElementById('tmdb-avatar');

        if (statusBadge) {
            statusBadge.textContent = '● 已授权';
            statusBadge.className = 'status-badge connected';
        }
        if (notConnected) notConnected.style.display = 'none';
        if (connected) connected.style.display = 'block';
        if (displayName && account?.username) displayName.textContent = account.username;
        if (sidebarId && account?.username) sidebarId.textContent = account.username;
        if (statusDot) statusDot.className = 'status-dot connected';
        if (sidebarStats) sidebarStats.textContent = account?.rated_count ? `${account.rated_count} 部` : '--';
        if (ratedCount) ratedCount.textContent = account?.rated_count || '0';
        if (watchlistCount) watchlistCount.textContent = account?.watchlist_count || '0';
        if (avatarEl) {
            if (account?.avatar) {
                avatarEl.src = proxyAvatarUrl(account.avatar);
                avatarEl.style.display = 'block';
            } else {
                avatarEl.removeAttribute('src');
                avatarEl.style.display = 'none';
            }
        }

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
        const sidebarId = document.getElementById('tmdb-sidebar-id');
        const sidebarStats = document.getElementById('tmdb-summary-stats');

        if (statusBadge) {
            statusBadge.textContent = '● 未授权';
            statusBadge.className = 'status-badge disconnected';
        }
        if (statusDot) statusDot.className = 'status-dot disconnected';
        if (notConnected) notConnected.style.display = 'block';
        if (connected) connected.style.display = 'none';
        if (sidebarId) sidebarId.textContent = '';
        if (sidebarStats) sidebarStats.textContent = '--';
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
        if (avatarEl) {
            if (profile.avatar) {
                // Use proxy for external avatar URLs to bypass anti-hotlinking
                const avatarUrl = proxyAvatarUrl(profile.avatar);
                avatarEl.src = avatarUrl;
                avatarEl.style.display = 'block';
            } else {
                avatarEl.removeAttribute('src');
                avatarEl.style.display = 'none';
            }
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
    if (ui.saveSettingsBtn) ui.saveSettingsBtn.addEventListener('click', saveConfig);

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
                const label = window.i18n ? window.i18n.t('trakt.authorize_btn') : '授权 Trakt';
                authBtn.innerHTML = `🔐 ${label}`;
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
            tmdbConnectBtn.textContent = window.i18n ? window.i18n.t('status.connecting') : '连接中...';
            socket.emit('tmdb_connect', { api_key: apiKey });
        });
    }

    if (tmdbAuthSessionBtn) {
        tmdbAuthSessionBtn.addEventListener('click', () => {
            tmdbAuthSessionBtn.disabled = true;
            tmdbAuthSessionBtn.textContent = window.i18n ? window.i18n.t('status.authorizing') : '授权中...';
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
            const label = window.i18n ? window.i18n.t('tmdb.connect_btn') : '连接 TMDB';
            connectBtn.textContent = `🔗 ${label}`;
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
            const label = window.i18n ? window.i18n.t('tmdb.auth_session') : '授权同步评分';
            authBtn.textContent = `🔐 ${label}`;
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
            const sidebarStats = document.getElementById('tmdb-summary-stats');

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
            if (sidebarStats) sidebarStats.textContent = data.rated_count ? `${data.rated_count} 部` : '--';

            // Handle avatar display
            const avatarEl = document.getElementById('tmdb-avatar');
            if (avatarEl) {
                if (data.avatar) {
                    avatarEl.src = proxyAvatarUrl(data.avatar);
                    avatarEl.style.display = 'block';
                } else {
                    avatarEl.removeAttribute('src');
                    avatarEl.style.display = 'none';
                }
            }

            // Update stats and links
            if (ratedCount) ratedCount.textContent = data.rated_count || '0';
            if (watchlistCount) watchlistCount.textContent = data.watchlist_count || '0';
            if (ratedLink && data.rated_link) ratedLink.href = data.rated_link;
            if (watchlistLink && data.watchlist_link) watchlistLink.href = data.watchlist_link;
            if (profileLink && data.profile_link) profileLink.href = data.profile_link;
        }
    });

    // Call initially
    setTimeout(() => updateSettingsAuthStatus(), 500);
    function updateSettingsAuthStatus() {
        // Douban
        const doubanStatus = document.getElementById('settings-douban-status');
        if (doubanStatus) {
            if (appState.douban_cookie && appState.douban_user_id) {
                doubanStatus.textContent = '✅ 已配置';
                doubanStatus.className = 'auth-status success';
            } else {
                doubanStatus.textContent = '未配置';
                doubanStatus.className = 'auth-status';
            }
        }

        // IMDb
        const imdbStatus = document.getElementById('settings-imdb-status');
        if (imdbStatus) {
            if (appState.imdb_cookie && appState.imdb_user_id) {
                imdbStatus.textContent = '✅ 已配置';
                imdbStatus.className = 'auth-status success';
            } else {
                imdbStatus.textContent = '未配置';
                imdbStatus.className = 'auth-status';
            }
        }

        // TMDB (Check API Key presence)
        // Assuming we rely on config input values or appState for API key
        // appState.tmdb_api_key might not be populated, let's check input primarily + stats
        // Actually script.js doesn't seem to store tmdb_api_key in appState explicitly on load?
        // Let's rely on basic Douban/IMDb for now as requested.
    }

    // Hook into existing events to trigger this update
    const originalUpdatePlatformStatus = updatePlatformStatus;
    updatePlatformStatus = function () {
        originalUpdatePlatformStatus();
        updateSettingsAuthStatus();
    }

    // Call initially
    // setTimeout(() => updateSettingsAuthStatus(), 500);

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
        const sidebarStats = document.getElementById('tmdb-summary-stats');

        if (ratedCount) ratedCount.textContent = data.rated_count || '0';
        if (watchlistCount) watchlistCount.textContent = data.watchlist_count || '0';
        if (ratedLink && data.rated_link) ratedLink.href = data.rated_link;
        if (watchlistLink && data.watchlist_link) watchlistLink.href = data.watchlist_link;
        if (profileLink && data.profile_link) profileLink.href = data.profile_link;
        if (sidebarStats) sidebarStats.textContent = data.rated_count ? `${data.rated_count} 部` : '--';

        log(`📊 TMDB 统计已更新: ${data.rated_count} 已评分, ${data.watchlist_count} 想看`, 'info');
    });

    // Sidebar summary card clicks - navigate to platform and test connection
    document.querySelectorAll('.account-summary-card').forEach(card => {
        card.addEventListener('click', () => {
            const platform = card.id.replace('-summary-card', '');
            openSettingsSection('tab-settings');
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

    // Data tab TMDB button - trigger data fetch
    const fetchTmdbBtn = document.getElementById('fetch-tmdb-btn');
    if (fetchTmdbBtn) {
        fetchTmdbBtn.addEventListener('click', () => {
            socket.emit('fetch_tmdb_data', {});
        });
    }

    // Cookie config buttons - jump to settings page
    const configDoubanBtn = document.getElementById('config-douban-btn');
    const configImdbBtn = document.getElementById('config-imdb-btn');

    if (configDoubanBtn) {
        configDoubanBtn.addEventListener('click', () => {
            openSettingsSection('tab-settings');
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
            openSettingsSection('tab-settings');
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
    // Expose globally for other scripts
    window.log = log;

    function updateProgress(data) {
        if (ui.progressCard) {
            ui.progressCard.style.display = 'block';
            const percent = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;

            // Clean up step text - remove trailing numbers like "10/12" or "5/20"
            let stepText = data.step || '正在处理...';
            stepText = stepText.replace(/\s*\d+\/\d+\s*$/, '').trim();

            // Update individual elements
            if (ui.progressStepText) ui.progressStepText.textContent = stepText;
            if (ui.progressPercent) ui.progressPercent.textContent = `${percent}%`;
            if (ui.progressBar) ui.progressBar.style.width = `${percent}%`;
            if (ui.progressCurrent) ui.progressCurrent.textContent = data.current;
            if (ui.progressTotal) ui.progressTotal.textContent = data.total;
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
        const buttons = [
            ui.fetchDoubanBtn,
            ui.fetchImdbBtn,
            ui.syncBtn,
            document.getElementById('fetch-douban-wish-btn')
        ];
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
            openSettingsSection('tab-settings');
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
        const downloadConfig = collectDownloadSiteConfig();
        const configData = {
            douban_user_id: document.getElementById('douban-user-id-config')?.value || appState.douban_user_id || '',
            douban_cookie: document.getElementById('douban-cookie-config')?.value || appState.douban_cookie || '',
            imdb_user_id: document.getElementById('imdb-user-id-config')?.value || appState.imdb_user_id || '',
            imdb_cookie: document.getElementById('imdb-cookie-config')?.value || appState.imdb_cookie || '',
            media_server_url: document.getElementById('media-server-url')?.value?.trim() || '',
            media_server_api_key: document.getElementById('media-server-api-key')?.value?.trim() || '',
            server_username: document.getElementById('server-username')?.value?.trim() || 'cinerecord',
            server_password: document.getElementById('server-password')?.value || '',
            cinepersona_url: document.getElementById('cinepersona-url')?.value?.trim() || '',
            cinepersona_base_url: document.getElementById('cinepersona-base-url')?.value?.trim() || 'https://film.133339.xyz',
            cinepersona_api_key: document.getElementById('cinepersona-api-key')?.value || '',
            cinepersona_session_cookie: document.getElementById('cinepersona-session-cookie')?.value || '',
            cinepersona_consent: !!document.getElementById('cinepersona-consent')?.checked,
            cinepersona_auto_sync: !!document.getElementById('cinepersona-auto-sync')?.checked,
            download_sites_enabled: downloadConfig.enabledIds,
            download_sites_custom: downloadConfig.customSites
        };
        // Update appState
        appState.douban_cookie = configData.douban_cookie;
        appState.imdb_cookie = configData.imdb_cookie;
        downloadSiteState.enabledIds = new Set(downloadConfig.enabledIds);
        downloadSiteState.customSites = downloadConfig.customSites;

        socket.emit('save_config', configData);
        if (window.log) window.log('💾 配置已保存', 'success');

        if (configData.cinepersona_url) {
            const base = configData.cinepersona_url.replace(/\/+$/, '');
            const cinepersonaLink = document.getElementById('cinepersona-link');
            const cinepersonaImportLink = document.getElementById('cinepersona-import-link');
            const cinepersonaLinkSettings = document.getElementById('cinepersona-link-settings');
            const cinepersonaImportLinkSettings = document.getElementById('cinepersona-import-link-settings');
            if (cinepersonaLink) cinepersonaLink.href = base;
            if (cinepersonaImportLink) cinepersonaImportLink.href = `${base}/import`;
            if (cinepersonaLinkSettings) cinepersonaLinkSettings.href = base;
            if (cinepersonaImportLinkSettings) cinepersonaImportLinkSettings.href = `${base}/import`;
        } else {
            const base = 'https://film.133339.xyz';
            const cinepersonaLink = document.getElementById('cinepersona-link');
            const cinepersonaImportLink = document.getElementById('cinepersona-import-link');
            const cinepersonaLinkSettings = document.getElementById('cinepersona-link-settings');
            const cinepersonaImportLinkSettings = document.getElementById('cinepersona-import-link-settings');
            if (cinepersonaLink) cinepersonaLink.href = base;
            if (cinepersonaImportLink) cinepersonaImportLink.href = `${base}/import`;
            if (cinepersonaLinkSettings) cinepersonaLinkSettings.href = base;
            if (cinepersonaImportLinkSettings) cinepersonaImportLinkSettings.href = `${base}/import`;
        }

        // Show feedback on both buttons if they exist
        if (ui.saveConfigBtn) highlightElement(ui.saveConfigBtn, 'success');
        if (ui.saveSettingsBtn) highlightElement(ui.saveSettingsBtn, 'success');

        updateSettingsAuthStatus();
        if (wishlistState.items.length > 0) {
            renderWishlistPage(wishlistState.currentPage);
        }
    }

    function triggerFetch(platform) {
        // Get userId from appState (set during login) or settings page
        let userId = appState[`${platform}_user_id`] ||
            document.getElementById(`${platform}-user-id-config`)?.value || '';

        // Handle Backup Mode for Douban
        if (platform === 'douban') {
            const backupIdEl = document.getElementById('douban-backup-user-id');
            if (backupIdEl && backupIdEl.value.trim()) {
                const targetId = backupIdEl.value.trim();
                userId = targetId; // Override with friend's ID
                log(`👥 正在为好友 (${targetId}) 备份数据...`, 'info');
            }
        }

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

    // ========================================
    // Sync Logic
    // ========================================

    // Handle source platform change to update target options
    const syncSourceEl = document.getElementById('sync-source');
    const syncTargetEl = document.getElementById('sync-target');

    if (syncSourceEl && syncTargetEl) {
        syncSourceEl.addEventListener('change', () => {
            const source = syncSourceEl.value;

            // Enable all options first
            Array.from(syncTargetEl.options).forEach(opt => {
                opt.disabled = false;
                if (opt.value === source) {
                    opt.disabled = true; // Disable same platform
                }
            });

            // Auto-select a valid target if current selection is disabled
            if (syncTargetEl.value === source) {
                const firstValid = Array.from(syncTargetEl.options).find(opt => !opt.disabled);
                if (firstValid) syncTargetEl.value = firstValid.value;
            }
        });

        // Trigger once on init
        syncSourceEl.dispatchEvent(new Event('change'));
    }

    async function triggerSync(isDryRun) {
        // Get source and target platform
        const sourceEl = document.getElementById('sync-source');
        const targetEl = document.getElementById('sync-target');

        if (!sourceEl || !targetEl) {
            console.error("Sync selectors not found!");
            return;
        }

        // Get Sync Options
        const syncMode = document.querySelector('input[name="sync-mode"]:checked')?.value || 'new';
        const overwrite = syncMode === 'overwrite';
        const onlyNew = !overwrite;
        const defaultRatingEnabled = document.getElementById('opt-default-rating-enable')?.checked || false;
        const defaultRatingValue = document.getElementById('opt-default-rating-value')?.value || 0;
        const defaultRating = defaultRatingEnabled ? parseFloat(defaultRatingValue) : 0;

        const syncOptions = {
            only_new: onlyNew,
            overwrite: overwrite,
            default_rating: defaultRating
        };

        const sourcePlatform = sourceEl.value;
        const targetPlatform = targetEl.value;

        // Validate platforms are different
        if (sourcePlatform === targetPlatform) {
            log('❌ 源平台和目标平台不能相同', 'error');
            return;
        }

        const direction = `${sourcePlatform}-to-${targetPlatform}`;

        // Validate based on sync direction
        if (direction === 'douban-to-imdb' || direction === 'imdb-to-douban' || direction === 'letterboxd-to-imdb') {

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
            if (!appState.trakt_count) {
                log('❌ 请先获取 Trakt 数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.douban_cookie) {
                log('❌ 请先登录豆瓣账号', 'error');
                openSettingsSection('tab-settings');
                return;
            }
            // Use socket event for trakt-to-douban
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} Trakt → 豆瓣 同步...`, 'info');
            socket.emit('sync_trakt_to_douban', {
                with_ratings: true,
                is_dry_run: isDryRun,
                ...syncOptions
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
                openSettingsSection('tab-settings');
                return;
            }
            // Use socket event for imdb-to-trakt
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} IMDB → Trakt 同步...`, 'info');
            socket.emit('sync_imdb_to_trakt', {
                is_dry_run: isDryRun,
                ...syncOptions
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
                openSettingsSection('tab-settings');
                return;
            }
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} IMDB → TMDB 同步...`, 'info');
            socket.emit('sync_imdb_to_tmdb', {
                is_dry_run: isDryRun,
                ...syncOptions
            });
            return;
        } else if (direction === 'trakt-to-tmdb') {
            // Need Trakt cached data and TMDB auth
            if (!appState.trakt_count) {
                log('❌ 请先获取 Trakt 数据', 'error');
                switchTab('data');
                return;
            }
            if (!appState.tmdb_ready) {
                log('❌ 请先授权 TMDB 账号', 'error');
                openSettingsSection('tab-settings');
                return;
            }
            setButtonsState(true);
            log(`🚀 开始${isDryRun ? '预览' : '执行'} Trakt → TMDB 同步...`, 'info');
            socket.emit('sync_trakt_to_tmdb', {
                is_dry_run: isDryRun,
                ...syncOptions
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
            imdb_cookie: appState.imdb_cookie || '',
            ...syncOptions
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
            const coverUrl = getSafeImageUrl(movie['Cover URL'] || movie['CoverURL'] || '');
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
        const fetchWishBtn = document.getElementById(`fetch-${platform}-wish-btn`);

        if (!notConnectedEl || !connectedEl) return;

        if (isConnected) {
            notConnectedEl.style.display = 'none';
            connectedEl.style.display = 'block';
            if (logoutBtn) logoutBtn.style.display = 'inline-flex';
            if (fetchWishBtn) fetchWishBtn.style.display = 'inline-flex';

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
            if (fetchWishBtn) fetchWishBtn.style.display = 'none';

            if (statusBadge) {
                statusBadge.textContent = '● 未连接';
                statusBadge.className = 'status-badge disconnected';
            }
        }
    }

    function renderMergedDataPreview(data) {
        // Disabled per user request - data is already shown in data page
        // and this preview doesn't support pagination
        return;

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

        // Build movie grid HTML (horizontal compact layout)
        let html = '<div class="preview-compact-grid">';
        pageMovies.forEach(movie => {
            const coverUrl = getSafeImageUrl(movie['Cover URL'] || '');
            const rating = movie['Your Rating'] || movie['YourRating_douban'] || movie['YourRating_imdb'] || movie['source_rating'] || '';
            const movieUrl = movie['URL_douban'] || movie['URL_imdb'] || movie['URL'] || '#';
            const title = movie['Title'] || movie.title || '未知';
            const year = movie['Year'] || movie.year || '';

            // Check if this is a "skip" item (无评分-跳过)
            const isSkipped = title.includes('⚠️');
            const cleanTitle = title.replace(' ⚠️(无评分-跳过)', '');

            html += `
                <div class="preview-compact-item ${isSkipped ? 'sync-result-skipped' : ''}">
                    <div class="compact-title">
                        <a href="${movieUrl}" target="_blank" title="${cleanTitle}">${cleanTitle}</a>
                    </div>
                    <div class="compact-meta">
                        <span class="compact-year">${year}</span>
                        ${rating && !isSkipped ? `<span class="compact-rating">★ ${rating}</span>` : ''}
                        ${isSkipped ? '<span class="compact-reason">无评分</span>' : ''}
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
        const coverUrl = getSafeImageUrl(movie['Cover URL'] || '');
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
    };

    // Render detailed sync results
    function renderSyncResults(results, summary, source, target) {
        // Create or get results panel
        let resultsPanel = document.getElementById('sync-results-panel');
        if (!resultsPanel) {
            resultsPanel = document.createElement('div');
            resultsPanel.id = 'sync-results-panel';
            resultsPanel.className = 'sync-results-panel';

            // Insert after preview card
            const previewCard = document.getElementById('sync-preview-card');
            if (previewCard && previewCard.parentNode) {
                previewCard.parentNode.insertBefore(resultsPanel, previewCard.nextSibling);
            } else {
                document.querySelector('.content-main').appendChild(resultsPanel);
            }
        }

        resultsPanel.style.display = 'block';

        // Build HTML
        let html = `
            <div class="sync-results-header">
                <h3>🏁 同步结果: ${source.toUpperCase()} → ${target.toUpperCase()}</h3>
                <div class="results-summary">
                    ✅ 成功 ${summary.success} · ❌ 失败 ${summary.failed} · ⏭️ 跳过 ${summary.skipped}
                </div>
            </div>
            
            <div class="results-tabs">
                <button class="results-tab active" data-tab="success">✅ 成功 (${summary.success})</button>
                <button class="results-tab" data-tab="failed">❌ 失败 (${summary.failed})</button>
                <button class="results-tab" data-tab="skipped">⏭️ 跳过 (${summary.skipped})</button>
            </div>
            
            <div class="results-content">
                <div class="results-tab-content active" data-content="success">
                    <div class="preview-compact-grid">
                        ${results.success.map(movie => `
                            <div class="preview-compact-item sync-result-success">
                                <div class="compact-title">
                                    <a href="${movie.target_url}" target="_blank" title="${movie.title}">${movie.title}</a>
                                </div>
                                <div class="compact-meta">
                                    <span class="compact-year">${movie.year}</span>
                                    <span class="compact-rating">★ ${movie.source_rating}/10</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    ${results.success.length === 0 ? '<p class="empty-state">无成功记录</p>' : ''}
                </div>
                
                <div class="results-tab-content" data-content="failed">
                    <div class="preview-compact-grid">
                        ${results.failed.map(movie => `
                            <div class="preview-compact-item sync-result-failed">
                                <div class="compact-title">
                                    <a href="${movie.source_url}" target="_blank" title="${movie.title}">${movie.title}</a>
                                </div>
                                <div class="compact-meta">
                                    <span class="compact-year">${movie.year}</span>
                                    <span class="compact-error">${movie.error_msg}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    ${results.failed.length === 0 ? '<p class="empty-state">无失败记录</p>' : ''}
                </div>
                
                <div class="results-tab-content" data-content="skipped">
                    <div class="preview-compact-grid">
                        ${results.skipped.map(movie => `
                            <div class="preview-compact-item sync-result-skipped">
                                <div class="compact-title">
                                    <a href="${movie.source_url}" target="_blank" title="${movie.title}">${movie.title}</a>
                                </div>
                                <div class="compact-meta">
                                    <span class="compact-year">${movie.year}</span>
                                    <span class="compact-reason">${movie.reason}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    ${results.skipped.length === 0 ? '<p class="empty-state">无跳过记录</p>' : ''}
                </div>
            </div>
        `;

        resultsPanel.innerHTML = html;

        // Add tab click handlers
        const tabs = resultsPanel.querySelectorAll('.results-tab');
        const tabContents = resultsPanel.querySelectorAll('.results-tab-content');

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetTab = tab.dataset.tab;

                tabs.forEach(t => t.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active'));

                tab.classList.add('active');
                resultsPanel.querySelector(`[data-content="${targetTab}"]`).classList.add('active');
            });
        });

        // Scroll to results
        resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
            const coverUrl = getSafeImageUrl(movie['Cover URL'] || '');
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
                activeTab: document.querySelector('.nav-tab.active')?.dataset.tab || 'dashboard',
                settingsSection: currentSettingsSection,
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
            if (sessionData.settingsSection) {
                currentSettingsSection = sessionData.settingsSection;
            }
            if (sessionData.activeTab) {
                switchTab(normalizeTabId(sessionData.activeTab));
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

                    if (statusDot) {
                        statusDot.className = data.connected ? 'status-dot connected' : 'status-dot disconnected';
                    }
                    if (data.connected) {
                        if (statsEl && data.stats && data.stats !== '--') {
                            statsEl.textContent = data.stats;
                        }
                        if (sidebarId && data.sidebarId) {
                            sidebarId.textContent = data.sidebarId;
                        }
                    } else {
                        if (statsEl) statsEl.textContent = '--';
                        if (sidebarId) sidebarId.textContent = '';
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

    // Handle detailed sync results
    socket.on('sync_results_data', (data) => {
        renderSyncResults(data.results, data.summary, data.source, data.target);
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

// =============== UNIFIED LIBRARY LOGIC ===============
let libraryState = {
    currentPage: 1,
    totalPages: 1,
    pageSize: 20,
    filter: 'all',  // 'all', 'douban', 'imdb', 'trakt', etc.
    viewMode: 'grid' // 'grid' or 'list'
};

document.addEventListener('DOMContentLoaded', () => {
    // Setup View Toggles
    const gridBtn = document.getElementById('library-view-grid');
    const listBtn = document.getElementById('library-view-list');

    if (gridBtn && listBtn) {
        gridBtn.addEventListener('click', () => {
            libraryState.viewMode = 'grid';
            renderUnifiedLibrary(window.lastLibraryData || { movies: [], total_pages: 1, page: 1, platform_counts: {} });
        });

        listBtn.addEventListener('click', () => {
            libraryState.viewMode = 'list';
            renderUnifiedLibrary(window.lastLibraryData || { movies: [], total_pages: 1, page: 1, platform_counts: {} });
        });
    }
});

function getSelectedPlatforms() {
    const checked = document.querySelectorAll('.filter-checkbox input[type="checkbox"]:checked');
    const selected = Array.from(checked)
        .map(cb => cb.value)
        .filter(Boolean);
    // If checkboxes not rendered yet, request all platforms to avoid empty results
    if (!checked.length) {
        return 'douban,imdb,trakt,letterboxd,tmdb';
    }
    return selected.join(',');
}

function refreshLibrary(page = 1) {
    const selectedPlatforms = getSelectedPlatforms();
    const pageSize = libraryState.pageSize || 20;
    const filter = libraryState.filter || 'all';

    return fetch(`/api/library?page=${page}&page_size=${pageSize}&platform=${filter}&platforms=${selectedPlatforms}`)
        .then(res => res.json())
        .then(data => {
            // Initialize checkboxes based on available data on first load
            if (data.platforms_with_data && !window.platformsInitialized) {
                window.platformsInitialized = true;
                const platformsWithData = new Set(data.platforms_with_data);

                document.querySelectorAll('.filter-checkbox input[type="checkbox"]').forEach(checkbox => {
                    checkbox.checked = platformsWithData.has(checkbox.value);
                });

                // Re-run with the newly checked platforms to ensure counts match
                setTimeout(() => refreshLibrary(page), 100);
                return;
            }

            renderUnifiedLibrary(data);
        })
        .catch(err => console.error('[Library] Refresh error:', err));
}

function renderUnifiedLibrary(data) {
    if (!data || !data.movies) return;
    window.lastLibraryData = data; // Cache for view toggling

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
    if (libraryList) {
        libraryList.style.display = '';
        // Apply view mode classes
        libraryList.classList.toggle('library-grid-view', libraryState.viewMode === 'grid');
        libraryList.classList.toggle('library-list-view', libraryState.viewMode === 'list');
        // Legacy cleanup just in case
        libraryList.classList.remove('library-list');
    }
    if (libraryPagination) libraryPagination.style.display = total_pages > 1 ? 'flex' : 'none';

    // Update view toggle button states
    const gridBtn = document.getElementById('library-view-grid');
    const listBtn = document.getElementById('library-view-list');
    if (gridBtn && listBtn) {
        gridBtn.classList.toggle('active', libraryState.viewMode === 'grid');
        listBtn.classList.toggle('active', libraryState.viewMode === 'list');
    }

    // Render movie list with rich metadata
    let html = '';
    movies.forEach(movie => {
        // Platform badges - next to title
        let platformBadgesHtml = '';

        const sourceCount = movie.sources ? movie.sources.length : 0;
        const isShared = sourceCount >= 2;

        const PLATFORM_ICONS = {
            'douban': '<img src="/static/images/platforms/douban.png" alt="Douban" style="width:14px;height:14px;vertical-align:middle;border-radius:2px;">',
            'imdb': '<img src="/static/images/platforms/imdb.svg" alt="IMDb" style="width:14px;height:14px;vertical-align:middle;border-radius:2px;">',
            'trakt': '<img src="/static/images/platforms/trakt.png" alt="Trakt" style="width:14px;height:14px;vertical-align:middle;border-radius:2px;">',
            'tmdb': '<img src="/static/images/platforms/tmdb.png" alt="TMDB" style="width:14px;height:14px;vertical-align:middle;border-radius:2px;">',
            'letterboxd': '<img src="/static/images/platforms/letterboxd.png" alt="Letterboxd" style="width:14px;height:14px;vertical-align:middle;border-radius:2px;">',
            'cinepersona': '🧬 '
        };

        const buildBadge = (platform, url, rating, votes, label, forceShow = false) => {
            // For shared movies: show all available platform links
            // For exclusive movies: only show the source platform
            if (!isShared && !movie.sources.includes(platform)) return '';
            // For shared movies, show if forceShow is true OR if platform is in sources
            if (isShared && !forceShow && !movie.sources.includes(platform)) return '';

            const voteText = votes ? formatVotes(votes) : '';
            const iconHtml = PLATFORM_ICONS[platform] || label;

            return `
                <a href="${url}" target="_blank" class="badge-v3 ${platform}" title="${label}">
                    <span class="badge-logo">${iconHtml}</span>
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
        const posterUrl = getSafeImageUrl(movie.poster_url || '');
        const coverHtml = posterUrl
            ? `<div class="movie-cover-wrapper"><img class="movie-cover-large" src="${posterUrl}" alt="" loading="lazy" onerror="this.onerror=null; this.src=''; this.parentNode.classList.add('error');"></div>`
            : `<div class="movie-cover-wrapper"><div class="movie-cover-placeholder large">🎬</div></div>`;

        // User's rating and date
        const userRating = movie.rating ? `<div class="rating-main"><span class="rating-label">评分</span><span class="rating-value">${movie.rating}</span></div>` : '';
        const earliestDate = movie.latest_date || movie.date_rated || movie.earliest_date || '';
        const dateDisplay = earliestDate ? `<div class="rating-date"><span class="date-label">最后操作于</span><span class="date-value">${earliestDate.substring(0, 10)}</span></div>` : '';

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
        // Platform checkbox change handlers
        document.querySelectorAll('.filter-checkbox input[type="checkbox"]').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                // Reset to page 1 when changing platform selection
                libraryState.currentPage = 1;
                refreshLibrary();
            });
        });

        // Refresh button handler
        const refreshBtn = document.getElementById('refresh-library-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                console.log('[Library] Refresh button clicked');
                refreshLibrary(1);
            });
        }

        // Filter tab handlers
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

                // Refresh with selected platforms
                refreshLibrary(1);
            });
        });

        // Pagination buttons
        const prevBtn = document.getElementById('lib-prev-btn');
        const nextBtn = document.getElementById('lib-next-btn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (libraryState.currentPage > 1) {
                    refreshLibrary(libraryState.currentPage - 1);
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (libraryState.currentPage < libraryState.totalPages) {
                    refreshLibrary(libraryState.currentPage + 1);
                }
            });
        }

        console.log('[Library] Filter handlers initialized');

        // Initial load with auto-detected platforms
        refreshLibrary();
    };

    // Initialize after a small delay to ensure socket is ready
    setTimeout(initFilterHandlers, 100);
});

// ==========================================
// Wishlist Feature Handlers
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    // 1. Event Handler for Fetch Wish Buttons
    const fetchDoubanWishBtn = document.getElementById('fetch-douban-wish-btn');
    if (fetchDoubanWishBtn) {
        fetchDoubanWishBtn.addEventListener('click', () => {
            triggerFetchWish('douban', fetchDoubanWishBtn);
        });
    }

    const wishlistFetchButtons = document.querySelectorAll('.wishlist-fetch-btn');
    if (wishlistFetchButtons.length) {
        wishlistFetchButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const platform = btn.dataset.platform;
                if (platform) {
                    triggerFetchWish(platform, btn);
                }
            });
        });
    }

    const wishlistViewButtons = document.querySelectorAll('.wishlist-view-toggle [data-view]');
    if (wishlistViewButtons.length) {
        wishlistViewButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                setWishlistViewMode(btn.dataset.view);
            });
        });
        updateWishlistViewToggle();
    }

    const wishlistFilterToggle = document.getElementById('wishlist-filter-undownloaded');
    if (wishlistFilterToggle) {
        if (typeof wishlistState !== 'undefined') {
            wishlistState.filterUndownloaded = wishlistFilterToggle.checked;
        }
        wishlistFilterToggle.addEventListener('change', () => {
            if (typeof wishlistState !== 'undefined') {
                wishlistState.filterUndownloaded = wishlistFilterToggle.checked;
                renderWishlistPage(1);
            }
        });
    }

    const wishlistSourceFilters = document.querySelectorAll('#wishlist-source-filters input[data-source]');
    if (wishlistSourceFilters.length) {
        wishlistSourceFilters.forEach(cb => {
            cb.addEventListener('change', () => {
                syncWishlistSourceSelection();
                renderWishlistPage(1);
            });
        });
    }

    const letterboxdWatchlistBtn = document.getElementById('letterboxd-watchlist-btn');
    const letterboxdWatchlistInput = document.getElementById('letterboxd-watchlist-input');
    if (letterboxdWatchlistBtn && letterboxdWatchlistInput) {
        letterboxdWatchlistBtn.addEventListener('click', () => letterboxdWatchlistInput.click());
        letterboxdWatchlistInput.addEventListener('change', async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            try {
                const content = await file.text();
                window.socket.emit('upload_letterboxd_watchlist', {
                    filename: file.name,
                    content
                });
                if (window.log) window.log('📥 正在导入 Letterboxd 想看列表...', 'info');
            } catch (err) {
                if (window.log) window.log(`❌ 读取文件失败: ${err}`, 'error');
            } finally {
                letterboxdWatchlistInput.value = '';
            }
        });
    }

    const cinepersonaWishlistBtn = document.getElementById('cinepersona-wishlist-btn');
    if (cinepersonaWishlistBtn) {
        cinepersonaWishlistBtn.addEventListener('click', () => {
            if (window.socket) {
                window.socket.emit('fetch_cinepersona_watchlist', {});
                if (window.log) window.log('🧬 正在从 CinePersona 拉取想看...', 'info');
            }
        });
    }

    // 2. Socket Listeners for Wishlist
    if (window.socket) {
        window.socket.on('fetch_wish_complete', (data) => {
            // Log success
            if (window.log) window.log(`✅ ${data.platform.toUpperCase()} 想看列表获取完成: ${data.count} 部`, 'success');

            // Update Count in Account Tab
            const wishCountEl = document.getElementById(`${data.platform}-wish-count`);
            if (wishCountEl) {
                wishCountEl.textContent = data.count;
            }

            // Reset button
            if (data.platform === 'douban' && fetchDoubanWishBtn) {
                fetchDoubanWishBtn.disabled = false;
                fetchDoubanWishBtn.innerHTML = '📥 获取想看';
            }
            document.querySelectorAll(`.wishlist-fetch-btn[data-platform="${data.platform}"]`).forEach(btn => {
                btn.disabled = false;
                if (btn.dataset.label) {
                    btn.innerHTML = btn.dataset.label;
                }
            });

            // Refresh wishlist view if active
            const activeTab = document.querySelector('.nav-tab.active');
            if (activeTab && activeTab.dataset.tab === 'wishlist') {
                loadWishlistLibrary();
            }
        });

        // Listeners for Wishlist View
        window.socket.on('wishlist_library_data', (data) => {
            renderWishlist(data.items);
        });

        // Listeners for Backups View
        window.socket.on('backups_list_data', (data) => {
            renderBackupsList(data.backups);
        });

        window.socket.on('backup_content_data', (data) => {
            renderBackupPreview(data);
        });

        // Listeners for My Platform Files
        window.socket.on('my_files_list_data', (data) => {
            renderMyFilesList(data.files);
        });

        window.socket.on('my_file_deleted', () => {
            loadMyFilesList();
        });
    }
});

// ==========================================
// Wishlist & Backups Functions
// ==========================================

function loadWishlistLibrary() {
    if (window.log) window.log('📡 加载想看列表...', 'info');
    window.socket.emit('get_wishlist_library');
}

const WISHLIST_VIEW_STORAGE_KEY = 'wishlist_view_mode';
const WISHLIST_PAGE_SIZES = { grid: 24, list: 12 };
const WISHLIST_SOURCE_LABELS = {
    douban: '豆瓣',
    imdb: 'IMDb',
    trakt: 'Trakt',
    tmdb: 'TMDB',
    letterboxd: 'Letterboxd',
    cinepersona: 'CinePersona'
};

function normalizeWishlistSource(value) {
    return String(value || '').toLowerCase().trim();
}

function getWishlistSource(movie) {
    return normalizeWishlistSource(movie?.source || movie?.Source || movie?.platform || '');
}

function getSavedWishlistViewMode() {
    try {
        const saved = localStorage.getItem(WISHLIST_VIEW_STORAGE_KEY);
        if (saved === 'grid' || saved === 'list') return saved;
    } catch (e) {
        console.warn('Wishlist view mode storage unavailable:', e);
    }
    return 'list';
}

function updateWishlistViewToggle() {
    const gridBtn = document.getElementById('wishlist-view-grid');
    const listBtn = document.getElementById('wishlist-view-list');
    if (!gridBtn || !listBtn) return;

    gridBtn.classList.toggle('active', wishlistState.viewMode === 'grid');
    listBtn.classList.toggle('active', wishlistState.viewMode === 'list');

    // Attach click handlers if not already attached
    if (!gridBtn.dataset.initialized) {
        gridBtn.addEventListener('click', () => setWishlistViewMode('grid'));
        gridBtn.dataset.initialized = 'true';
    }
    if (!listBtn.dataset.initialized) {
        listBtn.addEventListener('click', () => setWishlistViewMode('list'));
        listBtn.dataset.initialized = 'true';
    }
}

function setWishlistViewMode(mode) {
    const normalized = mode === 'list' ? 'list' : 'grid';
    if (wishlistState.viewMode === normalized) return;

    wishlistState.viewMode = normalized;
    wishlistState.pageSize = WISHLIST_PAGE_SIZES[normalized] || WISHLIST_PAGE_SIZES.grid;
    const displayItems = getWishlistDisplayItems();
    wishlistState.totalPages = Math.ceil(displayItems.length / wishlistState.pageSize) || 1;
    wishlistState.currentPage = Math.min(wishlistState.currentPage, wishlistState.totalPages) || 1;

    try {
        localStorage.setItem(WISHLIST_VIEW_STORAGE_KEY, normalized);
    } catch (e) {
        console.warn('Wishlist view mode storage unavailable:', e);
    }

    updateWishlistViewToggle();

    if (wishlistState.items.length > 0) {
        renderWishlistPage(wishlistState.currentPage);
    }
}

function formatWishlistVotes(num) {
    if (!num) return '';
    const n = parseFloat(num);
    if (Number.isNaN(n)) return '';
    if (n >= 10000) return (n / 10000).toFixed(1) + '万';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
}

// Wishlist state
const initialWishlistViewMode = getSavedWishlistViewMode();
const wishlistState = {
    items: [],
    totalCount: 0,
    currentPage: 1,
    pageSize: WISHLIST_PAGE_SIZES[initialWishlistViewMode] || WISHLIST_PAGE_SIZES.grid,
    totalPages: 1,
    viewMode: initialWishlistViewMode,
    filterUndownloaded: false,
    activeSources: []
};

function isLibraryMatched(movie) {
    if (!movie) return false;
    if (movie.library_matched !== undefined) return !!movie.library_matched;
    if (movie.libraryMatched !== undefined) return !!movie.libraryMatched;
    if (movie.library_match && typeof movie.library_match === 'object') {
        return !!movie.library_match.matched;
    }
    return false;
}

function updateWishlistSourceFilters(items) {
    const container = document.getElementById('wishlist-source-filters');
    if (!container) return;

    const availableSources = new Set();
    (items || []).forEach(item => {
        const source = getWishlistSource(item);
        if (source) availableSources.add(source);
    });

    const checkboxes = Array.from(container.querySelectorAll('input[type="checkbox"][data-source]'));
    if (!checkboxes.length) return;

    if (!availableSources.size) {
        wishlistState.activeSources = [];
    }

    if (!wishlistState.activeSources.length && availableSources.size) {
        wishlistState.activeSources = Array.from(availableSources);
    } else {
        wishlistState.activeSources = wishlistState.activeSources.filter(source => availableSources.has(source));
        if (!wishlistState.activeSources.length && availableSources.size) {
            wishlistState.activeSources = Array.from(availableSources);
        }
    }

    checkboxes.forEach(cb => {
        const source = normalizeWishlistSource(cb.dataset.source);
        const hasSource = availableSources.has(source);
        cb.disabled = !hasSource;
        cb.checked = wishlistState.activeSources.includes(source);
        const label = cb.closest('.wishlist-source-option');
        if (label) label.classList.toggle('disabled', !hasSource);
    });
}

function syncWishlistSourceSelection() {
    const container = document.getElementById('wishlist-source-filters');
    if (!container) return;

    const selections = Array.from(container.querySelectorAll('input[type="checkbox"][data-source]'))
        .filter(cb => cb.checked && !cb.disabled)
        .map(cb => normalizeWishlistSource(cb.dataset.source));
    wishlistState.activeSources = selections;
}

function getWishlistDisplayItems() {
    const items = Array.isArray(wishlistState.items) ? wishlistState.items : [];
    return items.filter(movie => {
        const source = getWishlistSource(movie);
        if (wishlistState.activeSources.length) {
            if (!source) return false;
            if (!wishlistState.activeSources.includes(source)) return false;
        }
        if (wishlistState.filterUndownloaded && isLibraryMatched(movie)) return false;
        return true;
    });
}

function renderWishlist(items) {
    const listEl = document.getElementById('wishlist-list');
    const emptyEl = document.getElementById('wishlist-empty');
    const paginationEl = document.getElementById('wishlist-pagination');

    wishlistState.items = items || [];
    wishlistState.totalCount = wishlistState.items.length;
    wishlistState.currentPage = 1;
    wishlistState.pageSize = WISHLIST_PAGE_SIZES[wishlistState.viewMode] || WISHLIST_PAGE_SIZES.grid;
    updateWishlistSourceFilters(wishlistState.items);
    const displayItems = getWishlistDisplayItems();
    wishlistState.totalPages = Math.ceil(displayItems.length / wishlistState.pageSize) || 1;

    if (!items || items.length === 0) {
        if (listEl) listEl.style.display = 'none';
        if (emptyEl) emptyEl.style.display = 'block';
        if (paginationEl) paginationEl.style.display = 'none';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    if (listEl) listEl.style.display = '';
    updateWishlistViewToggle();
    renderWishlistPage(1);
}

function getSafeImageUrl(url) {
    if (!url) return '';
    const lower = String(url).toLowerCase();
    if (lower.includes('doubanio.com') || lower.includes('douban.com')) {
        return `/proxy/image?url=${encodeURIComponent(url)}`;
    }
    return url;
}

// Smart Cover Art Fallback (CSS Gradients)
function escapeQuotes(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function handlePosterError(imgEl, title) {
    if (imgEl.dataset.failed) return;
    imgEl.dataset.failed = "true";
    imgEl.style.display = 'none';

    const safeTitle = title || '?';
    // Use first character, ignoring common prefixes roughly if we want, or just first char
    const firstChar = safeTitle.replace(/^[^\w\u4e00-\u9fa5]+/, '').charAt(0).toUpperCase() || '?';

    const fallbackDiv = document.createElement('div');
    fallbackDiv.className = 'poster-fallback';
    fallbackDiv.innerHTML = `<span>${firstChar}</span>`;

    const colors = [
        'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'linear-gradient(135deg, #434343 0%, #000000 100%)',
        'linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)',
        'linear-gradient(135deg, #d53369 0%, #cbad6d 100%)',
        'linear-gradient(135deg, #ff0844 0%, #ffb199 100%)',
        'linear-gradient(135deg, #09203f 0%, #537895 100%)',
        'linear-gradient(135deg, #b06ab3 0%, #4568dc 100%)'
    ];
    let sum = 0;
    for (let i = 0; i < safeTitle.length; i++) {
        sum += safeTitle.charCodeAt(i);
    }
    fallbackDiv.style.background = colors[sum % colors.length];

    // Check if the previous element is already a fallback (defensive coding)
    if (!imgEl.nextElementSibling || !imgEl.nextElementSibling.classList.contains('poster-fallback')) {
        imgEl.parentNode.insertBefore(fallbackDiv, imgEl.nextSibling);
    }
}


function renderWishlistPage(page) {
    const listEl = document.getElementById('wishlist-list');
    const paginationEl = document.getElementById('wishlist-pagination');

    if (!listEl) return;

    listEl.style.display = '';

    const displayItems = getWishlistDisplayItems();
    wishlistState.totalPages = Math.ceil(displayItems.length / wishlistState.pageSize) || 1;
    wishlistState.currentPage = Math.min(page, wishlistState.totalPages) || 1;
    const start = (wishlistState.currentPage - 1) * wishlistState.pageSize;
    const end = start + wishlistState.pageSize;
    const pageItems = displayItems.slice(start, end);

    listEl.classList.toggle('wishlist-grid-view', wishlistState.viewMode === 'grid');
    listEl.classList.toggle('wishlist-list-view', wishlistState.viewMode === 'list');

    if (displayItems.length === 0) {
        listEl.style.display = '';
        listEl.innerHTML = '<div class="wishlist-filter-empty">已全部在媒体库中</div>';
        if (paginationEl) paginationEl.style.display = 'none';
        return;
    }

    if (wishlistState.viewMode === 'list') {
        listEl.innerHTML = pageItems.map(movie => {
            const title = movie.Title || movie.title || 'Unknown Title';
            const year = movie.Year || movie.year || '';
            const poster = getSafeImageUrl(movie['Cover URL'] || movie.poster_url || '/static/images/default_poster.png');
            const rating = movie['Douban Rating'] || movie['IMDb Rating'] || '';
            const votes = movie['Num Votes'] || movie['IMDb Votes'] || '';
            const dateAdded = movie['Date Rated'] || movie['Date Added'] || '';
            const directors = movie['Directors'] || '';
            const actors = movie['Actors'] || '';
            const genres = movie['Genres'] || '';
            const country = movie['Country'] || '';
            const source = getWishlistSource(movie);
            const sourceLabel = source ? (WISHLIST_SOURCE_LABELS[source] || source.toUpperCase()) : '';
            const matched = isLibraryMatched(movie);
            const links = matched ? [] : buildDownloadSiteLinks(movie);
            const libraryUrl = movie.library_url || '';
            const libraryFile = movie.library_file_name || movie.library_file || '';
            const libraryPath = movie.library_path || '';

            const metaParts = [];
            if (genres) metaParts.push(genres);
            if (directors) metaParts.push(`导演: ${directors}`);
            if (actors) metaParts.push(`主演: ${actors}`);
            if (country) metaParts.push(country);
            if (sourceLabel) metaParts.push(`来源: ${sourceLabel}`);
            const metaText = metaParts.filter(Boolean).join(' · ');

            let ratingText = '';
            let ratingClass = '';
            if (movie['Douban Rating']) { ratingText = `豆瓣 ${movie['Douban Rating']}`; ratingClass = 'rating-douban'; }
            else if (movie['IMDb Rating']) { ratingText = `IMDb ${movie['IMDb Rating']}`; ratingClass = 'rating-imdb'; }

            const votesText = formatWishlistVotes(votes);
            const mainLink = movie.URL || movie.douban_url || movie.imdb_url || '#';
            const linksHtml = links.length
                ? links.map(link => `<a class="wishlist-link" href="${link.url}" target="_blank">${link.label} ↗</a>`).join('')
                : '';
            const libraryLinkHtml = matched
                ? (libraryUrl
                    ? `<a class="wishlist-library-link" href="${libraryUrl}" target="_blank">库内播放 ↗</a>`
                    : `<span class="wishlist-library-tag">已入库</span>`)
                : '';
            const libraryFileHtml = matched && libraryFile
                ? `<span class="wishlist-library-file" title="${libraryPath || libraryFile}">${libraryFile}</span>`
                : '';

            return `
            <div class="wishlist-row">
                <div class="wishlist-cover">
                    <img src="${poster}" alt="${title}" loading="lazy" referrerpolicy="no-referrer"
                        onerror="handlePosterError(this, '${escapeQuotes(title)}')">
                </div>
                <div class="wishlist-main">
                    <div class="wishlist-title-row">
                        <div class="wishlist-title-group">
                            <a class="wishlist-title" href="${mainLink}" target="_blank" title="${title}">${title}</a>
                            ${year ? `<span class="wishlist-year">${year}</span>` : ''}
                        </div>
                        ${linksHtml ? `<div class="wishlist-links">${linksHtml}</div>` : ''}
                    </div>
                    ${metaText ? `<div class="wishlist-meta" title="${metaText}">${metaText}</div>` : ''}
                    <div class="wishlist-submeta">
                        ${libraryLinkHtml}
                        ${libraryFileHtml}
                        ${ratingText ? `<span class="wishlist-rating ${ratingClass}">${ratingText}</span>` : ''}
                        ${votesText ? `<span class="wishlist-votes">${votesText}人评价</span>` : ''}
                        ${dateAdded ? `<span class="wishlist-date">想看于 ${String(dateAdded).substring(0, 10)}</span>` : ''}
                    </div>
                </div>
            </div>
            `;
        }).join('');
    } else {
        listEl.innerHTML = pageItems.map(movie => {
            const title = movie.Title || movie.title || 'Unknown Title';
            const poster = getSafeImageUrl(movie['Cover URL'] || movie.poster_url || '/static/images/default_poster.png');
            const rating = movie['Douban Rating'] || 0;
            const link = movie.URL || movie.douban_url || '#';

            return `
            <div class="movie-card compact">
                <a href="${link}" target="_blank" style="text-decoration:none;color:inherit;">
                    <div class="movie-poster-wrapper">
                        <img src="${poster}" alt="${title}" class="movie-poster" loading="lazy" referrerpolicy="no-referrer"
                             onerror="handlePosterError(this, '${escapeQuotes(title)}')">
                        ${rating ? `<div class="movie-rating-badge douban">${rating}</div>` : ''}
                    </div>
                    <div class="movie-info">
                        <div class="movie-title" title="${title}">${title}</div>
                    </div>
                </a>
            </div>
            `;
        }).join('');
    }

    // Update pagination
    if (paginationEl) {
        if (wishlistState.totalPages > 1) {
            paginationEl.style.display = 'flex';
            paginationEl.innerHTML = `
                <button class="btn btn-secondary btn-sm" onclick="renderWishlistPage(${wishlistState.currentPage - 1})" ${wishlistState.currentPage <= 1 ? 'disabled' : ''}>← 上一页</button>
                <span class="pagination-info">${wishlistState.currentPage} / ${wishlistState.totalPages} (共 ${wishlistState.totalCount} 部)</span>
                <button class="btn btn-secondary btn-sm" onclick="renderWishlistPage(${wishlistState.currentPage + 1})" ${wishlistState.currentPage >= wishlistState.totalPages ? 'disabled' : ''}>下一页 →</button>
            `;
        } else {
            paginationEl.style.display = 'none';
        }
    }
}

function downloadWishlist(format = 'cinerecord-csv') {
    const downloadUrl = `/download/wishlist?format=${encodeURIComponent(format)}&t=${Date.now()}`;
    let iframe = document.getElementById('download-iframe');
    if (!iframe) {
        iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.id = 'download-iframe';
        document.body.appendChild(iframe);
    }
    iframe.src = downloadUrl;
}

function triggerFetchWish(platform, btnEl) {
    const btn = btnEl || document.getElementById('refresh-wishlist-btn');
    if (btn) {
        if (!btn.dataset.label) {
            btn.dataset.label = btn.innerHTML;
        }
        btn.disabled = true;
        btn.innerHTML = '<span class="loading-spinner"></span> 处理中...';
    }
    if (window.socket) {
        window.socket.emit('fetch_wish', { platform: platform, force_full: true });
        window.log(`🚀 开始获取 ${platform.toUpperCase()} 想看列表...`, 'info');
    }
}

// Backups Functions

// Backup sub-tab switching
let backupSubTabsInitialized = false;
function initBackupSubTabs() {
    if (backupSubTabsInitialized) return;
    backupSubTabsInitialized = true;

    document.querySelectorAll('.backup-sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            // Update tab styles
            document.querySelectorAll('.backup-sub-tab').forEach(t => {
                t.classList.remove('active');
                t.style.background = 'transparent';
                t.style.color = 'var(--text-secondary)';
            });
            tab.classList.add('active');
            tab.style.background = 'var(--bg-card)';
            tab.style.color = 'var(--text-primary)';

            // Update panels
            document.querySelectorAll('.backup-sub-panel').forEach(p => {
                p.classList.remove('active');
                p.style.display = 'none';
            });
            const panelId = tab.dataset.backupTab + '-panel';
            const panel = document.getElementById(panelId);
            if (panel) {
                panel.classList.add('active');
                panel.style.display = 'block';
            }

            // Load appropriate data
            if (tab.dataset.backupTab === 'my-data') {
                loadMyFilesList();
            } else {
                loadBackupsList();
            }
        });
    });
}

// My Platform Files
function loadMyFilesList() {
    if (window.socket) window.socket.emit('get_my_files_list');
}

function renderMyFilesList(files) {
    const tbody = document.getElementById('my-files-table-body');
    const emptyMsg = document.getElementById('my-files-empty-msg');

    if (!tbody) return;

    if (!files || files.length === 0) {
        tbody.innerHTML = '';
        if (emptyMsg) emptyMsg.style.display = 'block';
        return;
    }

    if (emptyMsg) emptyMsg.style.display = 'none';
    tbody.innerHTML = files.map(file => `
        <tr style="border-bottom: 1px solid var(--border-color);">
            <td style="padding: 10px;">${file.filename}</td>
            <td style="padding: 10px;">
                <img src="/static/images/platforms/${file.platform.toLowerCase()}.png" 
                     style="width:16px;vertical-align:middle" 
                     onerror="this.style.display='none'"> 
                ${file.platform}
            </td>
            <td style="padding: 10px;">
                <span class="status-badge ${file.type === '想看' ? 'wishlist' : 'completed'}">
                    ${file.type}
                </span>
            </td>
            <td style="padding: 10px;">${(file.size / 1024).toFixed(1)} KB</td>
            <td style="padding: 10px;">${file.mtime}</td>
            <td style="padding: 10px;">
                <button class="btn btn-sm btn-outline danger" onclick="deleteMyFile('${file.filename}')">🗑️ 删除</button>
            </td>
        </tr>
    `).join('');
}

function deleteMyFile(filename) {
    if (confirm(`确定删除 ${filename}？\n删除后下次获取数据时将自动全量更新。`)) {
        if (window.socket) window.socket.emit('delete_my_file', { filename });
    }
}

function loadBackupsList() {
    if (window.socket) window.socket.emit('get_backups_list');
}

function renderBackupsList(backups) {
    const tbody = document.getElementById('backups-table-body');
    const emptyMsg = document.getElementById('backups-empty-msg');

    if (!backups || backups.length === 0) {
        tbody.innerHTML = '';
        emptyMsg.style.display = 'block';
        return;
    }

    emptyMsg.style.display = 'none';
    tbody.innerHTML = backups.map(file => `
        <tr style="border-bottom: 1px solid var(--border-color);">
            <td style="padding: 10px;">${file.filename}</td>
            <td style="padding: 10px;">
                <img src="/static/images/platforms/${file.platform}.png" style="width:16px;vertical-align:middle"> 
                ${file.platform.toUpperCase()}
            </td>
            <td style="padding: 10px;">${file.user_id}</td>
            <td style="padding: 10px;">
                <span class="status-badge ${file.type === 'wish' ? 'wishlist' : 'completed'}">
                    ${file.type === 'wish' ? '想看' : '看过'}
                </span>
            </td>
            <td style="padding: 10px;">${(file.size / 1024).toFixed(1)} KB</td>
            <td style="padding: 10px;">${file.mtime}</td>
            <td style="padding: 10px;">
                <button class="btn btn-sm btn-outline" onclick="previewBackup('${file.filename}')">👀 查看</button>
                <button class="btn btn-sm btn-outline danger" onclick="deleteBackup('${file.filename}')">🗑️ 删除</button>
            </td>
        </tr>
    `).join('');
}

function triggerBackupDouban(type = 'done') {
    const input = document.getElementById('backups-douban-id');
    const userId = input ? input.value.trim() : '';
    if (!userId) {
        alert('请输入好友豆瓣ID');
        return;
    }

    const typeText = type === 'wish' ? '想看' : '看过';
    if (window.socket) {
        window.log(`🚀 开始备份好友 ${userId} 的豆瓣${typeText}数据...`, 'info');
        if (type === 'wish') {
            window.socket.emit('fetch_wish', { platform: 'douban', user_id: userId });
        } else {
            window.socket.emit('fetch_data', { platform: 'douban', user_id: userId });
        }
        // Refresh list after a delay
        setTimeout(() => loadBackupsList(), 5000);
    }
}

function previewBackup(filename) {
    if (window.socket) window.socket.emit('get_backup_content', { filename });
    document.getElementById('backup-preview-panel').style.display = 'block';
    document.getElementById('preview-filename').textContent = filename;
    document.getElementById('backup-preview-list').innerHTML = '<div style=\"padding:20px;text-align:center\">加载中...</div>';
}

function renderBackupPreview(data) {
    const listEl = document.getElementById('backup-preview-list');
    if (!listEl || !data || !data.records) {
        console.error('Backup preview: missing elements or data', data);
        return;
    }

    if (data.records.length === 0) {
        listEl.innerHTML = '<div style=\"padding:20px;text-align:center;color:var(--text-secondary)\">该文件暂无数据</div>';
        return;
    }

    let html = data.records.map(movie => {
        const title = movie.Title || movie.title || 'Unknown';
        const rating = movie['Your Rating'] || movie.Rating || movie['Douban Rating'] || 0;
        const poster = getSafeImageUrl(movie['Cover URL'] || movie.poster_url || '/static/images/default_poster.png');
        return `
         <div class=\"movie-card compact\">
            <div class=\"movie-poster-wrapper\">
                <img src=\"${poster}\" class=\"movie-poster\" loading=\"lazy\" referrerpolicy=\"no-referrer\" 
                     onerror=\"this.src='/static/images/default_poster.png'\">
                <div class=\"movie-rating-badge\">${rating}</div>
            </div>
            <div class=\"movie-info\">
               <div class=\"movie-title\" title=\"${title}\">${title}</div>
            </div>
         </div>
        `;
    }).join('');

    listEl.innerHTML = html;
    listEl.style.display = 'grid';
    listEl.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
    listEl.style.gap = '10px';
}

function deleteBackup(filename) {
    if (confirm(`确定要删除备份文件 ${filename} 吗?`)) {
        if (window.socket) {
            window.socket.emit('delete_backup', { filename });
            // Refresh list after a short delay
            setTimeout(() => loadBackupsList(), 500);
        }
    }
}
