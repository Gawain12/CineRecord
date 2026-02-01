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
        if (this.translations[lang]) {
            this.currentLang = lang;
            localStorage.setItem('app_language', lang);
            this.applyTranslations();
            this.updateLangButton();
        }
    },

    /**
     * Toggle between zh-CN and en
     */
    toggleLanguage() {
        const newLang = this.currentLang === 'zh-CN' ? 'en' : 'zh-CN';
        this.switchLanguage(newLang);
    },

    /**
     * Apply translations to all elements with data-i18n attribute
     */
    applyTranslations() {
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.getAttribute('data-i18n');
            const translation = this.t(key);

            // Handle input placeholders
            if (element.hasAttribute('placeholder')) {
                element.setAttribute('placeholder', translation);
            } else {
                element.textContent = translation;
            }
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

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = i18n;
}
