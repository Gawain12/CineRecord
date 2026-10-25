/**
 * CineRecord Hub - Internationalization (i18n)
 * Bilingual support: Chinese (zh-CN) and English (en)
 */

const i18n = {
    currentLang: 'zh-CN',

    translations: {
        'zh-CN': {
            // Navigation
            'nav.dashboard': '🏠 总览',
            'nav.accounts': '🔐 账户',
            'nav.data': '📊 数据',
            'nav.wishlist': '✨ 想看',
            'nav.backups': '📁 备份',
            'nav.sync': '🔄 同步',
            'nav.settings': '⚙️ 设置',

            // Sidebar
            'sidebar.platform_status': '平台状态',
            'sidebar.logs': '运行日志',

            // Accounts Page
            'accounts.title': '账户中心',
            'accounts.subtitle': '管理平台账户、查看数据、配置认证',
            'account.status.connected': '已连接',
            'account.status.disconnected': '未连接',
            'account.status.external': '外部平台',
            'account.test': '测试',
            'account.update': '更新数据',
            'account.fetch_wish': '获取想看',
            'account.logout': '退出',
            'account.save_all': '保存所有配置',
            'account.view_profile': '查看主页 →',
            'btn.save_all': '保存所有设置',
            'btn.cancel': '取消',
            'trakt.authorize_btn': '授权 Trakt',
            'tmdb.connect_btn': '连接 TMDB',

            // Data Page
            'data.title': '我的影片库',
            'data.subtitle': '跨平台统一视图，自动按电影去重',
            'data.export': '导出',
            'data.fetch_label': '从平台更新',
            'data.filter.all': '共有',
            'data.filter.douban_only': '豆瓣独占',
            'data.filter.imdb_only': 'IMDB独占',
            'data.filter.trakt_only': 'Trakt独占',
            'data.filter.letterboxd_only': 'Letterboxd独占',
            'data.filter.tmdb_only': 'TMDB独占',
            'data.empty': '暂无数据',
            'data.empty_hint': '请先从上方获取平台数据',
            'data.prev_page': '上一页',
            'data.next_page': '下一页',

            // Sync Page
            'sync.title': '数据同步',
            'sync.subtitle': '在不同平台间同步评分数据',
            'sync.step1': '同步方向',
            'sync.step2': '操作',
            'sync.source': '源平台',
            'sync.target': '目标平台',
            'sync.preview': '预览',
            'sync.execute': '执行同步',
            'sync.hint.full': '全量同步：同步所有看过的电影及评分',
            'sync.results.success': '成功',
            'sync.results.failed': '失败',
            'sync.results.skipped': '跳过',

            // Wishlist Page
            'wishlist.title': '想看清单',
            'wishlist.subtitle': '汇集各平台的想看数据',

            // Backups Page
            'backups.title': '好友备份',
            'backups.subtitle': '管理为您好友备份的数据文件',

            // Settings Page
            'settings.title': '设置',
            'settings.subtitle': '配置应用程序和账户认证',
            'settings.auth': '账户认证',
            'settings.auth.desc': 'Cookie 配置用于 API 认证，请在浏览器开发者工具中获取',
            'settings.data_storage': '数据存储',
            'settings.data_dir': '数据目录',
            'settings.auto_backup': '自动备份',
            'settings.auto_backup.desc': '每次同步前自动备份数据',
            'settings.sync_settings': '同步设置',
            'settings.sync_delay': '同步延迟',
            'settings.sync_delay.desc': '每次评分操作之间的等待时间',
            'settings.timestamps': '各平台数据时间戳',
            'settings.timestamps.desc': '显示各平台最新记录时间，清除后下次获取将执行全量更新',
            'settings.about': '关于',

            // Sync Page  
            'sync.header': '🔄 数据同步',
            'sync.direction_header': '同步方向',
            'sync.source_label': '源平台',
            'sync.target_label': '目标平台',
            'sync.options_header': '同步选项',
            'sync.advanced_options': '⚙️ 高级同步选项',
            'sync.mode.only_new': '🆕 仅新增',
            'sync.mode.overwrite': '✏️ 覆盖已有',
            'sync.mode_help': '💡 仅新增: 只同步目标没有的电影 | 覆盖已有: 更新目标已有的评分',
            'sync.default_rating': '无评分时使用默认值:',
            'sync.default_rating_range': '(1-10)',
            'sync.full_sync_hint': '全量同步：同步所有看过的电影及评分',
            'sync.actions_header': '操作',
            'sync.preview_btn': '🔍 预览',
            'sync.execute_btn': '✨ 执行同步',
            'sync.scheduled_tasks_header': '定时同步任务',
            'sync.scheduled_tasks_desc': '自动执行跨平台评分同步，支持 Cron 表达式定制',
            'sync.no_tasks': '📭 暂无定时任务',
            'sync.no_tasks_hint': '点击下方"新建任务"开始',
            'sync.add_task_btn': '➕ 新建任务',
            'sync.task_list_tab': '任务列表',
            'sync.task_logs_tab': '执行日志',
            'sync.task_list_all': '全部任务',
            'sync.task_logs_header': '📋 执行日志',
            'sync.task_logs_empty': '暂无日志',
            'sync.task_form_title': '新建定时任务',
            'sync.task_form_placeholder': '选择或新建一个任务',
            'sync.task_name': '任务名称',
            'sync.form.task_name': '任务名称',
            'sync.form.task_name_placeholder': '例如: 每日豆瓣到IMDB同步',
            'sync.form.sync_direction': '同步方向',
            'sync.form.schedule': '执行计划',
            'sync.form.cron_placeholder': 'Cron 表达式: 分 时 日 月 周',
            'sync.schedule_preset_daily_2': '每日2点',
            'sync.schedule_preset_every_6h': '每6小时',
            'sync.schedule_preset_weekly_sun': '每周日',
            'sync.form.enable_task': '启用任务',
            'sync.form.save_task': '保存任务',

            // Common Buttons
            'btn.open': '打开',
            'btn.cancel': '取消',
            'btn.clear': '清除',
            'btn.test': '测试连接',
            'btn.connect': '连接',
            'btn.disconnect': '断开连接',
            'btn.login': '登录',
            'btn.fetch': '获取数据',
            'btn.sync': '同步',
            'btn.export': '导出',
            'btn.upload': '上传',
            'btn.auto_login': '自动登录',
            'btn.config_cookie': '配置Cookie',
            'btn.authorize': '授权',
            'btn.sync_cookiecloud': '同步 CookieCloud',
            'btn.sync_to_letterboxd': '同步到 Letterboxd',
            'btn.export_from_lb': '从LB导出',
            'btn.upload_diary': '上传 diary.csv',

            // Account card prompts
            'prompt.click_login': '点击登录以获取您的观影数据',
            'prompt.connect_trakt': '连接 Trakt 同步您的观影记录',
            'prompt.connect_tmdb': '连接 TMDB 获取电影信息',
            'prompt.import_letterboxd': '导入您的 Letterboxd 观影记录',
            'prompt.auth_help': '点击下方按钮进行设备授权，然后在 Trakt 网站输入验证码',
            'prompt.tmdb_help': '需要 TMDB API Key，可在',
            'prompt.tmdb_settings': 'TMDB 设置',
            'prompt.tmdb_get': '获取',

            // Letterboxd guide
            'letterboxd.guide.step1': '点击下方"导出数据"前往 Letterboxd 导出页面',
            'letterboxd.guide.step2': '下载 ZIP 文件并解压，找到',
            'letterboxd.guide.step3': '点击"上传 diary.csv"导入您的观影记录',
            'letterboxd.imported': 'Letterboxd 数据已导入',
            'letterboxd.source': '来源: diary.csv',

            // Trakt auth
            'trakt.custom_api': '使用自定义 API 凭据',
            'trakt.custom_api_help': '如需使用自己的 Trakt API，请在',
            'trakt.api_app_page': 'Trakt API 应用页面',
            'trakt.create_app': '创建应用',
            'trakt.client_id': 'Client ID',
            'trakt.client_secret': 'Client Secret',
            'trakt.optional_builtin': '可选 - 留空使用内置凭据',
            'trakt.visit_and_enter': '请访问以下链接并输入代码:',
            'trakt.waiting_auth': '等待授权中...',

            // TMDB
            'tmdb.api_key': 'API Key (v3 auth)',
            'tmdb.enter_key': '输入您的 TMDB API Key',
            'tmdb.api_help': '有了 API Key 后即可搜索电影信息。如需同步评分，需进一步授权获取 Session。',
            'tmdb.need_session': '需要完成用户授权才能同步评分',
            'tmdb.auth_session': '授权同步评分',

            // Stats labels
            'stats.watched': '看过',
            'stats.wish': '想看',
            'stats.doing': '在看',
            'stats.ratings': '已评分',
            'stats.watchlist': '待看',
            'stats.lists': '列表',
            'stats.movies_watched': '已观看',
            'stats.movies_rated': '已评分',
            'stats.imported': '已看',
            'stats.reviewed': '已评',

            // Settings page
            'settings.auth_header': '账户认证',
            'settings.auth_desc': 'Cookie 配置用于 API 认证，请在浏览器开发者工具中获取',
            'settings.cookiecloud_header': 'CookieCloud',
            'settings.cookiecloud_desc': '从 CookieCloud 手动同步浏览器里的登录态到本地配置，不会覆盖用户 ID。',
            'settings.cookiecloud_host': '服务地址',
            'settings.cookiecloud_uuid': 'UUID',
            'settings.cookiecloud_password': '密码',
            'settings.cookiecloud_host_placeholder': '例如 https://cookie.example.com',
            'settings.cookiecloud_uuid_placeholder': '输入 CookieCloud UUID',
            'settings.cookiecloud_password_placeholder': '输入 CookieCloud 密码',
            'settings.cookiecloud_idle': '未同步',
            'settings.douban_cookie': '豆瓣 Cookie',
            'settings.imdb_cookie': 'IMDB Cookie',
            'settings.not_configured': '未配置',
            'settings.user_id': '用户 ID',
            'settings.placeholder_douban_id': '例如 gawaintan',
            'settings.placeholder_imdb_id': '例如 ur12345678',
            'settings.paste_cookie': '粘贴豆瓣 Cookie...',
            'settings.paste_imdb_cookie': '粘贴 IMDB Cookie...',
            'settings.data_dir_header': '数据目录',
            'settings.data_dir_label': '数据目录',
            'settings.auto_backup_label': '自动备份',
            'settings.auto_backup_desc': '每次同步前自动备份数据',
            'settings.sync_settings_header': '同步设置',
            'settings.sync_delay_label': '同步延迟',
            'settings.sync_delay_desc': '每次评分操作之间的等待时间',
            'settings.clear_timestamps_header': '清除时间戳',
            'settings.clear_timestamps_desc': '清除后将重新从头获取数据',
            'settings.about_header': '关于',
            'settings.about_desc': '一站式电影数据同步工具',
            'settings.about_security': '本地运行，保障您的数据安全。',

            // Status
            'status.not_fetched': '未获取',
            'status.loading': '加载中...',
            'status.connecting': '连接中...',
            'status.authorizing': '授权中...',
            'status.seconds': '秒',
        },

        'en': {
            // Navigation
            'nav.dashboard': '🏠 Dashboard',
            'nav.accounts': '🔐 Accounts',
            'nav.data': '📊 Data',
            'nav.wishlist': '✨ Wishlist',
            'nav.backups': '📁 Backups',
            'nav.sync': '🔄 Sync',
            'nav.settings': '⚙️ Settings',

            // Sidebar
            'sidebar.platform_status': 'Platform Status',
            'sidebar.logs': 'Execution Logs',

            // Accounts Page
            'accounts.title': 'Account Center',
            'accounts.subtitle': 'Manage platform accounts, view data, configure authentication',
            'account.status.connected': 'Connected',
            'account.status.disconnected': 'Disconnected',
            'account.status.external': 'External Platform',
            'account.test': 'Test',
            'account.update': 'Update Data',
            'account.fetch_wish': 'Fetch Wishlist',
            'account.logout': 'Logout',
            'account.save_all': 'Save All Settings',
            'account.view_profile': 'View Profile →',
            'trakt.authorize_btn': 'Authorize Trakt',
            'tmdb.connect_btn': 'Connect TMDB',

            // Data Page
            'data.title': 'My Library',
            'data.subtitle': 'Unified cross-platform view with auto-deduplication',
            'data.export': 'Export',
            'data.fetch_label': 'Refresh from',
            'data.filter.all': 'All',
            'data.filter.douban_only': 'Douban Only',
            'data.filter.imdb_only': 'IMDB Only',
            'data.filter.trakt_only': 'Trakt Only',
            'data.filter.letterboxd_only': 'Letterboxd Only',
            'data.filter.tmdb_only': 'TMDB Only',
            'data.empty': 'No Data',
            'data.empty_hint': 'Please fetch platform data from above',
            'data.prev_page': 'Previous',
            'data.next_page': 'Next',

            // Sync Page
            'sync.title': 'Data Synchronization',
            'sync.subtitle': 'Sync ratings between different platforms',
            'sync.step1': 'Sync Direction',
            'sync.step2': 'Actions',
            'sync.source': 'Source Platform',
            'sync.target': 'Target Platform',
            'sync.preview': 'Preview',
            'sync.execute': 'Execute Sync',
            'sync.hint.full': 'Full Sync: Sync all watched movies and ratings',
            'sync.results.success': 'Success',
            'sync.results.failed': 'Failed',
            'sync.results.skipped': 'Skipped',

            // Wishlist Page
            'wishlist.title': 'Wishlist',
            'wishlist.subtitle': 'Aggregated wishlist from all platforms',

            // Backups Page
            'backups.title': 'Backups',
            'backups.subtitle': 'Manage data files backed up for friends',

            // Settings Page
            'settings.title': 'Settings',
            'settings.subtitle': 'Configure application and account authentication',
            'settings.auth': 'Account Authentication',
            'settings.auth.desc': 'Cookie configuration for API authentication, obtain from browser developer tools',
            'settings.data_storage': 'Data Storage',
            'settings.data_dir': 'Data Directory',
            'settings.auto_backup': 'Auto Backup',
            'settings.auto_backup.desc': 'Automatically backup data before each sync',
            'settings.sync_settings': 'Sync Settings',
            'settings.sync_delay': 'Sync Delay',
            'settings.sync_delay.desc': 'Wait time between each rating operation',
            'settings.timestamps': 'Platform Data Timestamps',
            'settings.timestamps.desc': 'Shows latest record time for each platform, clearing will trigger full update',
            'settings.about': 'About',

            // Sync Page
            'sync.header': '🔄 Data Synchronization',
            'sync.direction_header': 'Sync Direction',
            'sync.source_label': 'Source Platform',
            'sync.target_label': 'Target Platform',
            'sync.options_header': 'Sync Options',
            'sync.advanced_options': '⚙️ Advanced Options',
            'sync.mode.only_new': '🆕 New Only',
            'sync.mode.overwrite': '✏️ Overwrite Existing',
            'sync.mode_help': '💡 New Only: sync items missing in target | Overwrite: update ratings in target',
            'sync.default_rating': 'Use default rating when missing:',
            'sync.default_rating_range': '(1-10)',
            'sync.full_sync_hint': 'Full Sync: Synchronize all watched movies and ratings',
            'sync.actions_header': 'Actions',
            'sync.preview_btn': '🔍 Preview',
            'sync.execute_btn': '✨ Execute Sync',
            'sync.scheduled_tasks_header': 'Scheduled Sync Tasks',
            'sync.scheduled_tasks_desc': 'Automatically execute cross-platform rating sync with Cron expression customization',
            'sync.no_tasks': '📭 No Scheduled Tasks',
            'sync.no_tasks_hint': 'Click "New Task" below to get started',
            'sync.add_task_btn': '➕ New Task',
            'sync.task_list_tab': 'Task List',
            'sync.task_logs_tab': 'Execution Logs',
            'sync.task_list_all': 'All Tasks',
            'sync.task_logs_header': '📋 Execution Logs',
            'sync.task_logs_empty': 'No logs yet',
            'sync.task_form_title': 'New Scheduled Task',
            'sync.task_form_placeholder': 'Select or create a task',
            'sync.task_name': 'Task Name',
            'sync.form.task_name': 'Task Name',
            'sync.form.task_name_placeholder': 'e.g.: Daily Douban to IMDB Sync',
            'sync.form.sync_direction': 'Sync Direction',
            'sync.form.schedule': 'Schedule',
            'sync.form.cron_placeholder': 'Cron Expression: min hour day month weekday',
            'sync.schedule_preset_daily_2': 'Daily 2 AM',
            'sync.schedule_preset_every_6h': 'Every 6 Hours',
            'sync.schedule_preset_weekly_sun': 'Weekly Sun',
            'sync.form.enable_task': 'Enable Task',
            'sync.form.save_task': 'Save Task',

            // Common Buttons
            'btn.open': 'Open',
            'btn.cancel': 'Cancel',
            'btn.clear': 'Clear',
            'btn.test': 'Test Connection',
            'btn.connect': 'Connect',
            'btn.disconnect': 'Disconnect',
            'btn.login': 'Login',
            'btn.fetch': 'Fetch Data',
            'btn.sync': 'Sync',
            'btn.export': 'Export',
            'btn.upload': 'Upload',
            'btn.auto_login': 'Auto Login',
            'btn.config_cookie': 'Configure Cookie',
            'btn.authorize': 'Authorize',
            'btn.sync_cookiecloud': 'Sync CookieCloud',
            'btn.sync_to_letterboxd': 'Sync to Letterboxd',
            'btn.export_from_lb': 'Export from LB',
            'btn.upload_diary': 'Upload diary.csv',

            // Account card prompts
            'prompt.click_login': 'Click to login and fetch your movie data',
            'prompt.connect_trakt': 'Connect Trakt to sync your viewing history',
            'prompt.connect_tmdb': 'Connect TMDB to get movie information',
            'prompt.import_letterboxd': 'Import your Letterboxd viewing history',
            'prompt.auth_help': 'Click the button below for device authorization, then enter the code on Trakt website',
            'prompt.tmdb_help': 'TMDB API Key required, get it from',
            'prompt.tmdb_settings': 'TMDB Settings',
            'prompt.tmdb_get': 'get',

            // Letterboxd guide
            'letterboxd.guide.step1': 'Click "Export Data" below to go to Letterboxd export page',
            'letterboxd.guide.step2': 'Download the ZIP file, extract it, and find',
            'letterboxd.guide.step3': 'Click "Upload diary.csv" to import your viewing history',
            'letterboxd.imported': 'Letterboxd Data Imported',
            'letterboxd.source': 'Source: diary.csv',

            // Trakt auth
            'trakt.custom_api': 'Use Custom API Credentials',
            'trakt.custom_api_help': 'To use your own Trakt API, create an app at',
            'trakt.api_app_page': 'Trakt API Applications',
            'trakt.create_app': 'create an app',
            'trakt.client_id': 'Client ID',
            'trakt.client_secret': 'Client Secret',
            'trakt.optional_builtin': 'Optional - leave empty to use built-in credentials',
            'trakt.visit_and_enter': 'Please visit the link below and enter the code:',
            'trakt.waiting_auth': 'Waiting for authorization...',

            // TMDB
            'tmdb.api_key': 'API Key (v3 auth)',
            'tmdb.enter_key': 'Enter your TMDB API Key',
            'tmdb.api_help': 'With API Key you can search movie info. To sync ratings, you need further session authorization.',
            'tmdb.need_session': 'User authorization required to sync ratings',
            'tmdb.auth_session': 'Authorize Rating Sync',

            // Stats labels
            'stats.watched': 'Watched',
            'stats.wish': 'Wishlist',
            'stats.doing': 'Watching',
            'stats.ratings': 'Ratings',
            'stats.watchlist': 'Watchlist',
            'stats.lists': 'Lists',
            'stats.movies_watched': 'Watched',
            'stats.movies_rated': 'Rated',
            'stats.imported': 'Watched',
            'stats.reviewed': 'Reviewed',

            // Settings page
            'settings.douban_cookie': 'Douban Cookie',
            'settings.imdb_cookie': 'IMDB Cookie',
            'settings.not_configured': 'Not Configured',
            'settings.user_id': 'User ID',
            'settings.placeholder_douban_id': 'e.g. gawaintan',
            'settings.placeholder_imdb_id': 'e.g. ur12345678',
            'settings.paste_cookie': 'Paste Douban Cookie...',
            'settings.paste_imdb_cookie': 'Paste IMDB Cookie...',
            // Settings page
            'settings.auth_header': 'Account Authentication',
            'settings.auth_desc': 'Cookie configuration for API authentication, get it from browser developer tools',
            'settings.cookiecloud_header': 'CookieCloud',
            'settings.cookiecloud_desc': 'Manually sync browser login cookies from CookieCloud into local config without overwriting user IDs.',
            'settings.cookiecloud_host': 'Server URL',
            'settings.cookiecloud_uuid': 'UUID',
            'settings.cookiecloud_password': 'Password',
            'settings.cookiecloud_host_placeholder': 'e.g. https://cookie.example.com',
            'settings.cookiecloud_uuid_placeholder': 'Enter CookieCloud UUID',
            'settings.cookiecloud_password_placeholder': 'Enter CookieCloud password',
            'settings.cookiecloud_idle': 'Not Synced',
            'settings.data_dir_header': 'Data Directory',
            'settings.data_dir_label': 'Data Directory',
            'settings.auto_backup_label': 'Auto Backup',
            'settings.auto_backup_desc': 'Automatically backup data before each sync',
            'settings.sync_settings_header': 'Sync Settings',
            'settings.sync_delay_label': 'Sync Delay',
            'settings.sync_delay_desc': 'Wait time between each rating operation',
            'settings.clear_timestamps_header': 'Clear Timestamps',
            'settings.clear_timestamps_desc': 'After clearing, data will be re-fetched from the beginning',
            'settings.about_header': 'About',
            'settings.about_desc': 'All-in-one movie data synchronization tool',
            'settings.about_security': 'Running locally to ensure your data security.',

            // Status
            'status.not_fetched': 'Not Fetched',
            'status.loading': 'Loading...',
            'status.connecting': 'Connecting...',
            'status.authorizing': 'Authorizing...',
            'status.seconds': 'seconds',
        }
    },

    /**
     * Initialize i18n system
     */
    init() {
        // Load saved language preference
        const savedLang = localStorage.getItem('app_language');
        if (savedLang && this.translations[savedLang]) {
            this.currentLang = savedLang;
        }

        // Apply translations to the page
        this.applyTranslations();

        // Update language button
        this.updateLangButton();
    },

    /**
     * Get translation for a key
     */
    t(key, fallback = key) {
        const translation = this.translations[this.currentLang]?.[key];
        return translation || fallback;
    },

    /**
     * Switch language
     */
    switchLanguage(lang) {
        this.currentLang = (lang === 'en' || lang === 'en-US') ? 'en' : 'zh-CN';
        localStorage.setItem('app_language', this.currentLang);
        localStorage.setItem('cinerecord_lang', this.currentLang);
        document.documentElement.lang = this.currentLang;
        this.applyTranslations();
        this.updateLangButton();
        window.dispatchEvent(new CustomEvent('languagechange', { detail: { lang: this.currentLang } }));
        if (typeof updateCounts === 'function') updateCounts();
        if (typeof renderLibrary === 'function') renderLibrary();
        if (typeof renderWishlist === 'function') renderWishlist();
        if (typeof renderTasks === 'function') renderTasks();
        if (typeof renderScheduledTasks === 'function') renderScheduledTasks();
        if (typeof renderPlatformGrid === 'function') renderPlatformGrid();
    },

    /**
     * Toggle between zh-CN and en
     */
    toggleLanguage() {
        const newLang = this.currentLang === 'zh-CN' ? 'en' : 'zh-CN';
        this.switchLanguage(newLang);
    },

    /**
     * Apply translations to all elements with data-i18n attribute and known UI components
     */
    applyTranslations() {
        const isEn = this.currentLang === 'en';

        // 1. Data attributes
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.getAttribute('data-i18n');
            const translation = this.t(key);
            if (element.hasAttribute('placeholder')) {
                element.setAttribute('placeholder', translation);
            } else {
                element.textContent = translation;
            }
        });

        // 2. Navigation Tabs (Header & Bottom)
        const navMap = {
            'dashboard': isEn ? 'Dashboard' : '总览',
            'data': isEn ? 'Library' : '数据',
            'sync': isEn ? 'Sync' : '同步',
            'wishlist': isEn ? 'Wishlist' : '想看',
            'settings': isEn ? 'Settings' : '设置',
        };
        const navIcons = {
            'dashboard': '🏠',
            'data': '📊',
            'sync': '🔄',
            'wishlist': '✨',
            'settings': '⚙️',
        };
        document.querySelectorAll('.nav-tabs .nav-tab').forEach(tab => {
            const target = tab.dataset.tab;
            if (navMap[target]) {
                tab.textContent = `${navIcons[target]} ${navMap[target]}`;
            }
        });
        document.querySelectorAll('.bottom-nav .nav-tab').forEach(tab => {
            const target = tab.dataset.tab;
            if (navMap[target]) {
                const textSpan = tab.querySelector('span:not(.icon)');
                if (textSpan) textSpan.textContent = navMap[target];
            }
        });

        // 2.1 Tab Main Headers
        const dashH2 = document.querySelector('#tab-dashboard .content-header h2');
        if (dashH2) dashH2.textContent = isEn ? 'Dashboard' : '总览';
        const dataH2 = document.querySelector('#tab-data .content-header h2');
        if (dataH2) dataH2.textContent = isEn ? 'Movie Library' : '我的影片库';
        const syncH2 = document.querySelector('#tab-sync .content-header h2');
        if (syncH2) syncH2.textContent = isEn ? 'Data Sync' : '数据同步';
        const wishH2 = document.querySelector('#tab-wishlist .content-header h2');
        if (wishH2) wishH2.textContent = isEn ? 'Wishlist' : '想看管理';
        const setH2 = document.querySelector('#tab-settings .content-header h2');
        if (setH2) setH2.textContent = isEn ? 'Settings & Management' : '设置与管理';

        const dashP = document.querySelector('#tab-dashboard .content-header p');
        if (dashP) dashP.textContent = isEn ? 'Quickly check status and perform common actions' : '快速查看状态并执行常用操作';
        const dataP = document.querySelector('#tab-data .content-header p');
        if (dataP) dataP.textContent = isEn ? 'Unified cross-platform view with automated deduplication' : '跨平台统一视图，自动按电影去重';
        const syncP = document.querySelector('#tab-sync .content-header p');
        if (syncP) syncP.textContent = isEn ? 'Cross-platform movie & TV rating sync & automated scheduler' : '跨平台影视评分实时同步与定时任务调度';
        const wishP = document.querySelector('#tab-wishlist .content-header p');
        if (wishP) wishP.textContent = isEn ? 'Cross-platform wishlist aggregation · Single-site wishlist & diff matrix' : '跨平台全景想看聚合 · 平台单站想看与查漏矩阵';
        const setP = document.querySelector('#tab-settings .content-header p');
        if (setP) setP.textContent = isEn ? 'Platform credentials, data storage & automation preferences' : '平台账号授权、数据存储与自动化偏好';

        // 3. Sidebar headings and stat labels
        const sidebarTitles = document.querySelectorAll('.sidebar-title');
        if (sidebarTitles.length >= 2) {
            sidebarTitles[0].textContent = isEn ? 'PLATFORM STATUS' : '平台状态';
            sidebarTitles[1].textContent = isEn ? 'SYSTEM LOGS' : '运行日志';
        }

        const doubanSummaryName = document.querySelector('#summary-douban .summary-name');
        if (doubanSummaryName) {
            const idSpan = document.getElementById('summary-id-douban');
            doubanSummaryName.innerHTML = '';
            doubanSummaryName.appendChild(document.createTextNode(isEn ? 'Douban ' : '豆瓣 '));
            if (idSpan) doubanSummaryName.appendChild(idSpan);
        }

        // Sidebar summary stats
        document.querySelectorAll('.account-summary-card .summary-stats').forEach(el => {
            if (isEn) {
                el.textContent = el.textContent
                    .replace(/看过/g, 'Watched')
                    .replace(/想看/g, 'Wishlist')
                    .replace(/加载中/g, 'Loading...')
                    .replace(/导入入口保留/g, 'CSV Import Only')
                    .replace(/已填写配置，等待测试连接/g, 'Configured, awaiting test')
                    .replace(/授权已过期，请重新登录/g, 'Auth expired, please re-login')
                    .replace(/未连接 · 本地 SQLite 模式/g, 'Not connected · Local SQLite mode');
            } else {
                el.textContent = el.textContent
                    .replace(/Watched/g, '看过')
                    .replace(/Wishlist/g, '想看')
                    .replace(/Loading\.\.\./g, '加载中')
                    .replace(/CSV Import Only/g, '导入入口保留')
                    .replace(/Configured, awaiting test/g, '已填写配置，等待测试连接')
                    .replace(/Auth expired, please re-login/g, '授权已过期，请重新登录')
                    .replace(/Not connected · Local SQLite mode/g, '未连接 · 本地 SQLite 模式');
            }
        });

        // 4. Subfilter chips
        const chipAll = document.querySelector('[data-subfilter="all"]');
        if (chipAll) {
            const count = chipAll.querySelector('.chip-count')?.textContent || '0';
            chipAll.innerHTML = `${isEn ? 'All Items' : '全部条目'} <span class="chip-count" id="count-all">${count}</span>`;
        }
        const chipShared = document.querySelector('[data-subfilter="shared"]');
        if (chipShared) {
            const count = chipShared.querySelector('.chip-count')?.textContent || '0';
            chipShared.innerHTML = `🔗 ${isEn ? 'Multi-Platform' : '多平台共有'} <span class="chip-count" id="count-shared">${count}</span>`;
        }
        const chipSingle = document.querySelector('[data-subfilter="single"]');
        if (chipSingle) {
            const count = chipSingle.querySelector('.chip-count')?.textContent || '0';
            chipSingle.innerHTML = `${isEn ? 'Single-Platform' : '仅单平台有'} <span class="chip-count" id="count-single">${count}</span>`;
        }

        const wishAll = document.querySelector('[data-wishlist-subfilter="all"]');
        if (wishAll) {
            const count = wishAll.querySelector('.chip-count')?.textContent || '0';
            wishAll.innerHTML = `${isEn ? 'All Wishlist' : '全部想看'} <span class="chip-count" id="wishlist-count-all">${count}</span>`;
        }

        // 5. View modes & toolbar buttons
        const modeUnified = document.querySelector('[data-platform-mode="unified"], [data-library-mode="unified"]');
        if (modeUnified) modeUnified.innerHTML = `🌐 ${isEn ? 'Unified View' : '全景聚合'}`;
        const modePlatform = document.querySelector('[data-platform-mode="platform"], [data-library-mode="platform"]');
        if (modePlatform) modePlatform.innerHTML = `📱 ${isEn ? 'Single Platform' : '平台单站'}`;
        const modeDiff = document.querySelector('[data-platform-mode="diff"], [data-library-mode="diff"]');
        if (modeDiff) modeDiff.innerHTML = `🔍 ${isEn ? 'Diff Matrix' : '查漏补缺'}`;

        const gridBtn = document.getElementById('library-view-grid');
        if (gridBtn) gridBtn.innerHTML = `🔲 ${isEn ? 'Grid' : '网格'}`;
        const listBtn = document.getElementById('library-view-list');
        if (listBtn) listBtn.innerHTML = `📋 ${isEn ? 'List' : '列表'}`;
        const exportBtn = document.getElementById('export-library-btn');
        if (exportBtn) exportBtn.innerHTML = `📥 ${isEn ? 'Export' : '导出'}`;
        const importBtn = document.getElementById('import-legacy-btn');
        if (importBtn) importBtn.textContent = isEn ? 'Import CSV' : '导入旧版 CSV';

        // 6. Common Action Buttons
        document.querySelectorAll('.rust-test-btn').forEach(btn => {
            btn.textContent = isEn ? '✅ Test' : '✅ 测试连接';
        });
        document.querySelectorAll('.rust-logout-btn').forEach(btn => {
            btn.textContent = isEn ? '🚪 Logout' : '🚪 退出连接';
        });

        // 7. Page Titles & Subtitles
        const headerTitleMap = {
            '总览': isEn ? 'Dashboard' : '总览',
            'Dashboard': isEn ? 'Dashboard' : '总览',
            'Overview': isEn ? 'Dashboard' : '总览',
            '我的影片库': isEn ? 'Movie Library' : '我的影片库',
            'Movie Library': isEn ? 'Movie Library' : '我的影片库',
            'My Movie Library': isEn ? 'Movie Library' : '我的影片库',
            '数据同步': isEn ? 'Data Sync' : '数据同步',
            'Data Sync': isEn ? 'Data Sync' : '数据同步',
            '想看清单': isEn ? 'Wishlist' : '想看清单',
            'Wishlist': isEn ? 'Wishlist' : '想看清单',
            '设置与管理': isEn ? 'Settings & Management' : '设置与管理',
            'Settings & Management': isEn ? 'Settings & Management' : '设置与管理'
        };
        document.querySelectorAll('.content-header h2').forEach(h2 => {
            const text = h2.textContent.trim();
            if (headerTitleMap[text]) h2.textContent = headerTitleMap[text];
        });

        const subtitleMap = {
            '跨平台聚合总览 · 核心数据与最近同步': isEn ? 'Cross-platform aggregated overview · Core stats & recent syncs' : '跨平台聚合总览 · 核心数据与最近同步',
            'Cross-platform aggregated overview · Core stats & recent syncs': isEn ? 'Cross-platform aggregated overview · Core stats & recent syncs' : '跨平台聚合总览 · 核心数据与最近同步',
            'Cross-platform aggregated overview & recent syncs': isEn ? 'Cross-platform aggregated overview · Core stats & recent syncs' : '跨平台聚合总览 · 核心数据与最近同步',
            '跨平台统一视图，自动按电影去重': isEn ? 'Unified cross-platform view with automated deduplication' : '跨平台统一视图，自动按电影去重',
            'Unified cross-platform view with automated deduplication': isEn ? 'Unified cross-platform view with automated deduplication' : '跨平台统一视图，自动按电影去重',
            'Unified cross-platform view with deduplication': isEn ? 'Unified cross-platform view with automated deduplication' : '跨平台统一视图，自动按电影去重',
            '跨平台想看聚合 · 单站想看与查漏补缺': isEn ? 'Cross-platform wishlist aggregation · Single-site wishlist & diff matrix' : '跨平台想看聚合 · 单站想看与查漏补缺',
            'Cross-platform wishlist aggregation · Single-site wishlist & diff matrix': isEn ? 'Cross-platform wishlist aggregation · Single-site wishlist & diff matrix' : '跨平台想看聚合 · 单站想看与查漏补缺',
            'Cross-platform wishlist aggregation & diff matrix': isEn ? 'Cross-platform wishlist aggregation · Single-site wishlist & diff matrix' : '跨平台想看聚合 · 单站想看与查漏补缺',
            '跨平台影视评分实时同步与定时任务调度': isEn ? 'Cross-platform movie & TV rating sync & automated scheduler' : '跨平台影视评分实时同步与定时任务调度',
            'Cross-platform movie & TV rating sync & automated scheduler': isEn ? 'Cross-platform movie & TV rating sync & automated scheduler' : '跨平台影视评分实时同步与定时任务调度',
            'Real-time rating sync & scheduled task scheduler': isEn ? 'Cross-platform movie & TV rating sync & automated scheduler' : '跨平台影视评分实时同步与定时任务调度',
            '账户连接、备份与系统设置': isEn ? 'Platform credentials, data storage & automation preferences' : '账户连接、备份与系统设置',
            'Platform credentials, data storage & automation preferences': isEn ? 'Platform credentials, data storage & automation preferences' : '账户连接、备份与系统设置',
            'Account connections, backups & system configuration': isEn ? 'Platform credentials, data storage & automation preferences' : '账户连接、备份与系统设置'
        };
        document.querySelectorAll('.content-header p').forEach(p => {
            const text = p.textContent.trim();
            if (subtitleMap[text]) p.textContent = subtitleMap[text];
        });

        // 8. Search Input Placeholders
        const libSearch = document.getElementById('library-search-input');
        if (libSearch) libSearch.placeholder = isEn ? '🔍 Search movie, director, actor...' : '🔍 检索电影、导演、演员...';
        const wishSearch = document.getElementById('wishlist-search-input');
        if (wishSearch) wishSearch.placeholder = isEn ? '🔍 Search wishlist movies, directors...' : '🔍 检索想看电影、导演...';

        // 9. Select Options
        const selectOptionMap = {
            '🎬 豆瓣': isEn ? '🎬 Douban' : '🎬 豆瓣',
            '⭐ IMDb': isEn ? '⭐ IMDb' : '⭐ IMDb',
            '🎯 Trakt': isEn ? '🎯 Trakt' : '🎯 Trakt',
            '🎬 TMDB': isEn ? '🎬 TMDB' : '🎬 TMDB',
            '🎨 CinePersona': isEn ? '🎨 CinePersona' : '🎨 CinePersona',
            '豆瓣': isEn ? 'Douban' : '豆瓣',
            '全部平台': isEn ? 'All Platforms' : '全部平台',
            '全部类型': isEn ? 'All Types' : '全部类型',
            '电影': isEn ? 'Movies' : '电影',
            '剧集': isEn ? 'TV Shows' : '剧集',
            '按添加时间降序': isEn ? 'Date Added (Desc)' : '按添加时间降序',
            '按评分降序': isEn ? 'Rating (High to Low)' : '按评分降序',
            '按年份降序': isEn ? 'Release Year (Desc)' : '按年份降序'
        };
        document.querySelectorAll('select option').forEach(opt => {
            const txt = opt.textContent.trim();
            if (selectOptionMap[txt]) opt.textContent = selectOptionMap[txt];
        });

        // 10. Sync Buttons & Preview
        const previewBtn = document.getElementById('preview-sync-btn');
        if (previewBtn) previewBtn.innerHTML = `🔍 ${isEn ? 'Preview' : '预览'}`;
        const runSyncBtn = document.getElementById('execute-sync-btn') || document.getElementById('run-sync-btn');
        if (runSyncBtn) runSyncBtn.innerHTML = `✨ ${isEn ? 'Execute Sync' : '执行同步'}`;
        const selectAllSync = document.getElementById('select-all-sync-btn');
        if (selectAllSync) selectAllSync.textContent = isEn ? 'Select All Executable' : '全选可执行';
        const clearSync = document.getElementById('clear-sync-btn');
        if (clearSync) clearSync.textContent = isEn ? 'Clear' : '清空';

        const advToggleSpan = document.querySelector('#toggle-advanced-sync span:last-child');
        if (advToggleSpan) {
            advToggleSpan.textContent = isEn ? '⚙️ Advanced Options' : '⚙️ 高级同步选项';
        }

        // Advanced sync options
        const syncRuleLabel = document.querySelector('#advanced-sync-options .legacy-sync-label');
        if (syncRuleLabel) syncRuleLabel.textContent = isEn ? 'Sync Rules' : '同步规则';
        const syncRadioNew = document.querySelector('input[name="rust-sync-mode"][value="new"]');
        if (syncRadioNew?.parentElement) {
            const span = syncRadioNew.parentElement.querySelector('span');
            if (span) span.textContent = isEn ? '🆕 New Items Only' : '🆕 仅新增';
        }
        const syncRadioOverwrite = document.querySelector('input[name="rust-sync-mode"][value="overwrite"]');
        if (syncRadioOverwrite?.parentElement) {
            const span = syncRadioOverwrite.parentElement.querySelector('span');
            if (span) span.textContent = isEn ? '✏️ Overwrite Existing' : '✏️ 覆盖已有';
        }

        const recentLimitLabel = document.querySelector('label[for="sync-recent-limit"]');
        if (recentLimitLabel) recentLimitLabel.textContent = isEn ? 'Recent Limit (0 for all)' : '最近条目数 (0 为全量)';

        const refreshBeforeToggle = document.querySelector('label[for="sync-refresh-before"]');
        if (refreshBeforeToggle) {
            const cb = refreshBeforeToggle.querySelector('input');
            refreshBeforeToggle.innerHTML = '';
            if (cb) refreshBeforeToggle.appendChild(cb);
            refreshBeforeToggle.appendChild(document.createTextNode(isEn ? ' Refresh platforms before preview' : ' 预览前也刷新双方'));
        }

        const defaultRatingToggle = document.querySelector('label[for="sync-default-rating-enabled"]');
        if (defaultRatingToggle) {
            const cb = defaultRatingToggle.querySelector('input');
            defaultRatingToggle.innerHTML = '';
            if (cb) defaultRatingToggle.appendChild(cb);
            defaultRatingToggle.appendChild(document.createTextNode(isEn ? ' Use default rating if unrated' : ' 未评分使用默认分'));
        }

        const syncNote = document.querySelector('.rust-compact-note');
        if (syncNote) {
            syncNote.textContent = isEn
                ? 'Preview uses local cache for speed; executing sync will refresh both platforms to prevent overwriting existing ratings.'
                : '预览默认使用本地库以保持快速；执行同步会强制刷新双方后再次确认，避免旧数据覆盖目标平台已有评分。';
        }

        const brandName = (platform) => ({
            douban: isEn ? 'Douban' : '豆瓣',
            imdb: 'IMDb',
            trakt: 'Trakt',
            tmdb: 'TMDB',
            letterboxd: 'Letterboxd',
            cinepersona: 'CinePersona',
        }[platform] || platform || '');

        // 11. Wishlist Buttons
        const refreshWishlistBtns = document.querySelectorAll('.rust-wishlist-btn');
        refreshWishlistBtns.forEach(btn => {
            const platform = btn.dataset.platform;
            const img = btn.querySelector('img');
            const pName = brandName(platform);
            btn.innerHTML = '';
            if (img) btn.appendChild(img);
            const sp = /^[A-Za-z]/.test(pName) ? ' ' : '';
            btn.appendChild(document.createTextNode(isEn ? ` Refresh ${pName} Wishlist` : ` 刷新${sp}${pName}${sp}想看`));
        });

        const wishUnifiedBtn = document.querySelector('[data-wishlist-mode="unified"]');
        if (wishUnifiedBtn) wishUnifiedBtn.innerHTML = `🌐 ${isEn ? 'Unified Wishlist' : '全景聚合想看'}`;
        const wishPlatformBtn = document.querySelector('[data-wishlist-mode="platform"]');
        if (wishPlatformBtn) wishPlatformBtn.innerHTML = `📱 ${isEn ? 'Single Platform' : '平台单站想看'}`;
        const wishDiffBtn = document.querySelector('[data-wishlist-mode="diff"]');
        if (wishDiffBtn) wishDiffBtn.innerHTML = `🔍 ${isEn ? 'Wishlist Diff Matrix' : '想看查漏矩阵'}`;

        // 12. Scheduled Tasks & Sync Form Text Maps
        const syncTextMap = {
            '定时同步任务': isEn ? 'Scheduled Tasks' : '定时同步任务',
            'Scheduled Tasks': isEn ? 'Scheduled Tasks' : '定时同步任务',
            '⏰ 定时同步任务': isEn ? '⏰ Scheduled Tasks' : '⏰ 定时同步任务',
            '⏰ Scheduled Tasks': isEn ? '⏰ Scheduled Tasks' : '⏰ 定时同步任务',
            '自动后台同步': isEn ? 'Automated background sync' : '自动后台同步',
            'Automated background sync': isEn ? 'Automated background sync' : '自动后台同步',
            '任务列表': isEn ? 'Task List' : '任务列表',
            'Task List': isEn ? 'Task List' : '任务列表',
            '执行日志': isEn ? 'Execution Logs' : '执行日志',
            'Execution Logs': isEn ? 'Execution Logs' : '执行日志',
            '全部任务': isEn ? 'All Tasks' : '全部任务',
            'All Tasks': isEn ? 'All Tasks' : '全部任务',
            '任务表单': isEn ? 'Task Form' : '任务表单',
            'Task Form': isEn ? 'Task Form' : '任务表单',
            '任务名称': isEn ? 'Task Name' : '任务名称',
            'Task Name': isEn ? 'Task Name' : '任务名称',
            '源平台': isEn ? 'Source Platform' : '源平台',
            'Source Platform': isEn ? 'Source Platform' : '源平台',
            '目标平台': isEn ? 'Target Platform' : '目标平台',
            'Target Platform': isEn ? 'Target Platform' : '目标平台',
            'Cron 表达式': isEn ? 'Cron Expression' : 'Cron 表达式',
            'Cron Expression': isEn ? 'Cron Expression' : 'Cron 表达式',
            '每日 2 点': isEn ? 'Daily 2 AM' : '每日 2 点',
            'Daily 2 AM': isEn ? 'Daily 2 AM' : '每日 2 点',
            '每 6 小时': isEn ? 'Every 6 Hours' : '每 6 小时',
            'Every 6 Hours': isEn ? 'Every 6 Hours' : '每 6 小时',
            '每周日': isEn ? 'Weekly Sunday' : '每周日',
            'Weekly Sunday': isEn ? 'Weekly Sunday' : '每周日',
            '启用任务': isEn ? 'Enable Task' : '启用任务',
            'Enable Task': isEn ? 'Enable Task' : '启用任务',
            '保存任务': isEn ? 'Save Task' : '保存任务',
            'Save Task': isEn ? 'Save Task' : '保存任务',
            '收起': isEn ? 'Close' : '收起',
            'Close': isEn ? 'Close' : '收起',
            '立即运行': isEn ? 'Run Now' : '立即运行',
            'Run Now': isEn ? 'Run Now' : '立即运行',
            '编辑': isEn ? 'Edit' : '编辑',
            'Edit': isEn ? 'Edit' : '编辑',
            '暂停': isEn ? 'Pause' : '暂停',
            'Pause': isEn ? 'Pause' : '暂停',
            '删除': isEn ? 'Delete' : '删除',
            'Delete': isEn ? 'Delete' : '删除',
            '已启用': isEn ? 'Enabled' : '已启用',
            'Enabled': isEn ? 'Enabled' : '已启用',
            '刷新': isEn ? 'Refresh' : '刷新',
            'Refresh': isEn ? 'Refresh' : '刷新',
            '数据同步': isEn ? 'Data Sync' : '数据同步',
            'Data Sync': isEn ? 'Data Sync' : '数据同步',
            '🔄 数据同步': isEn ? '🔄 Data Sync' : '🔄 数据同步',
            '🔄 Data Sync': isEn ? '🔄 Data Sync' : '🔄 数据同步',
            '同步流向': isEn ? 'Sync Flow' : '同步流向',
            'Sync Flow': isEn ? 'Sync Flow' : '同步流向',
            '高级同步选项': isEn ? 'Advanced Options' : '高级同步选项',
            'Advanced Options': isEn ? 'Advanced Options' : '高级同步选项',
            '▶ ⚙ 高级同步选项': isEn ? '▶ ⚙ Advanced Options' : '▶ ⚙ 高级同步选项',
            '▼ ⚙ 高级同步选项': isEn ? '▼ ⚙ Advanced Options' : '▼ ⚙ 高级同步选项',
            '▶ ⚙ Advanced Options': isEn ? '▶ ⚙ Advanced Options' : '▶ ⚙ 高级同步选项',
            '▼ ⚙ Advanced Options': isEn ? '▼ ⚙ Advanced Options' : '▼ ⚙ 高级同步选项',
            '跨平台影视评分实时同步与定时任务调度': isEn ? 'Cross-platform movie & TV rating sync & automated scheduler' : '跨平台影视评分实时同步与定时任务调度',
            'Cross-platform movie & TV rating sync & automated scheduler': isEn ? 'Cross-platform movie & TV rating sync & automated scheduler' : '跨平台影视评分实时同步与定时任务调度'
        };
        document.querySelectorAll('#tab-sync *').forEach(el => {
            if (el.children.length === 0 && el.textContent.trim()) {
                const txt = el.textContent.trim();
                if (syncTextMap[txt]) el.textContent = syncTextMap[txt];
            }
        });

        // 13. Action status toast
        const actionStatus = document.getElementById('action-status');
        if (actionStatus && actionStatus.textContent) {
            if (isEn) {
                actionStatus.textContent = actionStatus.textContent
                    .replace(/同步预览已更新[ ·]*可执行\s*(\d+)\s*\/\s*(\d+)\s*项/g, 'Sync preview updated · Executable $1 / $2 items')
                    .replace(/正在生成同步预览\.\.\./g, 'Generating sync preview...')
                    .replace(/正在执行同步\.\.\./g, 'Executing sync...')
                    .replace(/同步执行完成[ ·]*成功\s*(\d+)[ ·]*跳过\s*(\d+)[ ·]*失败\s*(\d+)/g, 'Sync completed · Success $1 · Skipped $2 · Failed $3');
            }
        }

        const syncPreviewTitle = document.querySelector('#sync-preview-card h3');
        if (syncPreviewTitle) syncPreviewTitle.textContent = isEn ? 'Sync Preview' : '同步预览';
        const selectAllSyncBtn = document.getElementById('select-all-sync-btn');
        if (selectAllSyncBtn) selectAllSyncBtn.textContent = isEn ? 'Select All Executable' : '全选可执行';
        const clearSyncBtn = document.getElementById('clear-sync-selection-btn');
        if (clearSyncBtn) clearSyncBtn.textContent = isEn ? 'Clear' : '清空';

        const taskFormPlaceholder = document.querySelector('#task-form-placeholder .rust-compact-note');
        if (taskFormPlaceholder) taskFormPlaceholder.textContent = isEn ? 'Select or create a task' : '选择或新建一个任务';

        const syncSummaryText = document.getElementById('sync-summary-text');
        if (syncSummaryText && syncSummaryText.textContent) {
            if (isEn) {
                syncSummaryText.textContent = syncSummaryText.textContent
                    .replace(/共\s*(\d+)\s*项/g, '$1 items total')
                    .replace(/尚未生成同步预览/g, 'No sync preview generated yet')
                    .replace(/正在生成同步预览/g, 'Generating sync preview...');
            } else {
                syncSummaryText.textContent = syncSummaryText.textContent
                    .replace(/(\d+)\s*items total/g, '共 $1 项')
                    .replace(/No sync preview generated yet/g, '尚未生成同步预览')
                    .replace(/Generating sync preview\.\.\./g, '正在生成同步预览');
            }
        }

        const syncSelectionSummary = document.getElementById('sync-selection-summary');
        if (syncSelectionSummary && syncSelectionSummary.textContent) {
            if (isEn) {
                syncSelectionSummary.textContent = syncSelectionSummary.textContent
                    .replace(/已选\s*(\d+)\s*\/\s*(\d+)/g, 'Selected $1 / $2')
                    .replace(/待预览/g, 'Awaiting Preview')
                    .replace(/刷新中/g, 'Refreshing...');
            } else {
                syncSelectionSummary.textContent = syncSelectionSummary.textContent
                    .replace(/Selected\s*(\d+)\s*\/\s*(\d+)/g, '已选 $1 / $2')
                    .replace(/Awaiting Preview/g, '待预览')
                    .replace(/Refreshing\.\.\./g, '刷新中');
            }
        }

        const syncMetricMap = {
            '源库': isEn ? 'Source' : '源库',
            'Source': isEn ? 'Source' : '源库',
            '目标库': isEn ? 'Target' : '目标库',
            'Target': isEn ? 'Target' : '目标库',
            '可执行': isEn ? 'Executable' : '可执行',
            'Executable': isEn ? 'Executable' : '可执行',
            '已跳过': isEn ? 'Skipped' : '已跳过',
            'Skipped': isEn ? 'Skipped' : '已跳过'
        };
        document.querySelectorAll('.stat-label').forEach(label => {
            const text = label.textContent.trim();
            if (syncMetricMap[text]) label.textContent = syncMetricMap[text];
        });

        // 14. Settings Sub-tabs and Platform Cards
        const settingsSubTabs = {
            '账户': isEn ? 'Accounts' : '账户',
            'Accounts': isEn ? 'Accounts' : '账户',
            '备份': isEn ? 'Backups' : '备份',
            'Backups': isEn ? 'Backups' : '备份',
            '系统': isEn ? 'System' : '系统',
            'System': isEn ? 'System' : '系统'
        };
        document.querySelectorAll('.settings-sub-tab').forEach(tab => {
            const raw = tab.textContent || '';
            const icon = raw.match(/[🔑💾⚙️\u{1F300}-\u{1F9FF}]/u)?.[0] || '';
            const txt = raw.replace(/[🔑💾⚙️\u{1F300}-\u{1F9FF}\s]/gu, '').trim();
            if (settingsSubTabs[txt]) tab.textContent = `${icon} ${settingsSubTabs[txt]}`.trim();
        });

        const statLabelMap = {
            '看过': isEn ? 'Watched' : '看过',
            'Watched': isEn ? 'Watched' : '看过',
            '想看': isEn ? 'Wishlist' : '想看',
            'Wishlist': isEn ? 'Wishlist' : '想看',
            '在看': isEn ? 'Watching' : '在看',
            'Watching': isEn ? 'Watching' : '在看',
            '已评分': isEn ? 'Rated' : '已评分',
            'Rated': isEn ? 'Rated' : '已评分',
            '列表': isEn ? 'Lists' : '列表',
            'Lists': isEn ? 'Lists' : '列表'
        };
        document.querySelectorAll('.account-stat-label').forEach(label => {
            const txt = label.textContent.trim();
            if (statLabelMap[txt]) label.textContent = statLabelMap[txt];
        });

        const traktStart = document.querySelector('[data-action="trakt-start"]');
        if (traktStart) traktStart.textContent = isEn ? '🔐 Start OAuth' : '🔐 开始 OAuth';
        const traktPoll = document.querySelector('[data-action="trakt-poll"]');
        if (traktPoll) traktPoll.textContent = isEn ? '🔄 Check Now' : '🔄 立即检查';
        const tmdbStart = document.querySelector('[data-action="tmdb-start"]');
        if (tmdbStart) tmdbStart.textContent = isEn ? '🌐 Start Auth' : '🌐 开始授权';
        const tmdbComplete = document.querySelector('[data-action="tmdb-complete"]');
        if (tmdbComplete) tmdbComplete.textContent = isEn ? '✅ Complete Auth' : '✅ 完成授权';

        document.querySelectorAll('.rust-test-btn').forEach(btn => {
            btn.textContent = isEn ? '✅ Test' : '✅ 测试连接';
        });
        document.querySelectorAll('.rust-logout-btn').forEach(btn => {
            btn.textContent = isEn ? '🚪 Logout' : '🚪 退出连接';
        });

        document.querySelectorAll('.status-badge').forEach(badge => {
            if (isEn) {
                badge.textContent = badge.textContent
                    .replace(/● 已连接/g, '● Connected')
                    .replace(/● 未配置/g, '● Not Configured')
                    .replace(/● 待验证/g, '● Pending')
                    .replace(/● 验证失败/g, '● Validation Failed')
                    .replace(/● 授权已过期/g, '● Auth Expired')
                    .replace(/已连接/g, 'Connected')
                    .replace(/未配置/g, 'Not Configured');
            } else {
                badge.textContent = badge.textContent
                    .replace(/● Connected/g, '● 已连接')
                    .replace(/● Not Configured/g, '● 未配置')
                    .replace(/● Pending/g, '● 待验证')
                    .replace(/● Validation Failed/g, '● 验证失败')
                    .replace(/● Auth Expired/g, '● 授权已过期')
                    .replace(/Connected/g, '已连接')
                    .replace(/Not Configured/g, '未配置');
            }
        });

        document.querySelectorAll('.account-profile-meta').forEach(meta => {
            if (isEn) {
                meta.textContent = meta.textContent
                    .replace(/上次同步: /g, 'Last synced: ')
                    .replace(/等待验证/g, 'Pending verification')
                    .replace(/授权已过期，请重新登录/g, 'Auth expired, please re-login');
            } else {
                meta.textContent = meta.textContent
                    .replace(/Last synced: /g, '上次同步: ')
                    .replace(/Pending verification/g, '等待验证')
                    .replace(/Auth expired, please re-login/g, '授权已过期，请重新登录');
            }
        });

        const settingsTextMap = {
            '豆瓣电影': isEn ? 'Douban Movie' : '豆瓣电影',
            'Douban Movie': isEn ? 'Douban Movie' : '豆瓣电影',
            '豆瓣主页 ↗': isEn ? 'Douban ↗' : '豆瓣主页 ↗',
            'IMDb 主页 ↗': isEn ? 'IMDb ↗' : 'IMDb 主页 ↗',
            '开始 OAuth': isEn ? 'Start OAuth' : '开始 OAuth',
            '立即检查': isEn ? 'Check Now' : '立即检查',
            '开始授权': isEn ? 'Start Auth' : '开始授权',
            '完成授权': isEn ? 'Finish Auth' : '完成授权'
        };
        document.querySelectorAll('#tab-settings *').forEach(el => {
            if (el.children.length === 0 && el.textContent.trim()) {
                const txt = el.textContent.trim();
                if (settingsTextMap[txt]) el.textContent = settingsTextMap[txt];
            }
        });

        // 15. Dashboard Cards & Guide
        const dashTitle = document.querySelector('#tab-dashboard .content-header p');
        if (dashTitle) dashTitle.textContent = isEn ? 'Quickly check status and perform common actions' : '快速查看状态并执行常用操作';
        const dashLibBtn = document.querySelector('.dashboard-actions button[data-tab="data"]');
        if (dashLibBtn) dashLibBtn.textContent = isEn ? '🔄 Refresh Library' : '🔄 刷新影片库';
        const dashWishBtn = document.querySelector('.dashboard-actions button[data-tab="wishlist"]');
        if (dashWishBtn) dashWishBtn.textContent = isEn ? '✨ Refresh Wishlist' : '✨ 刷新想看';
        const dashSetBtn = document.querySelector('.dashboard-actions button[data-tab="settings"]');
        if (dashSetBtn) dashSetBtn.textContent = isEn ? '⚙️ Settings & Backups' : '⚙️ 设置与备份';

        const dashTextMap = {
            '快速操作': isEn ? 'Quick Actions' : '快速操作',
            'Quick Actions': isEn ? 'Quick Actions' : '快速操作',
            '使用指引': isEn ? 'Quick Guide' : '使用指引',
            'Quick Guide': isEn ? 'Quick Guide' : '使用指引'
        };
        document.querySelectorAll('#tab-dashboard *').forEach(el => {
            if (el.children.length === 0 && el.textContent.trim()) {
                const txt = el.textContent.trim();
                if (dashTextMap[txt]) el.textContent = dashTextMap[txt];
            }
        });
        document.querySelectorAll('#tab-dashboard .guide-step, #tab-dashboard li, #tab-dashboard p, #tab-dashboard div').forEach(el => {
            if (el.children.length === 0 && el.textContent.trim()) {
                if (isEn) {
                    el.textContent = el.textContent
                        .replace(/在「数据」查看评分库与同步工具/g, 'View rating library & sync tools in Library')
                        .replace(/在「想看」聚合多平台片单/g, 'Aggregate multi-platform wishlists in Wishlist')
                        .replace(/在「设置」管理账户、备份与下载站点/g, 'Manage accounts, backups & sites in Settings');
                } else {
                    el.textContent = el.textContent
                        .replace(/View rating library & sync tools in Library/g, '在「数据」查看评分库与同步工具')
                        .replace(/Aggregate multi-platform wishlists in Wishlist/g, '在「想看」聚合多平台片单')
                        .replace(/Manage accounts, backups & sites in Settings/g, '在「设置」管理账户、备份与下载站点');
                }
            }
        });

        // 16. Library & Wishlist Buttons & Badges
        document.querySelectorAll('#tab-data .rust-fetch-btn').forEach(btn => {
            const platform = btn.dataset.platform;
            const img = btn.querySelector('img');
            const pName = brandName(platform);
            btn.innerHTML = '';
            if (img) btn.appendChild(img);
            btn.appendChild(document.createTextNode(` ${pName}`));
            const sp = /^[A-Za-z]/.test(pName) ? ' ' : '';
            btn.title = isEn ? `Re-fetch watched/ratings from ${pName}` : `从${sp}${pName}${sp}重新抓取看过与评分`;
        });
        document.querySelectorAll('#import-letterboxd-library-btn').forEach(btn => {
            btn.title = isEn ? 'Upload diary.csv / ratings.csv from your Letterboxd export' : '上传 Letterboxd 导出的 diary.csv / ratings.csv';
        });

        const mergeBtn = document.getElementById('manual-merge-btn') || document.querySelector('[data-action="merge"]');
        if (mergeBtn) mergeBtn.textContent = isEn ? 'Merge Records' : '合并数据';
        const doubanFilterBtn = document.querySelector('.platform-tab-btn[data-platform-tab="douban"]');
        if (doubanFilterBtn) {
            const img = doubanFilterBtn.querySelector('img');
            const cnt = doubanFilterBtn.querySelector('.tab-count')?.textContent || '0';
            doubanFilterBtn.innerHTML = '';
            if (img) doubanFilterBtn.appendChild(img);
            doubanFilterBtn.appendChild(document.createTextNode(isEn ? ' Douban ' : ' 豆瓣 '));
            const span = document.createElement('span');
            span.className = 'tab-count';
            span.id = 'count-tab-douban';
            span.textContent = cnt;
            doubanFilterBtn.appendChild(span);
        }

        const exportSelect = document.getElementById('export-source');
        if (exportSelect) {
            const optMerged = exportSelect.querySelector('option[value="merged"]');
            if (optMerged) optMerged.textContent = isEn ? 'All platforms (merged)' : '全部平台（合并）';
            exportSelect.title = isEn ? 'Choose which data to export' : '选择要导出的数据来源';
            const optDouban = exportSelect.querySelector('option[value="douban"]');
            if (optDouban) optDouban.textContent = isEn ? 'Douban' : '豆瓣';
        }
        const exportLibBtn = document.getElementById('export-library-btn');
        if (exportLibBtn) exportLibBtn.textContent = isEn ? '📥 Export' : '📥 导出';

        const wishViewGrid = document.getElementById('wishlist-view-grid');
        if (wishViewGrid) wishViewGrid.innerHTML = `🔲 ${isEn ? 'Grid' : '网格'}`;
        const wishViewList = document.getElementById('wishlist-view-list');
        if (wishViewList) wishViewList.innerHTML = `📋 ${isEn ? 'List' : '列表'}`;
        const importLetterboxdBtn = document.getElementById('import-letterboxd-legacy-btn') || document.getElementById('import-letterboxd-wishlist-btn');
        if (importLetterboxdBtn) {
            importLetterboxdBtn.textContent = isEn ? 'Import Letterboxd watchlist.csv' : '导入 Letterboxd watchlist.csv';
            importLetterboxdBtn.title = isEn ? 'Upload watchlist.csv from your Letterboxd export' : '上传 Letterboxd 导出的 watchlist.csv';
        }

        const filterUnmatchedInput = document.getElementById('wishlist-filter-unmatched');
        if (filterUnmatchedInput?.parentElement) {
            const parent = filterUnmatchedInput.parentElement;
            parent.innerHTML = '';
            parent.appendChild(filterUnmatchedInput);
            parent.appendChild(document.createTextNode(isEn ? ' Only Missing from Library' : ' 仅未在个人片库中'));
        }

        const enableTaskLabel = document.querySelector('label[for="scheduled-task-enabled"]') || document.querySelector('#scheduled-task-enabled')?.parentElement;
        if (enableTaskLabel) {
            const cb = enableTaskLabel.querySelector('input');
            enableTaskLabel.innerHTML = '';
            if (cb) enableTaskLabel.appendChild(cb);
            enableTaskLabel.appendChild(document.createTextNode(isEn ? ' Enable Task' : ' 启用任务'));
        }

        // 17. Platform Badges and Tags across all tabs
        document.querySelectorAll('.source-pill, .rust-tag, .platform-badge, .status-pill').forEach(tag => {
            const txt = tag.textContent.trim();
            if (txt === '豆瓣') tag.textContent = isEn ? 'Douban' : '豆瓣';
            if (txt === 'Douban') tag.textContent = isEn ? 'Douban' : '豆瓣';
            if (txt === '● 已连接') tag.textContent = isEn ? '● Connected' : '● 已连接';
            if (txt === '已连接') tag.textContent = isEn ? 'Connected' : '已连接';
        });

        // 18. Card Meta Director / Cast / Play strings
        document.querySelectorAll('.movie-item, .wishlist-card, .rust-movie-card').forEach(card => {
            card.querySelectorAll('.movie-meta, .wishlist-meta, .rust-movie-meta').forEach(meta => {
                if (isEn) {
                    meta.innerHTML = meta.innerHTML
                        .replace(/想看于/g, 'Added on')
                        .replace(/导演:/g, 'Director:')
                        .replace(/主演:/g, 'Cast:')
                        .replace(/评分/g, 'Rating')
                        .replace(/暂无详细信息/g, 'No details available');
                } else {
                    meta.innerHTML = meta.innerHTML
                        .replace(/Added on/g, '想看于')
                        .replace(/Director:/g, '导演:')
                        .replace(/Cast:/g, '主演:')
                        .replace(/Rating/g, '评分')
                        .replace(/No details available/g, '暂无详细信息');
                }
            });
            card.querySelectorAll('.source-badge, .source-pill').forEach(badge => {
                if (isEn) {
                    badge.textContent = badge.textContent.replace(/豆瓣/g, 'Douban');
                } else {
                    badge.textContent = badge.textContent.replace(/Douban/g, '豆瓣');
                }
            });
            card.querySelectorAll('.play-btn, .action-btn, button').forEach(btn => {
                if (btn.textContent.includes('播放')) {
                    btn.textContent = isEn ? '▶ Play' : '▶ 播放';
                }
            });
        });
    },

    /**
     * Update language button text
     */
    updateLangButton() {
        const langBtn = document.getElementById('lang-btn');
        if (langBtn) {
            langBtn.textContent = this.currentLang === 'zh-CN' ? 'EN' : '中';
        }
    }
};

window.i18n = i18n;

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = i18n;
}
