const API_BASE = "/api/v2";
const LIBRARY_PAGE_SIZE = 20;
const WISHLIST_FETCH_LIMIT = 2000;
const WISHLIST_PAGE_SIZE = 24;
const PLATFORM_IDS = ["douban", "imdb", "trakt", "letterboxd", "tmdb"];
const DEFAULT_DOWNLOAD_SITES = [
    { id: "ptp", label: "PTP", template: "https://passthepopcorn.me/torrents.php?searchstr={imdbid}" },
    { id: "kg", label: "KG", template: "https://karagarga.in/browse.php?search={imdbid}&search_type=imdb" },
    { id: "hdroute", label: "路", template: "http://hdroute.org/browse.php?dp=0&add=0&action=s&or=1&imdb={imdbno}" },
    { id: "tik", label: "Tik", template: "https://www.cinematik.net/torrents?imdbid={imdbno}&perPage=25&imdbId={imdbno}" },
    { id: "in", label: "IN", template: "https://nzbs.in/search?query=imdb:{imdbid}" },
    { id: "hdb", label: "HDB", template: "https://hdbits.org/browse.php?search={imdbid}" },
    { id: "i2", label: "I2", template: "https://nzbs.in/search?query={search_name}" },
    { id: "imdb", label: "IMDb", template: "https://www.imdb.com/title/{imdbid}/" },
    { id: "btn", label: "妞", template: "https://broadcasthe.net/torrents.php?action=advanced&imdb={imdbid}" },
    { id: "omg", label: "OMG", template: "https://omgwtfnzbs.org/browse?search={imdbid}&cat=default&sort=3" },
    { id: "fl", label: "FL", template: "https://filelist.io/browse.php?search={imdbid}" },
    { id: "bhd", label: "BHD", template: "https://beyond-hd.me/torrents?imdb={imdbid}" },
    { id: "blu", label: "BLU", template: "https://blutopia.cc/torrents?imdbid={imdbno}&perPage=25&imdbId={imdbno}" },
    { id: "cg", label: "CG", template: "http://cinemageddon.net/browse.php?search={imdbid}&proj=0&descr=1" },
    { id: "mt", label: "MT", template: "https://kp.m-team.cc/browse?keyword={search_name}&search_area=4&search_mode=0" },
    { id: "sc", label: "SC", template: "https://secret-cinema.pw/torrents.php?action=advanced&searchsubmit=1&filter_cat=1&cataloguenumber={imdbid}" },
    { id: "ttg", label: "套", template: "https://totheglory.im/browse.php?search_field=imdb{imdbno}&c=M" },
    { id: "nc", label: "nC", template: "https://ncore.pro/torrents.php?mire={imdbid}&miben=imdb&tipus=all_own" },
    { id: "hdt", label: "HDT", template: "https://hd-torrents.org/torrents.php?&search={imdbid}&active=0" },
    { id: "douban", label: "豆", template: "https://search.douban.com/movie/subject_search?search_text={imdbid}" },
    { id: "zmk", label: "ZMK", template: "http://so.zimuku.org/search?q={imdbid}" },
    { id: "op", label: "OP", template: "https://www.opensubtitles.org/en/search2/sublanguageid-eng/moviename-{search_name}" },
    { id: "sh", label: "SH", template: "https://subhd.tv/search/{imdbid}" },
    { id: "ops", label: "OPS", template: "https://orpheus.network/torrents.php?searchstr={search_name}" },
    { id: "bm", label: "BM", template: "https://www.blu-ray.com/search/?quicksearch=1&quicksearch_country=all&quicksearch_keyword={search_name}&section=bluraymovies" },
    { id: "lb", label: "LB", template: "https://letterboxd.com/imdb/{imdbid}" },
    { id: "of", label: "OF", template: "https://www.ofdb.de/suchergebnis/?{search_name}" },
    { id: "az", label: "AZ", template: "https://avistaz.to/torrents?in=1&search={search_name}" },
    { id: "tb", label: "TB", template: "https://thetvdb.com/search?query={search_name}" },
    { id: "ade", label: "ADE", template: "https://audiences.me/torrents.php?incldead=0&spstate=0&inclbookmarked=0&search={imdbid}&search_area=4&search_mode=0" },
];

const state = {
    currentConfig: null,
    overview: null,
    tasks: [],
    platforms: [],
    traktDeviceAuth: null,
    traktAuthPollTimer: null,
    library: {
        filter: "all",
        page: 1,
        total: 0,
        items: [],
        view: localStorage.getItem("cinerecord_library_view_v3") || "list",
        platformsInitialized: false,
    },
    wishlist: {
        items: [],
        filteredItems: [],
        page: 1,
        view: localStorage.getItem("cinerecord_legacy_wishlist_view") || "list",
        sources: new Set(["douban", "imdb", "trakt", "tmdb", "letterboxd"]),
        onlyUnmatched: localStorage.getItem("cinerecord_wishlist_unmatched") === "1",
    },
    sync: {
        preview: null,
        result: null,
        selectedTargetIds: new Set(),
        liveItems: [],
    },
    scheduled: {
        tasks: [],
        logs: [],
        editingId: null,
    },
    backups: {
        items: [],
        selected: null,
        previewKind: "watched",
    },
    downloadSites: {
        enabledIds: new Set(),
        customSites: [],
        deletedDefaults: new Set(),
    },
    logs: {
        recent: new Map(),
        lastSseErrorAt: 0,
    },
    theme: localStorage.getItem("theme") || "dark",
};

const ui = {
    healthStatus: document.getElementById("health-status"),
    eventsLog: document.getElementById("events-log"),
    configForm: document.getElementById("config-form"),
    libraryList: document.getElementById("library-list"),
    libraryEmpty: document.getElementById("library-empty"),
    libraryPagination: document.getElementById("library-pagination"),
    libraryPageInfo: document.getElementById("lib-page-info"),
    libraryInsightBar: document.getElementById("library-insight-bar"),
    libPrevBtn: document.getElementById("lib-prev-btn"),
    libNextBtn: document.getElementById("lib-next-btn"),
    wishlistList: document.getElementById("wishlist-list"),
    wishlistEmpty: document.getElementById("wishlist-empty"),
    wishlistPagination: document.getElementById("wishlist-pagination"),
    wishlistPageInfo: document.getElementById("wishlist-page-info"),
    wishlistPrevBtn: document.getElementById("wishlist-prev-btn"),
    wishlistNextBtn: document.getElementById("wishlist-next-btn"),
    tasksList: document.getElementById("tasks-list"),
    dashboardTaskList: document.getElementById("dashboard-task-list"),
    dashboardPlatformGrid: document.getElementById("dashboard-platform-grid"),
    syncPreviewList: document.getElementById("sync-preview-list"),
    syncPreviewEmpty: document.getElementById("sync-preview-empty"),
    syncSummaryText: document.getElementById("sync-summary-text"),
    syncSelectionSummary: document.getElementById("sync-selection-summary"),
    syncLiveProgress: document.getElementById("sync-live-progress"),
    syncLiveProgressBar: document.getElementById("sync-live-progress-bar"),
    syncLiveProgressText: document.getElementById("sync-live-progress-text"),
    selectAllSyncBtn: document.getElementById("select-all-sync-btn"),
    clearSyncSelectionBtn: document.getElementById("clear-sync-selection-btn"),
    tmdbAuthStatus: document.getElementById("tmdb-auth-status"),
    traktAuthStatus: document.getElementById("trakt-auth-status"),
    traktAuthPanel: document.getElementById("trakt-auth-panel"),
    traktAuthCode: document.getElementById("trakt-auth-code"),
    traktAuthCopy: document.getElementById("trakt-auth-copy"),
    traktAuthLink: document.getElementById("trakt-auth-link"),
    traktAuthHint: document.getElementById("trakt-auth-hint"),
    cookieCloudStatus: document.getElementById("cookiecloud-sync-status"),
    configSaveStatus: document.getElementById("config-save-status"),
    actionStatus: document.getElementById("action-status"),
    scheduledTasksList: document.getElementById("scheduled-tasks-list"),
    scheduledTasksEmpty: document.getElementById("scheduled-tasks-empty"),
    scheduledTaskForm: document.getElementById("scheduled-task-form"),
    scheduledTaskFormPanel: document.getElementById("scheduled-task-form-panel"),
    backupsList: document.getElementById("backups-list"),
    backupsEmpty: document.getElementById("backups-empty"),
    backupsSummary: document.getElementById("backups-summary"),
    backupPreviewPanel: document.getElementById("backup-preview-panel"),
    backupPreviewList: document.getElementById("backup-preview-list"),
    friendBackupForm: document.getElementById("friend-backup-form"),
    friendBackupStatus: document.getElementById("friend-backup-status"),
    systemInfoGrid: document.getElementById("system-info-grid"),
    mobileMenuBtn: document.getElementById("mobile-menu-btn"),
    mobileSidebarOverlay: document.getElementById("mobile-sidebar-overlay"),
    sidebar: document.querySelector(".main-layout-sidebar"),
};

function $(selector, root = document) {
    return root.querySelector(selector);
}

function $$(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
}

async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });
    if (!response.ok) {
        const text = await response.text();
        let message = text || `HTTP ${response.status}`;
        try {
            const json = JSON.parse(text);
            message = json.error || json.message || message;
        } catch (_error) {
            // Keep text body
        }
        throw new Error(message);
    }
    return response.json();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function normalizeImdbId(rawValue) {
    const value = String(rawValue || "").trim();
    if (!value) return "";
    if (value.startsWith("tt")) return value;
    if (/^\d+$/.test(value)) return `tt${value}`;
    return value;
}

function buildDownloadSiteUrl(template, tokens) {
    if (!template) return "";
    let url = template;
    if (url.includes("{imdbid}")) {
        if (!tokens.imdbid) return "";
        url = url.replaceAll("{imdbid}", encodeURIComponent(tokens.imdbid));
    }
    if (url.includes("{imdbno}")) {
        if (!tokens.imdbno) return "";
        url = url.replaceAll("{imdbno}", encodeURIComponent(tokens.imdbno));
    }
    if (url.includes("{search_name}")) {
        if (!tokens.search_name) return "";
        url = url.replaceAll("{search_name}", encodeURIComponent(tokens.search_name));
    }
    return url;
}

function getDownloadTokens(item) {
    const imdbid = normalizeImdbId(item?.identifiers?.imdb || item?.imdb_id || "");
    const imdbno = imdbid.startsWith("tt") ? imdbid.slice(2) : "";
    const search_name = [item?.title || "", item?.year || ""].filter(Boolean).join(" ").trim();
    return { imdbid, imdbno, search_name };
}

function activeDownloadSites() {
    const defaults = DEFAULT_DOWNLOAD_SITES.filter(
        (site) => !state.downloadSites.deletedDefaults.has(site.id) && state.downloadSites.enabledIds.has(site.id)
    );
    const customs = (state.downloadSites.customSites || []).filter(
        (site) => site?.label && site?.template && site.enabled !== false
    );
    return [...defaults, ...customs];
}

function buildDownloadLinks(item) {
    const tokens = getDownloadTokens(item);
    return activeDownloadSites()
        .map((site) => {
            const url = buildDownloadSiteUrl(site.template, tokens);
            return url ? { label: site.label, url } : null;
        })
        .filter(Boolean);
}

function isSensitiveKey(key) {
    const lower = String(key || "").toLowerCase();
    if (!lower) return false;
    if (lower === "cookie_names") return false;
    return ["cookie", "password", "secret", "token", "session", "api_key"].some((part) => lower.includes(part));
}

function redactPayload(value, key = "") {
    if (Array.isArray(value)) {
        return value.map((item) => redactPayload(item, key));
    }
    if (value && typeof value === "object") {
        return Object.fromEntries(
            Object.entries(value).map(([entryKey, entryValue]) => [
                entryKey,
                isSensitiveKey(entryKey) ? "[redacted]" : redactPayload(entryValue, entryKey),
            ])
        );
    }
    if (typeof value === "string" && isSensitiveKey(key)) {
        return "[redacted]";
    }
    return value;
}

function formatDate(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN");
}

function formatShortDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
    return date.toLocaleDateString("zh-CN");
}

function platformLabel(platform) {
    return {
        douban: "豆瓣",
        imdb: "IMDb",
        trakt: "Trakt",
        tmdb: "TMDB",
        letterboxd: "Letterboxd",
    }[platform] || String(platform || "").toUpperCase();
}

function statusText(task) {
    return {
        pending: "等待中",
        running: "执行中",
        succeeded: "已完成",
        failed: "失败",
        cancelled: "已取消",
    }[task?.status] || (task?.status || "--");
}

function taskTypeLabel(kind) {
    return {
        fetch_platform: "更新看过",
        fetch_wishlist: "更新想看",
        import_legacy: "导入旧版数据",
        sync_preview: "同步预览",
        sync_execute: "执行同步",
        maintenance: "维护任务",
    }[kind] || String(kind || "任务");
}

function statusBadgeClass(configured, platformId, configPresent = false, lastValidatedAt = null) {
    if (platformId === "letterboxd") return "info";
    if (!configured && configPresent && lastValidatedAt) return "disconnected";
    if (!configured && configPresent) return "validating";
    return configured ? "connected" : "disconnected";
}

function statusBadgeText(configured, configPresent = false, lastValidatedAt = null) {
    if (configured) return "● 已连接";
    if (configPresent && lastValidatedAt) return "● 验证失败";
    if (configPresent) return "● 待验证";
    return "● 未配置";
}

function platformHint(platformId) {
    return {
        douban: "浏览器登录 / Cookie",
        imdb: "浏览器登录 / Cookie",
        trakt: "设备授权 / OAuth",
        tmdb: "API Key / Session",
        letterboxd: "CSV 导入 / 映射",
    }[platformId] || "待配置";
}

function livePlatformMessage(platformId, fallback = "") {
    if (platformId === "trakt" && state.traktDeviceAuth?.user_code) {
        return `正在等待 Trakt 授权确认 · 验证码 ${state.traktDeviceAuth.user_code}`;
    }
    return fallback;
}

function platformStatusElement(platformId) {
    return {
        douban: document.getElementById("browser-auth-status-douban"),
        imdb: document.getElementById("browser-auth-status-imdb"),
        trakt: document.getElementById("trakt-card-status"),
        tmdb: document.getElementById("tmdb-card-status"),
    }[platformId] || null;
}

function platformMetaElement(platformId) {
    return document.getElementById(`${platformId}-join-date`);
}

function defaultPlatformStatus(platformId, config = state.currentConfig) {
    const platforms = config?.platforms || {};
    if (platformId === "douban") {
        if (platforms.douban?.user_id && !platforms.douban?.cookie) {
            return `豆瓣用户 ${platforms.douban.user_id} 已写入，可直接读取公开看过 / 想看；只有写入豆瓣时才需要 Cookie。`;
        }
        return platforms.douban?.cookie
            ? `豆瓣 Cookie 已写入${platforms.douban?.user_id ? ` · 用户 ${platforms.douban.user_id}` : ""}，等待验证`
            : "优先填写豆瓣 ID；需要写入豆瓣时再补 Cookie。";
    }
    if (platformId === "imdb") {
        return platforms.imdb?.cookie
            ? `IMDb Cookie 已写入${platforms.imdb?.user_id ? ` · 用户 ${platforms.imdb.user_id}` : ""}，等待验证`
            : "优先用 CookieCloud 或完整 Cookie，测试会直接验证取数能力。";
    }
    if (platformId === "trakt") {
        return platforms.trakt?.access_token
            ? "Trakt 已授权，准备验证可读取评分和同步数据。"
            : "设备授权、抓取和同步已经可用。";
    }
    if (platformId === "tmdb") {
        return platforms.tmdb?.session_id
            ? `TMDB 已配置 Session${platforms.tmdb?.username ? ` · 用户 ${platforms.tmdb.username}` : ""}，准备验证评分抓取`
            : "浏览器授权、抓取评分和同步到 Trakt 已可用。";
    }
    return platformHint(platformId);
}

function prettyStatusMessage(message) {
    if (!message) return "";
    return String(message)
        .replace("TMDB API key is valid; add a session to fetch or sync ratings", "TMDB API Key 已通过；补充 Session 后即可抓取和同步评分")
        .replace("Configure Trakt client_id and client_secret before starting device auth", "先填写 Trakt client_id 和 client_secret，再开始设备授权")
        .replace("Trakt is configured, but no access token is stored yet. Start device auth from the Rust UI.", "Trakt 基础配置已完成，但还没有 access token，请先完成设备授权")
        .replace("TMDB API key and session are valid", "TMDB API Key 和 Session 校验通过")
        .replace("Trakt OAuth token is valid", "Trakt OAuth token 校验通过");
}

function traktPollMessage(result = {}) {
    if (result.status === "success") {
        return "Trakt 授权完成，账号已绑定。";
    }
    if (result.status === "pending") {
        return "Trakt 还在等待你在授权页完成确认。";
    }
    if (result.status === "expired") {
        return result.message || "Trakt 授权码已过期，请重新开始 OAuth。";
    }
    if (result.status === "denied") {
        return result.message || "Trakt 授权被拒绝，请重新开始 OAuth。";
    }
    return `Trakt 授权状态: ${result.status || "unknown"}${result.message ? ` · ${result.message}` : ""}`;
}

function renderTraktDeviceAuthPanel() {
    if (!ui.traktAuthPanel || !ui.traktAuthCode || !ui.traktAuthCopy || !ui.traktAuthLink || !ui.traktAuthHint) return;
    const auth = state.traktDeviceAuth;
    if (!auth?.user_code || !auth?.verification_url) {
        ui.traktAuthPanel.hidden = true;
        ui.traktAuthCode.textContent = "--------";
        ui.traktAuthCopy.textContent = "点“开始 OAuth”后，这里会显示验证码。";
        ui.traktAuthLink.href = "https://trakt.tv/activate";
        ui.traktAuthHint.textContent = "开始授权后会自动检查状态，也可以手动立即检查。";
        return;
    }
    ui.traktAuthPanel.hidden = false;
    ui.traktAuthCode.textContent = auth.user_code;
    ui.traktAuthCopy.textContent = `打开 ${auth.verification_url}，输入这组验证码完成授权。`;
    ui.traktAuthLink.href = auth.verification_url;
    ui.traktAuthHint.textContent = "授权完成后会自动同步 access token；如果没变，也可以手动立即检查。";
}

function stopTraktAuthPolling() {
    if (state.traktAuthPollTimer) {
        clearInterval(state.traktAuthPollTimer);
        state.traktAuthPollTimer = null;
    }
}

function startTraktAuthPolling(intervalSeconds = 5) {
    stopTraktAuthPolling();
    const intervalMs = Math.max(3, Number(intervalSeconds) || 5) * 1000;
    state.traktAuthPollTimer = setInterval(() => {
        pollTraktAuth({ silent: true }).catch((error) => {
            stopTraktAuthPolling();
            handleError(error);
        });
    }, intervalMs);
}

function dotClass(configured, platformId) {
    if (platformId === "letterboxd") return "info";
    return configured ? "connected" : "disconnected";
}

function platformHasLocalConfig(platform, descriptor = null) {
    if (descriptor?.status?.config_present) return true;
    const platforms = state.currentConfig?.platforms || {};
    if (platform === "douban") return Boolean(platforms.douban?.user_id || platforms.douban?.cookie);
    if (platform === "imdb") return Boolean(platforms.imdb?.cookie);
    if (platform === "trakt") return Boolean(platforms.trakt?.client_id || platforms.trakt?.access_token);
    if (platform === "tmdb") return Boolean(platforms.tmdb?.api_key || platforms.tmdb?.session_id);
    return platform === "letterboxd";
}

function applyTheme() {
    document.body.classList.toggle("light-mode", state.theme === "light");
    const btn = document.getElementById("theme-btn");
    if (btn) btn.textContent = state.theme === "light" ? "☀️" : "🌙";
}

function toggleTheme() {
    state.theme = state.theme === "light" ? "dark" : "light";
    localStorage.setItem("theme", state.theme);
    applyTheme();
}

function appendLog(title, payload = {}) {
    if (!ui.eventsLog) return;
    const empty = ui.eventsLog.querySelector(".rust-empty");
    if (empty) empty.remove();
    const time = new Date().toLocaleTimeString("zh-CN");
    const safePayload = redactPayload(payload);
    let message = safePayload?.message || safePayload?.error || "";
    if (!message && safePayload?.result?.direction) {
        const result = safePayload.result;
        message = result.success_count !== undefined
            ? `${result.direction} · 成功 ${result.success_count} · 跳过 ${result.skipped_count} · 失败 ${result.failed_count}`
            : `${result.direction} · 候选 ${result.preview_count ?? 0} · 源 ${result.source_count ?? 0} · 目标 ${result.target_count ?? 0}`;
    }
    if (!message && safePayload?.direction && safePayload?.preview_count !== undefined) {
        message = `${safePayload.direction} · 候选 ${safePayload.preview_count ?? 0} · 源 ${safePayload.source_count ?? 0} · 目标 ${safePayload.target_count ?? 0}`;
    }
    if (!message && safePayload?.direction && safePayload?.success_count !== undefined) {
        message = `${safePayload.direction} · 成功 ${safePayload.success_count} · 跳过 ${safePayload.skipped_count} · 失败 ${safePayload.failed_count}`;
    }
    if (!message && safePayload?.platform && safePayload?.stored_count !== undefined) {
        message = `${platformLabel(safePayload.platform)} 已更新 ${safePayload.stored_count} 条`;
    }
    const level = safePayload?.level || title;
    const body = message ? message : compactEventMessage(title, safePayload);
    const signature = body;
    const now = Date.now();
    const lastSeen = state.logs.recent.get(signature) || 0;
    if (now - lastSeen < 6000) return;
    state.logs.recent.set(signature, now);
    if (state.logs.recent.size > 120) {
        for (const [key, value] of state.logs.recent.entries()) {
            if (now - value > 60000) state.logs.recent.delete(key);
        }
    }
    const el = document.createElement(ui.eventsLog.classList.contains("log-container-sidebar") ? "p" : "div");
    const tone = String(level).includes("error") || String(level).includes("failed")
        ? "error"
        : String(level).includes("success") || String(level).includes("completed")
          ? "success"
          : "info";
    if (el.tagName === "P") {
        el.className = tone;
        el.textContent = `[${time}] ${body}`;
    } else {
        el.className = "rust-log-entry";
        el.innerHTML = `<strong>${escapeHtml(time)} · ${escapeHtml(level)}</strong><pre>${escapeHtml(body)}</pre>`;
    }
    ui.eventsLog.prepend(el);
    const nodes = ui.eventsLog.classList.contains("log-container-sidebar")
        ? $$("p", ui.eventsLog)
        : $$(".rust-log-entry", ui.eventsLog);
    if (nodes.length > 80) {
        nodes.slice(80).forEach((node) => node.remove());
    }
}

function compactEventMessage(title, payload = {}) {
    if (payload?.task_type) {
        return `${taskTypeLabel(payload.task_type)} · ${statusText(payload)}${payload.summary ? ` · ${payload.summary}` : ""}`;
    }
    if (payload?.event_type && payload?.payload?.message) return payload.payload.message;
    if (payload?.platform && payload?.success !== undefined) {
        return `${platformLabel(payload.platform)} ${payload.success ? "验证通过" : "验证失败"}`;
    }
    const keys = Object.keys(payload || {}).filter((key) => !["payload", "id", "task_id"].includes(key));
    if (keys.length) {
        return keys.slice(0, 4).map((key) => `${key}: ${JSON.stringify(payload[key])}`).join(" · ");
    }
    return title;
}

function bindClick(id, handler) {
    const element = document.getElementById(id);
    if (element) element.addEventListener("click", handler);
}

let actionStatusTimer = null;

function setActionStatus(message, tone = "info", options = {}) {
    if (!ui.actionStatus) return;
    ui.actionStatus.textContent = message;
    ui.actionStatus.className = `action-status-bar${tone && tone !== "info" ? ` ${tone}` : ""}`;
    if (actionStatusTimer) {
        clearTimeout(actionStatusTimer);
        actionStatusTimer = null;
    }
    if (options.reset && tone !== "loading") {
        actionStatusTimer = setTimeout(() => {
            if (ui.actionStatus) {
                ui.actionStatus.textContent = "准备就绪";
                ui.actionStatus.className = "action-status-bar";
            }
        }, options.timeout ?? 4000);
    }
}

function setAppLoading(isLoading) {
    document.body.classList.toggle("app-loading", Boolean(isLoading));
}

function setButtonBusy(button, busy, text) {
    if (!button) return;
    if (busy) {
        if (!button.dataset.originalText) {
            button.dataset.originalText = button.textContent;
        }
        const nonce = `${Date.now()}-${Math.random()}`;
        button.dataset.busyNonce = nonce;
        button.disabled = true;
        button.classList.add("is-busy");
        if (text) button.textContent = text;
        setTimeout(() => {
            if (button.dataset.busyNonce === nonce) {
                setButtonBusy(button, false);
            }
        }, 45000);
    } else {
        button.disabled = false;
        button.classList.remove("is-busy");
        delete button.dataset.busyNonce;
        if (button.dataset.originalText) {
            button.textContent = button.dataset.originalText;
            delete button.dataset.originalText;
        }
    }
}

function openTab(tabName) {
    $$(".nav-tab").forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === tabName);
    });
    $$(".tab-content").forEach((tab) => {
        tab.classList.toggle("active", tab.id === `tab-${tabName}`);
    });
    closeMobileSidebar();
    document.querySelector(".content-main")?.scrollTo({ top: 0, behavior: "smooth" });
}

function openMobileSidebar() {
    ui.sidebar?.classList.add("open");
    ui.mobileSidebarOverlay?.classList.add("visible");
}

function closeMobileSidebar() {
    ui.sidebar?.classList.remove("open");
    ui.mobileSidebarOverlay?.classList.remove("visible");
}

function platformConfigId(platform) {
    const config = state.currentConfig?.platforms || {};
    if (platform === "tmdb") return config.tmdb?.username || config.tmdb?.account_id || "";
    if (platform === "trakt") return config.trakt?.access_token ? "OAuth" : "";
    if (platform === "imdb") return config.imdb?.user_id || "";
    if (platform === "douban") return config.douban?.user_id || "";
    return "";
}

function platformCount(type, platform) {
    return state.overview?.counts?.[type]?.[platform] || 0;
}

function platformProfileCount(profile, keys = [], fallback = 0) {
    const value = profileValue(profile, keys);
    if (value === null || value === undefined || value === "") return fallback;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
}

function profileValue(profile, keys = []) {
    if (!profile || typeof profile !== "object") return null;
    for (const key of keys) {
        const value = profile[key];
        if (value !== undefined && value !== null && value !== "") return value;
    }
    return null;
}

function formatCount(value) {
    if (value === undefined || value === null || value === "") return "--";
    return String(value);
}

function defaultAvatar(platform) {
    return {
        douban:
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23233444'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%23d1d5db' font-size='20'%3E豆%3C/text%3E%3C/svg%3E",
        imdb:
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23f5c518'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%23000' font-size='15' font-weight='bold'%3EIMDb%3C/text%3E%3C/svg%3E",
        trakt:
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23ed1c24'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%23fff' font-size='12' font-weight='bold'%3ETrakt%3C/text%3E%3C/svg%3E",
        tmdb: "/static/images/platforms/tmdb.png",
    }[platform];
}

function proxyAvatarUrl(url) {
    if (!url) return "";
    if (url.startsWith("data:") || url.startsWith("/")) return url;
    const lower = url.toLowerCase();
    if (
        lower.includes("doubanio.com") ||
        lower.includes("douban.com") ||
        lower.includes("media-amazon.com") ||
        lower.includes("imdb.com") ||
        lower.includes("trakt.tv") ||
        lower.includes("tmdb.org")
    ) {
        return `/proxy/avatar?url=${encodeURIComponent(url)}`;
    }
    return url;
}

function proxyImageUrl(url) {
    if (!url) return "";
    if (url.startsWith("data:") || url.startsWith("/")) return url;
    const lower = url.toLowerCase();
    if (
        lower.includes("doubanio.com") ||
        lower.includes("douban.com") ||
        lower.includes("media-amazon.com") ||
        lower.includes("imdb.com") ||
        lower.includes("tmdb.org") ||
        lower.includes("themoviedb.org") ||
        lower.includes("image.tmdb.org")
    ) {
        return `/proxy/image?url=${encodeURIComponent(url)}`;
    }
    return url;
}

function posterFallback(title) {
    const first = String(title || "?").trim().charAt(0).toUpperCase() || "?";
    return `<div class="unified-media-fallback">${escapeHtml(first)}</div>`;
}

function updateStat(platform, key, value, href = null) {
    const valueEl = document.getElementById(`${platform}-${key}-count`);
    if (valueEl) valueEl.textContent = formatCount(value);
    const linkEl = document.getElementById(`link-${platform}-${key}`);
    if (linkEl && href) {
        linkEl.href = href;
    }
}

function renderPlatformAccount(platform, descriptor) {
    const status = descriptor?.status || {};
    const profile = status.profile || {};
    const avatarEl = document.getElementById(`${platform}-avatar`);
    const nameEl = document.getElementById(`${platform}-display-name`);
    const userIdEl = document.getElementById(`${platform}-user-id-display`);
    const metaEl = document.getElementById(`${platform}-join-date`);
    const profileLinkEl = document.getElementById(`${platform}-profile-link`);
    const configured = Boolean(status.configured);
    const configPresent = platformHasLocalConfig(platform, descriptor);
    const fallbackId = platformConfigId(platform) || "--";
    const displayName =
        profileValue(profile, ["display_name", "name", "username"]) ||
        (configured
            ? `${descriptor?.name || platform.toUpperCase()} 账户`
            : configPresent
              ? `${descriptor?.name || platform.toUpperCase()} 待验证`
              : `${descriptor?.name || platform.toUpperCase()} 未配置`);
    const userId = profileValue(profile, ["user_id", "account_id", "username"]) || fallbackId;
    const profileLink = profileValue(profile, ["profile_link", "profile_url"]);
    const avatar = proxyAvatarUrl(profileValue(profile, ["avatar"]) || defaultAvatar(platform));

    if (avatarEl) {
        avatarEl.src = avatar;
        avatarEl.onerror = () => {
            avatarEl.onerror = null;
            avatarEl.src = defaultAvatar(platform);
        };
    }
    if (nameEl) nameEl.textContent = displayName;
    if (userIdEl) userIdEl.textContent = userId || "--";
    if (metaEl) {
        metaEl.textContent =
            prettyStatusMessage(status.message) ||
            (configured ? "已连接，等待测试或更新数据" : defaultPlatformStatus(platform));
    }
    if (profileLinkEl) {
        profileLinkEl.href = profileLink || profileLinkEl.href;
        profileLinkEl.style.visibility = profileLink || configured || configPresent ? "visible" : "hidden";
    }

    const libraryCount = platformCount("library", platform);
    const wishlistCount = platformCount("wishlist", platform);

    if (platform === "douban") {
        const baseLink = profileLink || (userId && userId !== "--" ? `https://movie.douban.com/people/${userId}/` : "https://movie.douban.com/");
        updateStat(platform, "watched", profileValue(profile, ["watched", "watched_total"]) ?? libraryCount, `${baseLink}collect`);
        updateStat(platform, "wish", profileValue(profile, ["wish", "wish_total"]) ?? wishlistCount, `${baseLink}wish`);
        updateStat(platform, "doing", profileValue(profile, ["doing"]) ?? "--", `${baseLink}do`);
    }

    if (platform === "imdb") {
        const baseLink = userId && userId !== "--" ? `https://www.imdb.com/user/${userId}/` : "https://www.imdb.com/";
        updateStat(platform, "ratings", profileValue(profile, ["ratings", "ratings_total"]) ?? libraryCount, `${baseLink}ratings`);
        updateStat(platform, "watchlist", profileValue(profile, ["watchlist", "watchlist_total"]) ?? wishlistCount, `${baseLink}watchlist`);
        updateStat(platform, "lists", profileValue(profile, ["lists"]) ?? "--", `${baseLink}lists`);
    }

    if (platform === "trakt") {
        const traktId = userId && userId !== "--" ? userId : "";
        const baseLink = traktId ? `https://trakt.tv/users/${traktId}/` : "https://trakt.tv/";
        updateStat(platform, "watched", profileValue(profile, ["watched"]) ?? libraryCount, `${baseLink}history`);
        updateStat(platform, "rated", profileValue(profile, ["ratings", "ratings_total"]) ?? libraryCount, `${baseLink}ratings`);
    }

    if (platform === "tmdb") {
        const profileBase = profileLink || "https://www.themoviedb.org/";
        updateStat(platform, "rated", profileValue(profile, ["ratings", "rated_total"]) ?? libraryCount, profileBase);
        updateStat(platform, "watchlist", profileValue(profile, ["watchlist", "watchlist_total"]) ?? wishlistCount, profileBase);
    }
}

function setPlatformUi(platform, descriptor) {
    const configured = Boolean(descriptor?.status?.configured);
    const configPresent = platformHasLocalConfig(platform, descriptor);
    const lastValidatedAt = descriptor?.status?.last_validated_at || null;
    const summaryStats = document.getElementById(`summary-stats-${platform}`);
    const summaryId = document.getElementById(`summary-id-${platform}`);
    const summaryDot = document.getElementById(`summary-dot-${platform}`);
    const settingsBadge = document.getElementById(`settings-badge-${platform}`);
    const platformStatus = platformStatusElement(platform);
    const profile = descriptor?.status?.profile || {};
    const libraryCount = platformProfileCount(
        profile,
        platform === "douban"
            ? ["watched", "watched_total"]
            : platform === "imdb"
              ? ["ratings", "ratings_total"]
              : platform === "trakt"
                ? ["watched", "ratings", "ratings_total"]
                : ["ratings", "rated_total"],
        platformCount("library", platform)
    );
    const wishlistCount = platformProfileCount(
        profile,
        platform === "douban" ? ["wish", "wish_total"] : ["watchlist", "watchlist_total"],
        platformCount("wishlist", platform)
    );
    const hasMeaningfulCounts = libraryCount > 0 || wishlistCount > 0;
    const statsText = configured || hasMeaningfulCounts
        ? `看过 ${libraryCount} · 想看 ${wishlistCount}`
        : configPresent
          ? prettyStatusMessage(descriptor?.status?.message) || "已填写配置，等待测试连接"
          : platformHint(platform);
    const summaryIdentity =
        profileValue(profile, ["display_name", "user_id", "username"]) || platformConfigId(platform);

    if (summaryStats) summaryStats.textContent = statsText;
    if (summaryId) summaryId.textContent = summaryIdentity || "";
    if (summaryDot) summaryDot.className = `status-dot ${dotClass(configured, platform)}`;
    if (settingsBadge) {
        settingsBadge.className = `status-badge ${statusBadgeClass(configured, platform, configPresent, lastValidatedAt)}`;
        settingsBadge.textContent = statusBadgeText(configured, configPresent, lastValidatedAt);
    }
    if (platformStatus) {
        platformStatus.textContent = livePlatformMessage(
            platform,
            prettyStatusMessage(descriptor?.status?.message) ||
                (configPresent ? "已填写配置，点击测试连接验证账号和取数能力" : defaultPlatformStatus(platform))
        );
        platformStatus.style.display = "";
    }
    renderPlatformAccount(platform, descriptor);
}

function updateCounts() {
    const counts = state.overview?.counts || {};
    const library = counts.library || {};
    const wishlist = counts.wishlist || {};

    const metricLibraryTotal = document.getElementById("metric-library-total");
    const metricWishlistTotal = document.getElementById("metric-wishlist-total");
    const metricPlatformConfigured = document.getElementById("metric-platform-configured");
    const metricTaskTotal = document.getElementById("metric-task-total");
    if (metricLibraryTotal) metricLibraryTotal.textContent = counts.library_total || 0;
    if (metricWishlistTotal) metricWishlistTotal.textContent = counts.wishlist_total || 0;
    if (metricPlatformConfigured) {
        metricPlatformConfigured.textContent = (state.platforms || []).filter((platform) => platform.status?.configured).length;
    }
    if (metricTaskTotal) metricTaskTotal.textContent = (state.tasks || []).length;
    const sidebarLibraryTotal = document.getElementById("sidebar-library-total");
    const sidebarWishlistTotal = document.getElementById("sidebar-wishlist-total");
    const sidebarTaskTotal = document.getElementById("sidebar-task-total");
    if (sidebarLibraryTotal) sidebarLibraryTotal.textContent = counts.library_total || 0;
    if (sidebarWishlistTotal) sidebarWishlistTotal.textContent = counts.wishlist_total || 0;
    if (sidebarTaskTotal) sidebarTaskTotal.textContent = (state.tasks || []).length;

    updateLibraryFilterCounts({ shared: counts.library_shared ?? counts.library_total, ...library }, counts.library_total || 0);

    PLATFORM_IDS.forEach((platform) => {
        setPlatformUi(
            platform,
            state.platforms.find((item) => item.id === platform) || {
                status: { configured: false, message: "未配置" },
            }
        );
    });

    document.getElementById("summary-stats-letterboxd").textContent = `看过 ${library.letterboxd || 0} · 想看 ${
        wishlist.letterboxd || 0
    }`;
}

function updateLibraryFilterCounts(platformCounts = {}, totalFallback = 0) {
    const shared = platformCounts.shared ?? totalFallback;
    const countAll = document.getElementById("count-all");
    if (countAll) countAll.textContent = shared || 0;
    PLATFORM_IDS.forEach((platform) => {
        const el = document.getElementById(`count-${platform}`);
        if (el) el.textContent = platformCounts[platform] || 0;
    });
}

function selectedLibraryPlatforms() {
    if (!state.library.platformsInitialized) return "";
    const checked = $$('.filter-checkbox input[type="checkbox"]:checked');
    if (!checked.length) return "";
    return checked.map((checkbox) => checkbox.value).filter(Boolean).join(",");
}

function initializeLibraryPlatformCheckboxes(platformsWithData = []) {
    if (state.library.platformsInitialized || !platformsWithData.length) return false;
    const available = new Set(platformsWithData);
    $$('.filter-checkbox input[type="checkbox"]').forEach((checkbox) => {
        checkbox.checked = available.has(checkbox.value);
    });
    state.library.platformsInitialized = true;
    return true;
}

function taskSummary(task) {
    const payload = task?.payload || {};
    if (payload.platform) return `${payload.platform.toUpperCase()} · ${statusText(task)}`;
    if (payload.direction) return `${payload.direction} · ${statusText(task)}`;
    return statusText(task);
}

function compactDashboardTasks(tasks, limit = 5) {
    const seen = new Set();
    const result = [];
    for (const task of tasks) {
        const payload = task?.payload || {};
        const key = [task?.name || "", payload.platform || "", payload.direction || ""].join("|");
        if (seen.has(key)) continue;
        seen.add(key);
        result.push(task);
        if (result.length >= limit) break;
    }
    return result;
}

function renderTaskList(tasks, limit = tasks.length) {
    const scoped = tasks.slice(0, limit);
    return scoped.length
        ? scoped
              .map(
                  (task) => `
            <div class="rust-list-row">
                <div>
                    <div class="rust-movie-title">${escapeHtml(task.name)}</div>
                    <div class="rust-movie-meta">${escapeHtml(taskSummary(task))}</div>
                </div>
                <div class="rust-movie-meta">${escapeHtml(formatDate(task.updated_at))}</div>
                <div class="rust-tag">${escapeHtml(statusText(task))}</div>
            </div>
        `
              )
              .join("")
        : '<div class="rust-empty">暂无任务</div>';
}

function renderTasks() {
    const tasks = state.tasks || [];
    ui.tasksList.innerHTML = renderTaskList(tasks, 8);
    ui.dashboardTaskList.innerHTML = renderTaskList(compactDashboardTasks(tasks, 5), 5);
}

function populateScheduledTaskForm(task = null) {
    state.scheduled.editingId = task?.id || null;
    if (ui.scheduledTaskFormPanel) ui.scheduledTaskFormPanel.style.display = "";
    const placeholder = document.getElementById("task-form-placeholder");
    if (placeholder) placeholder.style.display = "none";
    document.getElementById("scheduled-task-id").value = task?.id || "";
    document.getElementById("scheduled-task-name").value = task?.name || "";
    document.getElementById("scheduled-task-source").value = task?.source_platform || "tmdb";
    document.getElementById("scheduled-task-target").value = task?.target_platform || "trakt";
    document.getElementById("scheduled-task-cron").value = task?.schedule || "0 2 * * *";
    document.getElementById("scheduled-task-enabled").checked = !(task?.paused ?? false);
}

function hideScheduledTaskForm() {
    state.scheduled.editingId = null;
    document.getElementById("scheduled-task-id").value = "";
    document.getElementById("scheduled-task-name").value = "";
    document.getElementById("scheduled-task-source").value = "tmdb";
    document.getElementById("scheduled-task-target").value = "trakt";
    document.getElementById("scheduled-task-cron").value = "0 2 * * *";
    document.getElementById("scheduled-task-enabled").checked = true;
    if (ui.scheduledTaskFormPanel) ui.scheduledTaskFormPanel.style.display = "none";
    const placeholder = document.getElementById("task-form-placeholder");
    if (placeholder) placeholder.style.display = "";
}

function renderScheduledTasks() {
    const tasks = state.scheduled.tasks || [];
    if (!ui.scheduledTasksList || !ui.scheduledTasksEmpty) return;
    if (!tasks.length) {
        ui.scheduledTasksEmpty.style.display = "";
        ui.scheduledTasksList.style.display = "none";
        ui.scheduledTasksList.innerHTML = "";
        return;
    }
    ui.scheduledTasksEmpty.style.display = "none";
    ui.scheduledTasksList.style.display = "";
    ui.scheduledTasksList.innerHTML = tasks
        .map(
            (task) => `
        <div class="scheduled-task-card">
            <div class="scheduled-task-head">
                <div>
                    <div class="rust-movie-title">${escapeHtml(task.name)}</div>
                    <div class="rust-movie-meta">${escapeHtml(task.source_platform.toUpperCase())} -> ${escapeHtml(
                task.target_platform.toUpperCase()
            )} · ${escapeHtml(task.schedule)}</div>
                </div>
                <span class="rust-tag">${task.running ? "执行中" : task.paused ? "已暂停" : "已启用"}</span>
            </div>
            <div class="scheduled-task-meta">
                <span class="rust-tag">${task.next_run_at ? `下次 ${formatDate(task.next_run_at)}` : "未计划"}</span>
                <span class="rust-tag">${escapeHtml(task.last_status_message || "等待首次执行")}</span>
            </div>
            <div class="scheduled-task-actions">
                <button class="btn btn-secondary btn-sm scheduled-run-btn" data-id="${task.id}" ${task.paused || task.running ? "disabled" : ""}>立即运行</button>
                <button class="btn btn-outline btn-sm scheduled-edit-btn" data-id="${task.id}">编辑</button>
                <button class="btn btn-outline btn-sm scheduled-toggle-btn" data-id="${task.id}" data-paused="${task.paused ? "1" : "0"}">${task.paused ? "启用" : "暂停"}</button>
                <button class="btn btn-outline btn-sm scheduled-delete-btn" data-id="${task.id}">删除</button>
            </div>
        </div>
    `
        )
        .join("");
}

function renderScheduledTaskLogs() {
    const container = document.getElementById("scheduled-task-logs");
    if (!container) return;
    const logs = state.scheduled.logs || [];
    container.innerHTML = logs.length
        ? logs
              .map(
                  (log) => `
            <div class="rust-list-row">
                <div>
                    <div class="rust-movie-title">${escapeHtml(log.task_name || "定时任务")}</div>
                    <div class="rust-movie-meta">${escapeHtml(
                        [log.source_platform?.toUpperCase(), log.target_platform?.toUpperCase()]
                            .filter(Boolean)
                            .join(" -> ")
                    )} · ${escapeHtml(log.message || "")}</div>
                </div>
                <div class="rust-movie-meta">${escapeHtml(formatDate(log.created_at))}</div>
                <span class="rust-tag">${escapeHtml(log.log_type || "info")}</span>
            </div>
        `
              )
              .join("")
        : '<div class="rust-empty">暂无执行日志。任务首次执行后会显示开始、完成或失败状态。</div>';
}

function renderBackups() {
    const backups = state.backups.items || [];
    if (!ui.backupsList || !ui.backupsEmpty) return;
    if (ui.backupsSummary) ui.backupsSummary.textContent = `${backups.length} 份`;
    ui.backupsEmpty.style.display = backups.length ? "none" : "";
    ui.backupsList.style.display = backups.length ? "" : "none";
    ui.backupsList.innerHTML = backups
        .map(
            (backup) => `
        <article class="backup-list-item">
            <div>
                <div class="rust-movie-title">${escapeHtml(backup.user_id)}</div>
                <div class="rust-movie-meta">豆瓣 · 看过 ${backup.watched_count} · 想看 ${backup.wishlist_count}</div>
                <div class="rust-movie-meta">${escapeHtml(formatDate(backup.created_at))}</div>
            </div>
            <div class="backup-list-actions">
                <button class="btn btn-outline btn-sm backup-preview-btn" type="button" data-id="${escapeHtml(backup.id)}">预览</button>
                <button class="btn btn-outline btn-sm backup-delete-btn" type="button" data-id="${escapeHtml(backup.id)}">删除</button>
            </div>
        </article>
    `
        )
        .join("");
}

function renderBackupPreview() {
    const backup = state.backups.selected;
    if (!backup || !ui.backupPreviewList) return;
    const kind = state.backups.previewKind;
    const items = backup[kind] || [];
    const title = document.getElementById("backup-preview-title");
    const summary = document.getElementById("backup-preview-summary");
    if (title) title.textContent = `${backup.user_id} 的豆瓣备份`;
    if (summary) {
        summary.textContent = `看过 ${backup.watched_count} · 想看 ${backup.wishlist_count} · ${formatDate(backup.created_at)}`;
    }
    document.querySelectorAll("[data-backup-preview-kind]").forEach((button) => {
        const active = button.dataset.backupPreviewKind === kind;
        button.classList.toggle("active", active);
        button.classList.toggle("btn-secondary", active);
        button.classList.toggle("btn-outline", !active);
    });
    ui.backupPreviewList.innerHTML = items.length
        ? items
              .slice(0, 200)
              .map((item) => {
                  const rating = kind === "watched" && item.rating != null ? ` · ${item.rating} 分` : "";
                  return `
                <div class="backup-preview-item">
                    <strong>${escapeHtml(item.title || "未命名")}</strong>
                    <span>${escapeHtml(item.year || "年份未知")}${escapeHtml(rating)}</span>
                </div>
            `;
              })
              .join("")
        : `<div class="rust-empty">这份备份没有${kind === "watched" ? "看过" : "想看"}条目</div>`;
}

function renderSystemInfo(payload) {
    if (!ui.systemInfoGrid) return;
    const storage = payload.storage || {};
    const counts = payload.counts || {};
    const entries = [
        ["服务", `${payload.version || "--"} · ${payload.os || "--"} ${payload.arch || ""}`],
        ["配置", storage.config || "--"],
        ["数据库", storage.database || "--"],
        ["好友备份", `${counts.backups || 0} 份 · ${storage.backups || "--"}`],
        ["定时任务", `${counts.scheduled_tasks || 0} 个`],
        ["后台任务", `${counts.tasks || 0} 条`],
        ["日志", storage.logs || "--"],
    ];
    ui.systemInfoGrid.innerHTML = entries
        .map(([label, value]) => `<div class="system-info-item"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`)
        .join("");
}

function switchSettingsPanel(targetId) {
    document.querySelectorAll(".settings-sub-tab").forEach((button) => {
        button.classList.toggle("active", button.dataset.settingsTarget === targetId);
    });
    document.querySelectorAll(".settings-sub-panel").forEach((panel) => {
        const active = panel.id === targetId;
        panel.classList.toggle("active", active);
        panel.style.display = active ? "" : "none";
    });
    if (targetId === "settings-backup-panel") loadBackups().catch(handleError);
    if (targetId === "settings-system-panel") loadSystemInfo().catch(handleError);
}

function switchScheduledPanel(targetId) {
    document.querySelectorAll(".scheduled-tab-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.scheduledTarget === targetId);
    });
    document.querySelectorAll(".scheduled-tab-panel").forEach((panel) => {
        const active = panel.id === targetId;
        panel.classList.toggle("active", active);
        panel.style.display = active ? "" : "none";
    });
    if (targetId === "scheduled-task-log-panel") loadScheduledTaskLogs().catch(handleError);
}

function renderPlatformGrid() {
    const grid = ui.dashboardPlatformGrid;
    if (!grid) return;
    grid.innerHTML = (state.platforms || [])
        .map((platform) => {
            const profile = platform.status?.profile || {};
            const libraryCount = platformProfileCount(
                profile,
                platform.id === "douban"
                    ? ["watched", "watched_total"]
                    : platform.id === "imdb"
                      ? ["ratings", "ratings_total"]
                      : platform.id === "trakt"
                        ? ["watched", "ratings", "ratings_total"]
                        : ["ratings", "rated_total"],
                platformCount("library", platform.id)
            );
            const wishlistCount = platformProfileCount(
                profile,
                platform.id === "douban" ? ["wish", "wish_total"] : ["watchlist", "watchlist_total"],
                platformCount("wishlist", platform.id)
            );
            return `
                <div class="rust-movie-card">
                    <div class="rust-tag-row">
                        <span class="rust-tag">${escapeHtml(platform.name)}</span>
                        <span class="rust-tag">${platform.status?.configured ? "已配置" : "未配置"}</span>
                    </div>
                    <div class="rust-movie-title">${escapeHtml(livePlatformMessage(platform.id, prettyStatusMessage(platform.status?.message) || platformHint(platform.id)))}</div>
                    <div class="rust-movie-meta">看过 ${libraryCount} · 想看 ${wishlistCount}</div>
                    <div class="rust-card-actions">
                        <button class="btn btn-outline btn-sm rust-open-tab-btn" data-tab="settings">管理账户</button>
                    </div>
                </div>
            `;
        })
        .join("");
}

function sourceBadges(item) {
    return (item.source_platforms || [])
        .map((platform) => `<span class="source-pill">${escapeHtml(platformLabel(platform))}</span>`)
        .join("");
}

function platformIcon(platform) {
    return {
        douban: "/static/images/platforms/douban.png",
        imdb: "/static/images/platforms/imdb.svg",
        trakt: "/static/images/platforms/trakt.png",
        letterboxd: "/static/images/platforms/letterboxd.png",
        tmdb: "/static/images/platforms/tmdb.png",
    }[platform] || "";
}

function itemPrimaryLink(item) {
    return item.source_url || item.library_url || item.sources?.find((source) => source.source_url)?.source_url || "";
}

function itemSubtitle(item) {
    const parts = [];
    if (item.year) parts.push(String(item.year));
    if (item.media_type === "tv") parts.push("剧集");
    if (item.personal_rating) parts.push(`我的评分 ${item.personal_rating}`);
    else if (item.public_rating) parts.push(`站点评分 ${item.public_rating}`);
    if (item.rated_at) parts.push(formatShortDate(item.rated_at));
    return parts.join(" · ");
}

function sourceRatingText(source) {
    if (source?.rating === null || source?.rating === undefined) return "未评分";
    return `评分 ${source.rating}`;
}

function sourceScoreStrip(item) {
    const sources = item.sources || [];
    if (!sources.length) return "";
    return `
        <div class="source-score-strip">
            ${sources
                .map(
                    (source) => `
                <span class="source-score" title="${escapeHtml(platformLabel(source.platform))}${source.rated_at ? ` · ${formatShortDate(source.rated_at)}` : ""}">
                    ${platformIcon(source.platform) ? `<img src="${escapeHtml(platformIcon(source.platform))}" alt="">` : ""}
                    <span>${escapeHtml(sourceRatingText(source).replace("评分 ", ""))}</span>
                </span>
            `
                )
                .join("")}
        </div>
    `;
}

function ratingDifferenceTag(item) {
    const ratings = (item.sources || [])
        .map((source) => source.rating)
        .filter((rating) => rating !== null && rating !== undefined)
        .map((rating) => Number(rating));
    if (ratings.length < 2) return "";
    const min = Math.min(...ratings);
    const max = Math.max(...ratings);
    if (Math.abs(max - min) < 0.01) return "";
    return `<span class="status-pill difference-pill">平台评分差 ${min} / ${max}</span>`;
}

function renderPlatformBadge(source) {
    const icon = platformIcon(source.platform);
    const label = source.platform === "letterboxd" ? "LB" : platformLabel(source.platform);
    const rating = source.rating !== null && source.rating !== undefined ? source.rating : "";
    const href = source.source_url || "";
    const content = `
        ${icon ? `<img src="${escapeHtml(icon)}" alt="">` : ""}
        <span>${escapeHtml(label)}</span>
        ${rating !== "" ? `<span class="badge-rating">${escapeHtml(rating)}</span>` : ""}
    `;
    return href
        ? `<a class="platform-badge ${escapeHtml(source.platform)}" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${content}</a>`
        : `<span class="platform-badge ${escapeHtml(source.platform)}">${content}</span>`;
}

function renderLegacyLibraryItem(item) {
    const posterUrl = proxyImageUrl(item.poster_url || "");
    const title = item.title || "Unknown title";
    const year = item.year ? `<span class="movie-year">${escapeHtml(item.year)}</span>` : "";
    const primaryRating =
        item.personal_rating !== null && item.personal_rating !== undefined
            ? item.personal_rating
            : item.sources?.find((source) => source.rating !== null && source.rating !== undefined)?.rating;
    const ratingHtml =
        primaryRating !== null && primaryRating !== undefined
            ? `<div class="rating-main"><span class="rating-label">评分</span><span class="rating-value">${escapeHtml(primaryRating)}</span></div>`
            : "";
    const dateValue = item.rated_at || item.sources?.find((source) => source.rated_at)?.rated_at || "";
    const dateHtml = dateValue
        ? `<div class="rating-date"><span class="date-label">最后操作于</span><span class="date-value">${escapeHtml(formatShortDate(dateValue))}</span></div>`
        : "";
    const poster = posterUrl
        ? `<div class="movie-cover-wrapper"><img class="movie-cover-large" src="${escapeHtml(posterUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null; this.src=''; this.parentNode.classList.add('error');"></div>`
        : `<div class="movie-cover-wrapper"><div class="movie-cover-placeholder large">🎬</div></div>`;
    const badges = (item.sources || []).map(renderPlatformBadge).join("");
    const identifiers = [
        item.identifiers?.imdb ? `IMDb ${item.identifiers.imdb}` : "",
        item.identifiers?.tmdb ? `TMDB ${item.identifiers.tmdb}` : "",
        item.identifiers?.douban ? `豆瓣 ${item.identifiers.douban}` : "",
    ].filter(Boolean).join(" · ");

    return `
        <div class="movie-item">
            ${poster}
            <div class="movie-info">
                <div class="movie-title-row">
                    <div class="movie-title">${escapeHtml(title)} ${year}</div>
                    <div class="platform-badges-inline">${badges}</div>
                </div>
                <div class="movie-metadata-grid">
                    ${identifiers ? `<div class="meta-item"><span class="meta-icon">🔎</span><span class="meta-text">${escapeHtml(identifiers)}</span></div>` : ""}
                    ${item.public_rating ? `<div class="meta-item"><span class="meta-icon">⭐</span><span class="meta-text">站点评分 ${escapeHtml(item.public_rating)}</span></div>` : ""}
                    ${item.public_votes ? `<div class="meta-item"><span class="meta-icon">👥</span><span class="meta-text">${escapeHtml(item.public_votes)} 人评价</span></div>` : ""}
                </div>
                <div class="movie-bottom">
                    <div class="score-display">
                        ${ratingHtml}
                        ${dateHtml}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderLegacyWishlistItem(item) {
    const posterUrl = proxyImageUrl(item.poster_url || "");
    const title = item.title || "Unknown title";
    const year = item.year ? `<span class="movie-year">${escapeHtml(item.year)}</span>` : "";
    const dateValue = item.added_at || item.rated_at || item.sources?.find((source) => source.rated_at)?.rated_at || "";
    const poster = posterUrl
        ? `<div class="movie-cover-wrapper"><img class="movie-cover-large" src="${escapeHtml(posterUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null; this.src=''; this.parentNode.classList.add('error');"></div>`
        : `<div class="movie-cover-wrapper"><div class="movie-cover-placeholder large">🎬</div></div>`;
    const badges = (item.sources || []).map(renderPlatformBadge).join("");
    const downloadLinks = !item.library_matched
        ? buildDownloadLinks(item)
              .slice(0, 8)
              .map((link) => `<a class="download-pill" href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)} ↗</a>`)
              .join("")
        : "";
    const matched = item.library_matched ? `<span class="status-pill matched">已在片库</span>` : `<span class="status-pill">待检索</span>`;

    return `
        <div class="movie-item">
            ${poster}
            <div class="movie-info">
                <div class="movie-title-row">
                    <div class="movie-title">${escapeHtml(title)} ${year}</div>
                    <div class="platform-badges-inline">${badges}${matched}</div>
                </div>
                <div class="movie-metadata-grid">
                    ${item.identifiers?.imdb ? `<div class="meta-item"><span class="meta-icon">🔎</span><span class="meta-text">IMDb ${escapeHtml(item.identifiers.imdb)}</span></div>` : ""}
                    ${item.library_matched && item.library_url ? `<div class="meta-item"><span class="meta-icon">✅</span><span class="meta-text">已匹配片库</span></div>` : ""}
                </div>
                <div class="movie-bottom">
                    <div class="score-display">
                        ${dateValue ? `<div class="rating-date"><span class="date-label">加入于</span><span class="date-value">${escapeHtml(formatShortDate(dateValue))}</span></div>` : ""}
                    </div>
                    <div class="unified-media-links">${downloadLinks}${item.library_matched && item.library_url ? `<a class="download-pill" href="${escapeHtml(item.library_url)}" target="_blank" rel="noopener noreferrer">片库条目 ↗</a>` : ""}</div>
                </div>
            </div>
        </div>
    `;
}

function updateLibraryInsight() {
    if (!ui.libraryInsightBar) return;
    const items = state.library.items || [];
    const currentShown = items.length;
    const withPoster = items.filter((item) => item.poster_url).length;
    const multiSource = items.filter((item) => (item.source_platforms || []).length > 1).length;
    const selected = selectedLibraryPlatforms()
        .split(",")
        .filter(Boolean)
        .map(platformLabel)
        .join(" / ");
    const filterText =
        state.library.filter === "all"
            ? `共有交集${selected ? ` · ${selected}` : " · 全部并集"}`
            : `${platformLabel(state.library.filter)} 差异项`;
    ui.libraryInsightBar.innerHTML = `
        <span class="status-pill">${escapeHtml(filterText)}</span>
        <span class="status-pill">当前页 ${currentShown} 条</span>
        <span class="status-pill">多平台合并 ${multiSource} 条</span>
        <span class="status-pill">有封面 ${withPoster} 条</span>
    `;
}

function renderMovieCard(item, mode = "library", view = "grid") {
    if (mode === "library" && view === "list") {
        return renderLegacyLibraryItem(item);
    }
    if (mode === "wishlist" && view === "list") {
        return renderLegacyWishlistItem(item);
    }
    const posterUrl = proxyImageUrl(item.poster_url || "");
    const title = item.title || "Unknown title";
    const primaryLink = itemPrimaryLink(item);
    const titleHtml = primaryLink
        ? `<a class="unified-media-title" href="${escapeHtml(primaryLink)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)}</a>`
        : `<span class="unified-media-title">${escapeHtml(title)}</span>`;
    const subtitle = itemSubtitle(item);
    const openLinks = (item.sources || [])
        .filter((source) => source.source_url)
        .slice(0, view === "grid" ? 3 : 5)
        .map(
            (source) =>
                `<a class="source-pill" href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.platform.toUpperCase())} ↗</a>`
        )
        .join("");
    const downloadLinks =
        mode === "wishlist" && !item.library_matched
            ? buildDownloadLinks(item)
                  .slice(0, view === "grid" ? 3 : 6)
                  .map(
                      (link) =>
                          `<a class="download-pill" href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)} ↗</a>`
                  )
                  .join("")
            : "";
    const matchedTag =
        mode === "wishlist"
            ? item.library_matched
                ? `<span class="status-pill matched">已在片库</span>`
                : `<span class="status-pill">待检索</span>`
            : "";
    const poster = posterUrl
        ? `<img src="${escapeHtml(posterUrl)}" alt="${escapeHtml(title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none';this.nextElementSibling.style.display='grid';"><div class="unified-media-fallback" style="display:none;">${escapeHtml(String(title || "?").trim().charAt(0).toUpperCase() || "?")}</div>`
        : posterFallback(title);

    return `
        <article class="unified-media-card ${view}">
            <div class="unified-media-poster">${poster}</div>
            <div class="unified-media-body">
                <div class="unified-media-title-row">
                    <div class="unified-media-title-group">
                        ${titleHtml}
                        <div class="unified-media-subtitle">${escapeHtml(subtitle || (mode === "wishlist" ? "想看条目" : "片库条目"))}</div>
                    </div>
                    <div class="unified-media-meta">
                        ${matchedTag}
                        ${ratingDifferenceTag(item)}
                        ${view === "grid" ? sourceBadges(item) : ""}
                    </div>
                </div>
                ${mode === "library" ? sourceScoreStrip(item) : ""}
                <div class="unified-media-meta">
                    ${view === "grid" && item.identifiers?.imdb ? `<span class="status-pill">IMDb ${escapeHtml(item.identifiers.imdb)}</span>` : ""}
                    ${view === "grid" && item.identifiers?.tmdb ? `<span class="status-pill">TMDB ${escapeHtml(item.identifiers.tmdb)}</span>` : ""}
                    ${view === "grid" && item.identifiers?.douban ? `<span class="status-pill">豆瓣 ${escapeHtml(item.identifiers.douban)}</span>` : ""}
                    ${item.public_votes ? `<span class="status-pill">${escapeHtml(String(item.public_votes))} 人评价</span>` : ""}
                </div>
                <div class="unified-media-links">
                    ${openLinks}
                    ${downloadLinks}
                    ${mode === "wishlist" && item.library_matched && item.library_url ? `<a class="download-pill" href="${escapeHtml(item.library_url)}" target="_blank" rel="noopener noreferrer">片库条目 ↗</a>` : ""}
                </div>
            </div>
        </article>
    `;
}

function renderLibrary() {
    const items = state.library.items || [];
    ui.libraryList.className = state.library.view === "list" ? "library-list library-list-view" : "rust-card-grid library-grid-view";
    if (!items.length) {
        ui.libraryEmpty.style.display = "";
        ui.libraryList.style.display = "none";
        ui.libraryPagination.style.display = "none";
        updateLibraryInsight();
        return;
    }
    ui.libraryEmpty.style.display = "none";
    ui.libraryList.style.display = "";
    ui.libraryList.innerHTML = items.map((item) => renderMovieCard(item, "library", state.library.view)).join("");
    updateLibraryInsight();
    const totalPages = Math.max(1, Math.ceil((state.library.total || 0) / LIBRARY_PAGE_SIZE));
    ui.libraryPageInfo.textContent = `${state.library.page} / ${totalPages}`;
    ui.libPrevBtn.disabled = state.library.page <= 1;
    ui.libNextBtn.disabled = state.library.page >= totalPages;
    ui.libraryPagination.style.display = totalPages > 1 ? "flex" : "none";
    updateLibraryInsight();
}

function filteredWishlistItems() {
    const active = state.wishlist.sources;
    return (state.wishlist.items || []).filter((item) => {
        if (state.wishlist.onlyUnmatched && item.library_matched) return false;
        const platforms = item.source_platforms || item.sources?.map((source) => source.platform) || [];
        return !active.size || platforms.some((platform) => active.has(platform));
    });
}

function renderWishlist() {
    const items = filteredWishlistItems();
    state.wishlist.filteredItems = items;
    const totalPages = Math.max(1, Math.ceil(items.length / WISHLIST_PAGE_SIZE));
    if (state.wishlist.page > totalPages) state.wishlist.page = totalPages;
    const start = (state.wishlist.page - 1) * WISHLIST_PAGE_SIZE;
    const pageItems = items.slice(start, start + WISHLIST_PAGE_SIZE);

    ui.wishlistList.className = state.wishlist.view === "list" ? "library-list library-list-view" : "rust-card-grid library-grid-view";
    if (!pageItems.length) {
        ui.wishlistEmpty.style.display = "";
        ui.wishlistList.style.display = "none";
        ui.wishlistPagination.style.display = items.length > 0 ? "flex" : "none";
        ui.wishlistPageInfo.textContent = `${state.wishlist.page} / ${totalPages}`;
        return;
    }
    ui.wishlistEmpty.style.display = "none";
    ui.wishlistList.style.display = "";
    ui.wishlistList.innerHTML = pageItems.map((item) => renderMovieCard(item, "wishlist", state.wishlist.view)).join("");
    ui.wishlistPageInfo.textContent = `${state.wishlist.page} / ${totalPages}`;
    ui.wishlistPrevBtn.disabled = state.wishlist.page <= 1;
    ui.wishlistNextBtn.disabled = state.wishlist.page >= totalPages;
    ui.wishlistPagination.style.display = totalPages > 1 ? "flex" : "none";
}

function syncActionLabel(status) {
    const labels = {
        new: "新增",
        overwrite: "覆盖",
        keep: "跳过",
        success: "成功",
        skipped: "跳过",
        failed: "失败",
        error: "失败",
    };
    return labels[status] || status || "待处理";
}

function isExecutablePreviewItem(item) {
    return Boolean(item?.target_linking_id && !item.reason && ["new", "overwrite"].includes(item.action));
}

function renderSyncItems(items, mode) {
    if (!items?.length) {
        ui.syncPreviewEmpty.style.display = "";
        ui.syncPreviewEmpty.textContent = mode === "preview"
            ? "没有发现可同步条目。可以调整同步方向、覆盖规则或最近条目数后重新预览。"
            : "本次执行没有返回条目。";
        ui.syncPreviewList.style.display = "none";
        if (ui.syncSelectionSummary) ui.syncSelectionSummary.textContent = "待预览";
        document.getElementById("execute-sync-btn").disabled = true;
        return;
    }
    ui.syncPreviewEmpty.style.display = "none";
    ui.syncPreviewList.style.display = "";
    if (mode !== "preview") {
        state.sync.selectedTargetIds = new Set();
    }

    const resultCounts = items.reduce(
        (acc, item) => {
            const key = mode === "preview" ? (isExecutablePreviewItem(item) ? "ready" : "skipped") : item.status || "skipped";
            acc[key] = (acc[key] || 0) + 1;
            return acc;
        },
        { ready: 0, success: 0, skipped: 0, failed: 0 }
    );
    const preview = state.sync.preview || {};
    const overview =
        mode === "preview"
            ? [
                  ["源库", preview.source_count ?? "--"],
                  ["目标库", preview.target_count ?? "--"],
                  ["可执行", resultCounts.ready || 0],
                  ["已跳过", resultCounts.skipped || 0],
              ]
            : [
                  ["成功", resultCounts.success || 0],
                  ["跳过", resultCounts.skipped || 0],
                  ["失败", resultCounts.failed || 0],
                  ["返回项", items.length],
              ];

    const rows = items
        .map((item) => {
            const status = mode === "preview" ? item.action || "preview" : item.status || "result";
            const hasRating = item.source_rating !== null && item.source_rating !== undefined;
            const sourceRating = hasRating ? item.source_rating : "未评分";
            const targetRating =
                item.target_existing_rating !== null && item.target_existing_rating !== undefined
                    ? item.target_existing_rating
                    : "无";
            const reason =
                item.reason ||
                (mode === "preview" && !hasRating ? "目标平台需要评分时，可在高级选项启用默认分后重新预览。" : "");
            const selectable = mode === "preview" && isExecutablePreviewItem(item);
            const checked = selectable && state.sync.selectedTargetIds.has(item.target_linking_id) ? "checked" : "";
            const checkbox = selectable
                ? `<input type="checkbox" class="sync-preview-checkbox sync-item-checkbox" data-target-id="${escapeHtml(item.target_linking_id)}" aria-label="选择 ${escapeHtml(item.title || "条目")}" ${checked}>`
                : `<span class="sync-action-pill ${escapeHtml(status)}">${escapeHtml(syncActionLabel(status))}</span>`;
            const sourceLabel = item.source_platform
                ? `${platformLabel(item.source_platform)} → ${platformLabel(item.target_platform)}`
                : state.sync.preview?.direction || state.sync.result?.direction || "";
            const idLabel = item.target_linking_id ? `目标 ID ${item.target_linking_id}` : "缺少目标平台 ID";
            const rowClass = selectable ? "" : " class=\"is-skipped\"";
            return `
                <tr${rowClass}>
                    <td>${checkbox}</td>
                    <td>
                        <strong>${escapeHtml(item.title || "Unknown title")}</strong>
                        <div class="rust-movie-meta">${escapeHtml([item.year || "", idLabel].filter(Boolean).join(" · "))}</div>
                        <div class="sync-preview-links">
                            ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">源页面 ↗</a>` : ""}
                            ${item.target_url ? `<a href="${escapeHtml(item.target_url)}" target="_blank" rel="noopener noreferrer">目标页面 ↗</a>` : ""}
                        </div>
                    </td>
                    <td>${escapeHtml(sourceLabel)}</td>
                    <td><span class="sync-rating-badge">${escapeHtml(sourceRating)}</span></td>
                    <td><span class="sync-rating-badge">${escapeHtml(targetRating)}</span></td>
                    <td><span class="sync-action-pill ${escapeHtml(status)}">${escapeHtml(syncActionLabel(status))}</span></td>
                    <td>${reason ? `<span class="sync-reason">${escapeHtml(reason)}</span>` : "--"}</td>
                </tr>
            `;
        })
        .join("");

    ui.syncPreviewList.innerHTML = `
        <div class="sync-preview-overview">
            ${overview
                .map(([label, value]) => `<div class="sync-preview-metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`)
                .join("")}
        </div>
        <div class="sync-preview-table-wrap">
            <table class="sync-preview-table">
                <thead>
                    <tr>
                        <th>选择</th>
                        <th>电影</th>
                        <th>流向</th>
                        <th>源评分</th>
                        <th>目标评分</th>
                        <th>动作</th>
                        <th>说明</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
    document.getElementById("execute-sync-btn").disabled =
        mode !== "preview" || (state.sync.selectedTargetIds?.size || 0) === 0;
    updateSyncSelectionSummary();
}

function syncDownloadStateFromConfig(config) {
    state.downloadSites.enabledIds = new Set(config.download_sites_enabled || []);
    state.downloadSites.customSites = Array.isArray(config.download_sites_custom) ? config.download_sites_custom : [];
    state.downloadSites.deletedDefaults = new Set(config.download_sites_deleted || []);
}

function collectDownloadSiteConfig() {
    const enabledIds = Array.from(
        document.querySelectorAll('#download-sites-default input[data-type="default"]:checked')
    ).map((input) => input.dataset.siteId);
    const customSites = Array.from(document.querySelectorAll('#download-sites-default input[data-type="custom"]')).map((input) => {
        const index = Number(input.dataset.index || "-1");
        const site = state.downloadSites.customSites[index];
        return site
            ? {
                  label: site.label,
                  template: site.template,
                  enabled: input.checked,
              }
            : null;
    }).filter(Boolean);
    return {
        enabledIds,
        customSites,
        deletedDefaults: Array.from(state.downloadSites.deletedDefaults || []),
    };
}

function renderDownloadSiteSettings() {
    const container = document.getElementById("download-sites-default");
    if (!container) return;
    const defaults = DEFAULT_DOWNLOAD_SITES.filter((site) => !state.downloadSites.deletedDefaults.has(site.id));
    const customs = state.downloadSites.customSites || [];
    const html = [...defaults.map((site) => ({ ...site, type: "default" })), ...customs.map((site, index) => ({ ...site, type: "custom", index }))]
        .map((site) => `
            <label class="download-site-item">
                <div class="download-site-info">
                    <div class="download-site-item-top">
                        <div>
                            <span class="download-site-name">${escapeHtml(site.label)}</span>
                            <div class="download-site-meta">
                                <span class="download-site-kind">${site.type === "default" ? "默认站点" : "自定义"}</span>
                                <span class="rust-status-inline">${site.type === "default" ? "可隐藏" : "可删除"}</span>
                            </div>
                        </div>
                        <input
                            class="download-site-toggle"
                            type="checkbox"
                            data-type="${site.type}"
                            ${site.type === "default" ? `data-site-id="${site.id}"` : `data-index="${site.index}"`}
                            ${site.type === "default"
                                ? (state.downloadSites.enabledIds.has(site.id) ? "checked" : "")
                                : (site.enabled !== false ? "checked" : "")}
                        >
                    </div>
                    <span class="download-site-template">${escapeHtml(site.template)}</span>
                    <button
                        type="button"
                        class="btn btn-outline btn-sm download-site-delete-btn"
                        data-type="${site.type}"
                        ${site.type === "default" ? `data-site-id="${site.id}"` : `data-index="${site.index}"`}
                    >${site.type === "default" ? "隐藏" : "删除"}</button>
                </div>
            </label>
        `)
        .join("");
    container.innerHTML = html || '<div class="rust-empty">暂无可用站点</div>';

    container.querySelectorAll("input[type='checkbox']").forEach((input) => {
        input.addEventListener("change", () => {
            const config = collectDownloadSiteConfig();
            state.downloadSites.enabledIds = new Set(config.enabledIds);
            state.downloadSites.customSites = config.customSites;
            renderWishlist();
        });
    });
    container.querySelectorAll(".download-site-delete-btn").forEach((button) => {
        button.addEventListener("click", () => {
            if (button.dataset.type === "default") {
                state.downloadSites.deletedDefaults.add(button.dataset.siteId);
                state.downloadSites.enabledIds.delete(button.dataset.siteId);
            } else {
                state.downloadSites.customSites.splice(Number(button.dataset.index || "-1"), 1);
            }
            renderDownloadSiteSettings();
            renderWishlist();
        });
    });
}

function filterDownloadSites(query) {
    const normalized = String(query || "").trim().toLowerCase();
    document.querySelectorAll("#download-sites-default .download-site-item").forEach((item) => {
        const text = item.textContent?.toLowerCase() || "";
        item.style.display = !normalized || text.includes(normalized) ? "" : "none";
    });
}

function populateConfig(config) {
    state.currentConfig = config;
    syncDownloadStateFromConfig(config);
    document.getElementById("tmdb-api-key").value = config.platforms?.tmdb?.api_key || "";
    document.getElementById("tmdb-session-id").value = config.platforms?.tmdb?.session_id || "";
    document.getElementById("trakt-client-id").value = config.platforms?.trakt?.client_id || "";
    document.getElementById("trakt-client-secret").value = config.platforms?.trakt?.client_secret || "";
    document.getElementById("imdb-user-id").value = config.platforms?.imdb?.user_id || "";
    document.getElementById("imdb-cookie").value = config.platforms?.imdb?.cookie || "";
    document.getElementById("douban-user-id").value = config.platforms?.douban?.user_id || "";
    document.getElementById("douban-cookie").value = config.platforms?.douban?.cookie || "";
    document.getElementById("cookiecloud-host").value = config.cookiecloud?.host || "";
    document.getElementById("cookiecloud-uuid").value = config.cookiecloud?.uuid || "";
    document.getElementById("cookiecloud-password").value = config.cookiecloud?.password || "";

    if (ui.cookieCloudStatus) ui.cookieCloudStatus.textContent = config.cookiecloud?.host ? "已配置" : "未同步";
    const traktAuthText = config.platforms?.trakt?.access_token
        ? `Trakt 已授权${config.platforms?.trakt?.token_expires_at ? ` · 过期 ${formatDate(config.platforms.trakt.token_expires_at)}` : ""}`
        : "Trakt 尚未完成 OAuth 授权。";
    const tmdbAuthText = config.platforms?.tmdb?.session_id
        ? `TMDB 已配置 Session${config.platforms?.tmdb?.username ? ` · 用户 ${config.platforms.tmdb.username}` : ""}`
        : "TMDB 当前可直接填 Session ID，也可走浏览器授权。";
    if (ui.traktAuthStatus) ui.traktAuthStatus.textContent = traktAuthText;
    if (ui.tmdbAuthStatus) ui.tmdbAuthStatus.textContent = tmdbAuthText;
    const traktCardStatus = document.getElementById("trakt-card-status");
    const tmdbCardStatus = document.getElementById("tmdb-card-status");
    const doubanStatus = document.getElementById("browser-auth-status-douban");
    const imdbStatus = document.getElementById("browser-auth-status-imdb");
    if (traktCardStatus) traktCardStatus.textContent = traktAuthText;
    if (tmdbCardStatus) tmdbCardStatus.textContent = tmdbAuthText;
    if (doubanStatus) doubanStatus.textContent = defaultPlatformStatus("douban", config);
    if (imdbStatus) imdbStatus.textContent = defaultPlatformStatus("imdb", config);
    if (ui.configSaveStatus) ui.configSaveStatus.textContent = "保存后会自动验证账号和取数能力";
    renderDownloadSiteSettings();
}

function gatherConfigPayload() {
    const base = state.currentConfig || {
        app: {
            host: "127.0.0.1",
            port: 18000,
            timezone: "Asia/Shanghai",
            data_dir: "data/v2",
            database_url: "sqlite://data/v2/app.db",
            log_path: "logs/v2/server.log",
        },
        platforms: {},
        cookiecloud: {},
    };
    const downloadConfig = collectDownloadSiteConfig();

    return {
        app: {
            ...base.app,
            host: "127.0.0.1",
            port: 18000,
        },
        platforms: {
            ...base.platforms,
            tmdb: {
                ...(base.platforms?.tmdb || {}),
                api_key: document.getElementById("tmdb-api-key").value.trim() || null,
                session_id: document.getElementById("tmdb-session-id").value.trim() || null,
            },
            trakt: {
                ...(base.platforms?.trakt || {}),
                client_id: document.getElementById("trakt-client-id").value.trim() || null,
                client_secret: document.getElementById("trakt-client-secret").value.trim() || null,
            },
            imdb: {
                ...(base.platforms?.imdb || {}),
                user_id: document.getElementById("imdb-user-id").value.trim() || null,
                cookie: document.getElementById("imdb-cookie").value.trim() || null,
            },
            douban: {
                ...(base.platforms?.douban || {}),
                user_id: document.getElementById("douban-user-id").value.trim() || null,
                cookie: document.getElementById("douban-cookie").value.trim() || null,
            },
        },
        cookiecloud: {
            ...(base.cookiecloud || {}),
            host: document.getElementById("cookiecloud-host").value.trim() || null,
            uuid: document.getElementById("cookiecloud-uuid").value.trim() || null,
            password: document.getElementById("cookiecloud-password").value || null,
        },
        download_sites_enabled: downloadConfig.enabledIds,
        download_sites_custom: downloadConfig.customSites,
        download_sites_deleted: downloadConfig.deletedDefaults,
    };
}

function gatherSyncPayload(options = {}) {
    const source = document.getElementById("sync-source-select").value;
    const target = document.getElementById("sync-target-select").value;
    if (source === target) {
        throw new Error("源平台和目标平台不能相同");
    }
    const mode = document.querySelector('input[name="rust-sync-mode"]:checked')?.value || "new";
    const recentLimit = Math.min(500, Math.max(1, Number(document.getElementById("sync-recent-limit").value || 100)));
    const useDefaultRating = document.getElementById("sync-default-rating-enabled")?.checked;
    const defaultRating = Number(document.getElementById("sync-default-rating").value || 0);
    if (useDefaultRating && (defaultRating < 1 || defaultRating > 10)) {
        throw new Error("默认评分需要在 1 到 10 之间");
    }
    return {
        source_platform: source,
        target_platform: target,
        recent_limit: recentLimit,
        only_new: mode === "new",
        overwrite: mode === "overwrite",
        default_rating: useDefaultRating ? defaultRating : null,
        refresh_before_sync: options.forceRefresh === true
            ? true
            : document.getElementById("sync-refresh-before")?.checked === true,
        selected_target_ids: Array.from(state.sync.selectedTargetIds || []),
    };
}

function updateSyncSelectionSummary() {
    if (!ui.syncSelectionSummary) return;
    const previewItems = state.sync.preview?.items || [];
    if (!previewItems.length) {
        ui.syncSelectionSummary.textContent = "待预览";
        return;
    }
    const selectableCount = previewItems.filter(isExecutablePreviewItem).length;
    const selectedCount = Array.from(state.sync.selectedTargetIds || []).filter(Boolean).length;
    ui.syncSelectionSummary.textContent = `已选 ${selectedCount} / ${selectableCount}`;
    document.getElementById("execute-sync-btn").disabled = selectedCount === 0;
}

function markSyncPreviewStale() {
    state.sync.preview = null;
    state.sync.result = null;
    state.sync.selectedTargetIds = new Set();
    if (ui.syncPreviewList) {
        ui.syncPreviewList.style.display = "none";
        ui.syncPreviewList.innerHTML = "";
    }
    if (ui.syncPreviewEmpty) {
        ui.syncPreviewEmpty.style.display = "";
        ui.syncPreviewEmpty.textContent = "同步方向或规则已变化，请重新预览。";
    }
    if (ui.syncSummaryText) ui.syncSummaryText.textContent = "尚未生成同步预览";
    if (ui.syncSelectionSummary) ui.syncSelectionSummary.textContent = "待预览";
    document.getElementById("execute-sync-btn").disabled = true;
}

async function loadHealth() {
    const payload = await api("/health");
    ui.healthStatus.textContent = `CineRecord ${payload.version || ""} · ${payload.os || ""} ${payload.arch || ""} · 服务正常`;
}

async function loadConfig() {
    const payload = await api("/config");
    populateConfig(payload);
}

function platformsNeedingValidation(config) {
    const platforms = config?.platforms || {};
    const result = [];
    if (platforms.douban?.cookie || platforms.douban?.user_id) result.push("douban");
    if (platforms.imdb?.cookie) result.push("imdb");
    if (platforms.trakt?.client_id || platforms.trakt?.access_token) result.push("trakt");
    if (platforms.tmdb?.api_key || platforms.tmdb?.session_id) result.push("tmdb");
    return result;
}

async function validateConfiguredPlatforms(config, options = {}) {
    const platforms = options.platforms || platformsNeedingValidation(config);
    if (!platforms.length) {
        if (ui.configSaveStatus) ui.configSaveStatus.textContent = "已保存，暂无可验证的平台";
        return [];
    }
    if (ui.configSaveStatus) {
        ui.configSaveStatus.textContent = `已保存，正在验证 ${platforms.map((platform) => platform.toUpperCase()).join(" / ")}...`;
    }
    const results = await Promise.allSettled(
        platforms.map((platform) => runPlatformTest(platform, { refresh: false, append: true }))
    );
    const succeeded = results.filter((item) => item.status === "fulfilled").length;
    const failed = results.length - succeeded;
    if (ui.configSaveStatus) {
        ui.configSaveStatus.textContent =
            failed > 0 ? `验证完成：成功 ${succeeded}，失败 ${failed}` : `验证完成：${succeeded} 个平台已更新`;
    }
    await Promise.all([loadOverview(), loadConfig()]);
    return results;
}

async function saveConfig(event, options = {}) {
    if (event?.preventDefault) event.preventDefault();
    const validate = options.validate !== false;
    const payload = gatherConfigPayload();
    setActionStatus(validate ? "正在保存并验证配置..." : "正在保存配置...", "loading", { persist: true });
    const response = await api("/config", {
        method: "PUT",
        body: JSON.stringify(payload),
    });
    populateConfig(response.config);
    appendLog("config.saved", {
        message: "配置已保存",
        platforms: platformsNeedingValidation(response.config),
    });
    await loadOverview();
    if (validate) {
        await validateConfiguredPlatforms(response.config, options);
    } else if (ui.configSaveStatus) {
        ui.configSaveStatus.textContent = "配置已保存";
    }
}

async function loadOverview() {
    const payload = await api("/overview");
    state.overview = payload;
    state.platforms = payload.platforms || [];
    state.tasks = payload.tasks || [];
    updateCounts();
    renderPlatformGrid();
    renderTasks();
}

async function loadLibrary() {
    const offset = (state.library.page - 1) * LIBRARY_PAGE_SIZE;
    const platforms = selectedLibraryPlatforms();
    const platformQuery = `&platforms=${encodeURIComponent(platforms)}`;
    const path =
        state.library.filter === "all"
            ? `/library?limit=${LIBRARY_PAGE_SIZE}&offset=${offset}${platformQuery}`
            : `/library/${state.library.filter}?limit=${LIBRARY_PAGE_SIZE}&offset=${offset}${platformQuery}`;
    const payload = await api(path);
    if (initializeLibraryPlatformCheckboxes(payload.platforms_with_data || [])) {
        state.library.page = 1;
        return loadLibrary();
    }
    state.library.items = payload.items || [];
    state.library.total = payload.total || 0;
    updateLibraryFilterCounts(payload.platform_counts || {}, payload.total || 0);
    renderLibrary();
}

async function loadWishlist() {
    const payload = await api(`/wishlist?limit=${WISHLIST_FETCH_LIMIT}&offset=0`);
    state.wishlist.items = payload.items || [];
    renderWishlist();
}

async function loadTasks() {
    const payload = await api("/tasks");
    state.tasks = payload.tasks || [];
    renderTasks();
}

async function loadScheduledTasks() {
    const payload = await api("/scheduled-tasks");
    state.scheduled.tasks = payload.tasks || [];
    renderScheduledTasks();
}

async function loadScheduledTaskLogs() {
    if (!document.getElementById("scheduled-task-logs")) return;
    const payload = await api("/scheduled-tasks/logs?limit=200");
    state.scheduled.logs = payload.logs || [];
    renderScheduledTaskLogs();
}

async function loadBackups() {
    const payload = await api("/backups");
    state.backups.items = payload.backups || [];
    renderBackups();
}

async function createFriendBackup(event) {
    event?.preventDefault();
    const userId = document.getElementById("friend-backup-user-id")?.value.trim() || "";
    const includeWatched = Boolean(document.getElementById("friend-backup-watched")?.checked);
    const includeWishlist = Boolean(document.getElementById("friend-backup-wishlist")?.checked);
    if (!userId) throw new Error("请输入好友豆瓣 ID");
    if (!includeWatched && !includeWishlist) throw new Error("至少选择看过或想看");
    if (ui.friendBackupStatus) ui.friendBackupStatus.textContent = `正在读取 ${userId} 的公开数据，请稍候...`;
    setActionStatus(`正在备份 ${userId}...`, "loading", { persist: true });
    const payload = await api("/backups", {
        method: "POST",
        body: JSON.stringify({
            user_id: userId,
            include_watched: includeWatched,
            include_wishlist: includeWishlist,
        }),
    });
    const backup = payload.backup;
    if (ui.friendBackupStatus) {
        ui.friendBackupStatus.textContent = `备份完成：看过 ${backup.watched_count} · 想看 ${backup.wishlist_count}`;
    }
    setActionStatus(`${userId} 的好友备份已完成`, "success");
    await loadBackups();
}

async function openBackupPreview(backupId) {
    setActionStatus("正在加载备份预览...", "loading", { persist: true });
    const payload = await api(`/backups/${encodeURIComponent(backupId)}`);
    state.backups.selected = payload.backup;
    state.backups.previewKind = payload.backup.watched_count ? "watched" : "wishlist";
    if (ui.backupPreviewPanel) ui.backupPreviewPanel.style.display = "";
    renderBackupPreview();
    setActionStatus("备份预览已加载", "success");
}

async function deleteBackup(backupId) {
    const backup = state.backups.items.find((item) => item.id === backupId);
    if (!window.confirm(`确定删除 ${backup?.user_id || "这份"} 好友备份？`)) return;
    await api(`/backups/${encodeURIComponent(backupId)}`, { method: "DELETE" });
    if (state.backups.selected?.id === backupId) {
        state.backups.selected = null;
        if (ui.backupPreviewPanel) ui.backupPreviewPanel.style.display = "none";
    }
    setActionStatus("好友备份已删除", "success");
    await loadBackups();
}

async function loadSystemInfo() {
    const payload = await api("/system");
    renderSystemInfo(payload);
}

async function runPlatformTest(platform, options = {}) {
    const name = platform.toUpperCase();
    const statusEl = platformStatusElement(platform);
    setActionStatus(`正在测试 ${name}...`, "loading", { persist: true });
    if (statusEl) statusEl.textContent = `正在测试 ${name}...`;
    try {
        const payload = await api(`/platforms/${platform}/test`, { method: "POST" });
        const message = prettyStatusMessage(payload.message) || payload.message || `${name} 测试完成`;
        if (options.append !== false) {
            appendLog(`platform.test.${platform}`, payload);
        }
        if (statusEl) statusEl.textContent = message;
        setActionStatus(message, payload.success ? "success" : "error");
        if (options.refresh !== false) {
            await Promise.all([loadOverview(), loadConfig()]);
        }
        return payload;
    } catch (error) {
        if (statusEl) statusEl.textContent = error.message || `${name} 测试失败`;
        setActionStatus(error.message || `${name} 测试失败`, "error");
        throw error;
    }
}

async function runFetchPlatform(platform) {
    const statusEl = platformStatusElement(platform);
    setActionStatus(`正在抓取 ${platform.toUpperCase()} 数据...`, "loading", { persist: true });
    if (statusEl) statusEl.textContent = `正在更新 ${platform.toUpperCase()} 看过数据...`;
    const payload = await api(`/platforms/${platform}/fetch`, { method: "POST" });
    appendLog(`platform.fetch.${platform}`, payload);
    const storedCount = payload.result?.stored_count ?? payload.result?.item_count ?? 0;
    setActionStatus(`${platform.toUpperCase()} 数据已更新${storedCount ? ` · ${storedCount} 条` : ""}`, "success");
    await Promise.all([loadOverview(), loadLibrary(), loadTasks()]);
}

async function runFetchWishlist(platform) {
    const statusEl = platformStatusElement(platform);
    setActionStatus(`正在抓取 ${platform.toUpperCase()} 想看...`, "loading", { persist: true });
    if (statusEl) statusEl.textContent = `正在更新 ${platform.toUpperCase()} 想看数据...`;
    const payload = await api(`/platforms/${platform}/fetch-wishlist`, { method: "POST" });
    appendLog(`platform.wishlist.${platform}`, payload);
    const count = payload.result?.stored_count ?? payload.result?.item_count ?? payload.result?.total ?? 0;
    setActionStatus(`${platform.toUpperCase()} 想看已更新${count ? ` · ${count} 条` : ""}`, "success");
    await Promise.all([loadOverview(), loadWishlist(), loadTasks()]);
}

async function importLegacy(platformOverride = null) {
    const preferred = platformOverride || (state.library.filter === "all" ? "all" : state.library.filter);
    const platforms = preferred === "all" ? PLATFORM_IDS : [preferred];
    setActionStatus(`正在导入 ${preferred === "all" ? "全部旧版 CSV" : platformLabel(preferred)}...`, "loading", { persist: true });
    const results = await Promise.allSettled(
        platforms.map(async (platform) => {
            const payload = await api(`/platforms/${platform}/import-legacy`, { method: "POST" });
            appendLog(`platform.import_legacy.${platform}`, payload);
            return { platform, payload };
        })
    );
    const succeeded = results.filter((result) => result.status === "fulfilled").length;
    const failed = results.length - succeeded;
    results.forEach((result, index) => {
        if (result.status === "rejected") {
            appendLog(`platform.import_legacy.failed.${platforms[index]}`, { message: result.reason?.message || String(result.reason) });
        }
    });
    await Promise.all([loadOverview(), loadLibrary(), loadWishlist(), loadTasks()]);
    setActionStatus(
        failed ? `旧版 CSV 导入完成：成功 ${succeeded}，失败 ${failed}` : `旧版 CSV 导入完成：${succeeded} 个平台已更新`,
        failed ? "warning" : "success"
    );
}

function csvCell(value) {
    const text = String(value ?? "");
    return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function libraryItemToExportRow(item) {
    const sources = item.sources || [];
    const firstSource = sources[0] || {};
    const sourcePlatforms = item.source_platforms || sources.map((source) => source.platform).filter(Boolean);
    const identifiers = item.identifiers || {};
    return {
        title: item.title || "",
        year: item.year || "",
        personal_rating: item.personal_rating ?? item.rating ?? firstSource.rating ?? "",
        rated_at: item.rated_at || firstSource.rated_at || "",
        public_rating: item.public_rating ?? "",
        imdb_id: identifiers.imdb_id || item.imdb_id || "",
        tmdb_id: identifiers.tmdb_id || item.tmdb_id || "",
        douban_id: identifiers.douban_id || item.douban_id || "",
        source_platforms: sourcePlatforms.join("|"),
        source_url: item.source_url || firstSource.source_url || "",
    };
}

function downloadCsv(filename, rows) {
    const columns = ["title", "year", "personal_rating", "rated_at", "public_rating", "imdb_id", "tmdb_id", "douban_id", "source_platforms", "source_url"];
    const csv = [
        columns.join(","),
        ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
    ].join("\n");
    const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

async function fetchAllLibraryForExport(source) {
    const limit = 500;
    let offset = 0;
    let total = Infinity;
    const items = [];
    while (offset < total) {
        const path = source === "merged"
            ? `/library?view=full&limit=${limit}&offset=${offset}`
            : `/library/${source}?view=full&limit=${limit}&offset=${offset}`;
        const payload = await api(path);
        const pageItems = payload.items || [];
        items.push(...pageItems);
        total = payload.total ?? items.length;
        if (!pageItems.length) break;
        offset += pageItems.length;
    }
    return items;
}

async function exportLibrary() {
    const source = document.getElementById("export-source")?.value || "merged";
    setActionStatus(`正在导出 ${source === "merged" ? "合并数据" : platformLabel(source)}...`, "loading", { persist: true });
    const items = await fetchAllLibraryForExport(source);
    const rows = items.map(libraryItemToExportRow);
    const date = new Date().toISOString().slice(0, 10);
    downloadCsv(`cinerecord-${source}-${date}.csv`, rows);
    appendLog("library.export", { source, count: rows.length });
    setActionStatus(`已导出 ${rows.length} 条 ${source === "merged" ? "合并数据" : platformLabel(source)} CSV`, "success");
}

async function previewSync() {
    const requestPayload = gatherSyncPayload();
    state.sync.preview = null;
    state.sync.result = null;
    state.sync.selectedTargetIds = new Set();
    if (ui.syncSummaryText) ui.syncSummaryText.textContent = "正在生成同步预览";
    if (ui.syncSelectionSummary) ui.syncSelectionSummary.textContent = "刷新中";
    if (ui.syncPreviewList) {
        ui.syncPreviewList.style.display = "none";
        ui.syncPreviewList.innerHTML = "";
    }
    if (ui.syncPreviewEmpty) {
        ui.syncPreviewEmpty.style.display = "";
        ui.syncPreviewEmpty.textContent = "正在用本地库生成预览，完成后会显示可执行条目与跳过原因。";
    }
    document.getElementById("execute-sync-btn").disabled = true;
    setActionStatus("正在生成同步预览...", "loading", { persist: true });
    const payload = await api("/sync/preview", {
        method: "POST",
        body: JSON.stringify(requestPayload),
    });
    state.sync.preview = payload.result;
    state.sync.result = null;
    state.sync.selectedTargetIds = new Set(
        (payload.result.items || [])
            .filter(isExecutablePreviewItem)
            .map((item) => item.target_linking_id)
    );
    ui.syncSummaryText.textContent = `${payload.result.direction} · 共 ${payload.result.preview_count} 项`;
    renderSyncItems(payload.result.items, "preview");
    appendLog("sync.preview", payload);
    setActionStatus(`同步预览已更新 · 可执行 ${state.sync.selectedTargetIds.size} / ${payload.result.preview_count} 项`, "success");
    loadTasks().catch(handleError);
}

async function executeSync() {
    if (!state.sync.preview) {
        setActionStatus("先生成同步预览，确认待执行条目后再同步", "warning");
        return;
    }
    if (state.sync.preview && state.sync.selectedTargetIds.size === 0) {
        setActionStatus("先在预览里至少选中一项再执行同步", "warning");
        return;
    }
    state.sync.liveItems = [];
    if (ui.syncLiveProgress) ui.syncLiveProgress.hidden = false;
    if (ui.syncLiveProgressBar) ui.syncLiveProgressBar.style.width = "0%";
    if (ui.syncLiveProgressText) ui.syncLiveProgressText.textContent = "正在刷新两边数据并确认执行清单";
    setActionStatus("正在执行同步...", "loading", { persist: true });
    const payload = await api("/sync/execute", {
        method: "POST",
        body: JSON.stringify(gatherSyncPayload({ forceRefresh: true })),
    });
    state.sync.result = payload.result;
    state.sync.liveItems = payload.result.items || [];
    ui.syncSummaryText.textContent = `${payload.result.direction} · 成功 ${payload.result.success_count} · 跳过 ${payload.result.skipped_count} · 失败 ${payload.result.failed_count}`;
    renderSyncItems(payload.result.items, "result");
    appendLog("sync.execute", payload);
    setActionStatus(`同步执行完成 · 成功 ${payload.result.success_count} · 跳过 ${payload.result.skipped_count} · 失败 ${payload.result.failed_count}`, payload.result.failed_count ? "warning" : "success");
    loadTasks().catch(handleError);
}

async function startTraktAuth() {
    await saveConfig(null, { validate: false });
    setActionStatus("正在启动 Trakt 设备授权...", "loading", { persist: true });
    const payload = await api("/platforms/trakt/device-auth/start", { method: "POST" });
    state.traktDeviceAuth = payload.auth;
    renderTraktDeviceAuthPanel();
    startTraktAuthPolling(payload.auth?.interval || 5);
    const message = `打开 ${payload.auth.verification_url} 并输入验证码 ${payload.auth.user_code}`;
    if (ui.traktAuthStatus) ui.traktAuthStatus.textContent = message;
    const statusEl = platformStatusElement("trakt");
    if (statusEl) statusEl.textContent = message;
    const metaEl = platformMetaElement("trakt");
    if (metaEl) metaEl.textContent = "等待你在 Trakt 页面完成确认";
    setActionStatus(`Trakt 设备授权已开始 · 验证码 ${payload.auth.user_code}`, "success");
    appendLog("trakt.auth.start", payload);
    window.open(payload.auth.verification_url, "_blank", "noopener,noreferrer");
}

async function pollTraktAuth(options = {}) {
    if (!state.traktDeviceAuth?.device_code) {
        throw new Error("请先开始 Trakt 授权");
    }
    const payload = await api("/platforms/trakt/device-auth/poll", {
        method: "POST",
        body: JSON.stringify({ device_code: state.traktDeviceAuth.device_code }),
    });
    const message = traktPollMessage(payload.result);
    if (ui.traktAuthStatus) ui.traktAuthStatus.textContent = message;
    const statusEl = platformStatusElement("trakt");
    if (statusEl) statusEl.textContent = message;
    const metaEl = platformMetaElement("trakt");
    if (metaEl) metaEl.textContent = message;
    if (ui.traktAuthHint) {
        ui.traktAuthHint.textContent =
            payload.result.status === "success"
                ? "授权完成，正在同步 Trakt access token。"
                : payload.result.status === "pending"
                  ? "如果你还没在 Trakt 页面点确认，请先完成确认，再回来点一次“检查 OAuth”。"
                  : payload.result.status === "expired" || payload.result.status === "denied"
                    ? "这组验证码已不可用，请重新点“开始 OAuth”。"
                    : "请检查授权页是否已完成，并在完成后重新检查。";
    }
    const tone =
        payload.result.status === "success"
            ? "success"
            : payload.result.status === "pending"
              ? "loading"
              : "error";
    if (!options.silent || payload.result.status !== "pending") {
        setActionStatus(message, tone, { persist: payload.result.status === "pending" });
    }
    appendLog("trakt.auth.poll", payload);
    if (payload.result.status === "expired" || payload.result.status === "denied" || payload.result.status === "error") {
        stopTraktAuthPolling();
    }
    if (payload.result.status === "success") {
        stopTraktAuthPolling();
        state.traktDeviceAuth = null;
        renderTraktDeviceAuthPanel();
        await Promise.all([loadConfig(), loadOverview()]);
    }
    return payload;
}

async function startTmdbAuth() {
    await saveConfig(null, { validate: false });
    setActionStatus("正在启动 TMDB 授权...", "loading", { persist: true });
    const payload = await api("/platforms/tmdb/auth/start", { method: "POST" });
    const message = "浏览器已打开 TMDB 授权页，授权后回来点“完成 TMDB 授权”";
    if (ui.tmdbAuthStatus) ui.tmdbAuthStatus.textContent = message;
    const statusEl = platformStatusElement("tmdb");
    if (statusEl) statusEl.textContent = message;
    setActionStatus(message, "success");
    appendLog("tmdb.auth.start", payload);
    window.open(payload.auth.auth_url, "_blank", "noopener,noreferrer");
}

async function completeTmdbAuth() {
    setActionStatus("正在完成 TMDB 授权...", "loading", { persist: true });
    const payload = await api("/platforms/tmdb/auth/complete", { method: "POST" });
    const message = `TMDB 授权完成${payload.result?.username ? ` · 用户 ${payload.result.username}` : ""}`;
    if (ui.tmdbAuthStatus) ui.tmdbAuthStatus.textContent = message;
    const statusEl = platformStatusElement("tmdb");
    if (statusEl) statusEl.textContent = message;
    setActionStatus(message, "success");
    appendLog("tmdb.auth.complete", payload);
    await Promise.all([loadConfig(), loadOverview()]);
}

async function syncCookieCloud() {
    await saveConfig(null, { validate: false });
    ui.cookieCloudStatus.textContent = "同步中...";
    setActionStatus("正在从 CookieCloud 同步...", "loading", { persist: true });
    const payload = await api("/cookiecloud/sync", {
        method: "POST",
        body: JSON.stringify({
            host: document.getElementById("cookiecloud-host").value.trim() || null,
            uuid: document.getElementById("cookiecloud-uuid").value.trim() || null,
            password: document.getElementById("cookiecloud-password").value || null,
        }),
    });
    const imported = payload.result?.imported || [];
    const skipped = payload.result?.skipped || [];
    const missing = payload.result?.missing || [];
    const successText = imported.length
        ? imported
              .map((item) =>
                  item.imported_without_validation
                      ? `${item.platform.toUpperCase()} (${item.matched_count} 项，待验证)`
                      : `${item.platform.toUpperCase()} (${item.matched_count} 项)`
              )
              .join("、")
        : "没有可导入的平台";
    ui.cookieCloudStatus.textContent = skipped.length
        ? `部分成功 · ${successText}`
        : `已同步 · ${successText}`;
    appendLog("cookiecloud.sync", payload);
    setActionStatus(ui.cookieCloudStatus.textContent, skipped.length ? "error" : "success");
    if (missing.length) {
        appendLog("cookiecloud.missing", { missing });
    }
    await Promise.all([loadConfig(), loadOverview()]);
}

function handleAuthAction(action) {
    if (action === "tmdb-start") return startTmdbAuth();
    if (action === "tmdb-complete") return completeTmdbAuth();
    if (action === "trakt-start") return startTraktAuth();
    if (action === "trakt-poll") return pollTraktAuth();
    return Promise.resolve();
}

function gatherScheduledTaskPayload() {
    return {
        name: document.getElementById("scheduled-task-name").value.trim(),
        source_platform: document.getElementById("scheduled-task-source").value,
        target_platform: document.getElementById("scheduled-task-target").value,
        schedule: document.getElementById("scheduled-task-cron").value.trim(),
        paused: !document.getElementById("scheduled-task-enabled").checked,
        recent_limit: 100,
        only_new: true,
        overwrite: false,
        default_rating: null,
    };
}

async function saveScheduledTask(event) {
    if (event?.preventDefault) event.preventDefault();
    const payload = gatherScheduledTaskPayload();
    if (!payload.name) {
        throw new Error("请输入任务名称");
    }
    if (!payload.schedule) {
        throw new Error("请输入 Cron 表达式");
    }
    setActionStatus("正在保存定时任务...", "loading", { persist: true });
    const taskId = document.getElementById("scheduled-task-id").value.trim();
    const path = taskId ? `/scheduled-tasks/${taskId}` : "/scheduled-tasks";
    const method = taskId ? "PATCH" : "POST";
    const result = await api(path, {
        method,
        body: JSON.stringify(payload),
    });
    appendLog("scheduled.task.saved", {
        level: "success",
        message: taskId ? `定时任务“${payload.name}”已更新` : `定时任务“${payload.name}”已创建`,
    });
    setActionStatus(taskId ? "定时任务已更新" : "定时任务已创建", "success");
    hideScheduledTaskForm();
    await loadScheduledTasks();
}

async function toggleScheduledTask(taskId, paused) {
    const task = state.scheduled.tasks.find((item) => item.id === taskId);
    if (!task) return;
    await api(`/scheduled-tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify({
            name: task.name,
            source_platform: task.source_platform,
            target_platform: task.target_platform,
            schedule: task.schedule,
            recent_limit: task.recent_limit,
            only_new: task.only_new,
            overwrite: task.overwrite,
            default_rating: task.default_rating,
            paused: !paused,
        }),
    });
    setActionStatus(paused ? "定时任务已启用" : "定时任务已暂停", "success");
    await loadScheduledTasks();
}

async function deleteScheduledTask(taskId) {
    await api(`/scheduled-tasks/${taskId}`, {
        method: "DELETE",
    });
    setActionStatus("定时任务已删除", "success");
    await loadScheduledTasks();
}

async function runScheduledTask(taskId) {
    setActionStatus("正在执行定时任务...", "loading", { persist: true });
    await api(`/scheduled-tasks/${taskId}/run`, {
        method: "POST",
    });
    setActionStatus("定时任务已开始执行", "success");
    await Promise.all([loadScheduledTasks(), loadTasks()]);
}

function setLibraryView(view) {
    state.library.view = view;
    localStorage.setItem("cinerecord_library_view_v3", view);
    document.getElementById("library-view-grid").classList.toggle("active", view === "grid");
    document.getElementById("library-view-list").classList.toggle("active", view === "list");
    renderLibrary();
}

function setWishlistView(view) {
    state.wishlist.view = view;
    localStorage.setItem("cinerecord_legacy_wishlist_view", view);
    document.getElementById("wishlist-view-grid").classList.toggle("active", view === "grid");
    document.getElementById("wishlist-view-list").classList.toggle("active", view === "list");
    renderWishlist();
}

function bindEvents() {
    $$(".nav-tab").forEach((button) => {
        button.addEventListener("click", () => openTab(button.dataset.tab));
    });
    $$(".settings-sub-tab").forEach((button) => {
        button.addEventListener("click", () => switchSettingsPanel(button.dataset.settingsTarget));
    });
    $$(".scheduled-tab-button").forEach((button) => {
        button.addEventListener("click", () => switchScheduledPanel(button.dataset.scheduledTarget));
    });

    bindClick("theme-btn", toggleTheme);
    ui.mobileMenuBtn?.addEventListener("click", openMobileSidebar);
    ui.mobileSidebarOverlay?.addEventListener("click", closeMobileSidebar);
    bindClick("dashboard-refresh-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        refreshAll()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("dashboard-refresh-tasks-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadTasks()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });

    ui.configForm.addEventListener("submit", (event) => {
        const button = event.submitter || document.querySelector("#config-form button[type='submit']");
        setButtonBusy(button, true, "保存中...");
        saveConfig(event)
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("load-config-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "加载中...");
        loadConfig()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("sync-cookiecloud-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "同步中...");
        syncCookieCloud()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("add-custom-site-btn", () => {
        const labelInput = document.getElementById("new-custom-site-name");
        const templateInput = document.getElementById("new-custom-site-template");
        const label = labelInput?.value.trim() || "";
        const template = templateInput?.value.trim() || "";
        if (!label || !template) {
            setActionStatus("请先填写站点名称和链接模板", "error");
            return;
        }
        state.downloadSites.customSites.push({ label, template, enabled: true });
        if (labelInput) labelInput.value = "";
        if (templateInput) templateInput.value = "";
        renderDownloadSiteSettings();
        renderWishlist();
        setActionStatus(`已添加站点 ${label}，保存配置后会写入本地`, "success");
    });
    document.getElementById("download-site-search")?.addEventListener("input", (event) => {
        filterDownloadSites(event.target.value);
    });

    bindClick("refresh-library-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadLibrary()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("import-legacy-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "导入中...");
        importLegacy(button.dataset.platform || null)
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("export-library-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "导出中...");
        exportLibrary()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("import-letterboxd-library-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "导入中...");
        importLegacy("letterboxd")
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("library-view-grid", () => setLibraryView("grid"));
    bindClick("library-view-list", () => setLibraryView("list"));
    ui.libPrevBtn.addEventListener("click", () => {
        if (state.library.page > 1) {
            state.library.page -= 1;
            loadLibrary().catch(handleError);
        }
    });
    ui.libNextBtn.addEventListener("click", () => {
        const totalPages = Math.max(1, Math.ceil((state.library.total || 0) / LIBRARY_PAGE_SIZE));
        if (state.library.page < totalPages) {
            state.library.page += 1;
            loadLibrary().catch(handleError);
        }
    });

    $$(".filter-tab").forEach((button) => {
        button.addEventListener("click", () => {
            $$(".filter-tab").forEach((tab) => tab.classList.toggle("active", tab === button));
            state.library.filter = button.dataset.filter;
            state.library.page = 1;
            loadLibrary().catch(handleError);
        });
    });
    $$('.filter-checkbox input[type="checkbox"]').forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            state.library.page = 1;
            loadLibrary().catch(handleError);
        });
    });

    bindClick("wishlist-view-grid", () => setWishlistView("grid"));
    bindClick("wishlist-view-list", () => setWishlistView("list"));
    bindClick("import-letterboxd-legacy-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "导入中...");
        importLegacy("letterboxd")
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    const wishlistUnmatched = document.getElementById("wishlist-filter-unmatched");
    if (wishlistUnmatched) {
        wishlistUnmatched.checked = state.wishlist.onlyUnmatched;
        wishlistUnmatched.addEventListener("change", () => {
            state.wishlist.onlyUnmatched = wishlistUnmatched.checked;
            localStorage.setItem("cinerecord_wishlist_unmatched", wishlistUnmatched.checked ? "1" : "0");
            state.wishlist.page = 1;
            renderWishlist();
        });
    }
    ui.wishlistPrevBtn.addEventListener("click", () => {
        if (state.wishlist.page > 1) {
            state.wishlist.page -= 1;
            renderWishlist();
        }
    });
    ui.wishlistNextBtn.addEventListener("click", () => {
        const totalPages = Math.max(1, Math.ceil(filteredWishlistItems().length / WISHLIST_PAGE_SIZE));
        if (state.wishlist.page < totalPages) {
            state.wishlist.page += 1;
            renderWishlist();
        }
    });

    $$("#wishlist-source-filters input[data-source]").forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) {
                state.wishlist.sources.add(checkbox.dataset.source);
            } else {
                state.wishlist.sources.delete(checkbox.dataset.source);
            }
            state.wishlist.page = 1;
            renderWishlist();
        });
    });

    bindClick("preview-sync-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "预览中...");
        previewSync()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("toggle-advanced-sync", (event) => {
        const content = document.getElementById("advanced-sync-options");
        const icon = document.getElementById("advanced-sync-icon");
        if (!content) return;
        const isHidden = content.style.display === "none" || !content.style.display;
        content.style.display = isHidden ? "flex" : "none";
        if (icon) icon.style.transform = isHidden ? "rotate(90deg)" : "rotate(0deg)";
        event.currentTarget.style.color = isHidden ? "var(--text-primary)" : "#888";
    });
    bindClick("execute-sync-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "执行中...");
        executeSync()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("select-all-sync-btn", () => {
        const previewItems = state.sync.preview?.items || [];
        state.sync.selectedTargetIds = new Set(
            previewItems
                .filter(isExecutablePreviewItem)
                .map((item) => item.target_linking_id)
        );
        renderSyncItems(previewItems, "preview");
    });
    bindClick("clear-sync-selection-btn", () => {
        state.sync.selectedTargetIds = new Set();
        renderSyncItems(state.sync.preview?.items || [], "preview");
    });
    ["sync-source-select", "sync-target-select", "sync-recent-limit", "sync-refresh-before"].forEach((id) => {
        document.getElementById(id)?.addEventListener("change", markSyncPreviewStale);
    });
    document.querySelectorAll('input[name="rust-sync-mode"]').forEach((input) => {
        input.addEventListener("change", markSyncPreviewStale);
    });
    const defaultRatingEnabled = document.getElementById("sync-default-rating-enabled");
    const defaultRatingInput = document.getElementById("sync-default-rating");
    defaultRatingEnabled?.addEventListener("change", () => {
        if (defaultRatingInput) defaultRatingInput.disabled = !defaultRatingEnabled.checked;
        markSyncPreviewStale();
    });
    defaultRatingInput?.addEventListener("change", markSyncPreviewStale);
    bindClick("refresh-tasks-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadTasks()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("refresh-scheduled-tasks-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadScheduledTasks()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("refresh-scheduled-logs-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadScheduledTaskLogs()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("show-scheduled-task-form-btn", () => populateScheduledTaskForm(null));
    bindClick("hide-scheduled-task-form-btn", hideScheduledTaskForm);
    ui.scheduledTaskForm.addEventListener("submit", (event) => saveScheduledTask(event).catch(handleError));
    $$(".scheduled-preset-btn").forEach((button) => {
        button.addEventListener("click", () => {
            document.getElementById("scheduled-task-cron").value = button.dataset.cron || "";
        });
    });
    ui.friendBackupForm?.addEventListener("submit", (event) => {
        const button = document.getElementById("create-friend-backup-btn");
        setButtonBusy(button, true, "备份中...");
        createFriendBackup(event)
            .catch((error) => {
                if (ui.friendBackupStatus) ui.friendBackupStatus.textContent = error.message;
                handleError(error);
            })
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("refresh-backups-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadBackups()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    bindClick("close-backup-preview-btn", () => {
        if (ui.backupPreviewPanel) ui.backupPreviewPanel.style.display = "none";
    });
    bindClick("refresh-system-info-btn", (event) => {
        const button = event.currentTarget;
        setButtonBusy(button, true, "刷新中...");
        loadSystemInfo()
            .catch(handleError)
            .finally(() => setButtonBusy(button, false));
    });
    $$("[data-backup-preview-kind]").forEach((button) => {
        button.addEventListener("click", () => {
            state.backups.previewKind = button.dataset.backupPreviewKind;
            renderBackupPreview();
        });
    });

    document.addEventListener("click", (event) => {
        const target = event.target.closest(".rust-fetch-btn, .rust-test-btn, .rust-wishlist-btn, .rust-auth-action-btn, .rust-open-tab-btn");
        if (!target) return;
        if (target.classList.contains("rust-open-tab-btn")) {
            openTab(target.dataset.tab || "settings");
        } else if (target.classList.contains("rust-fetch-btn")) {
            setButtonBusy(target, true, "更新中...");
            runFetchPlatform(target.dataset.platform)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        } else if (target.classList.contains("rust-test-btn")) {
            setButtonBusy(target, true, "测试中...");
            runPlatformTest(target.dataset.platform)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        } else if (target.classList.contains("rust-wishlist-btn")) {
            setButtonBusy(target, true, "获取中...");
            runFetchWishlist(target.dataset.platform)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        } else if (target.classList.contains("rust-auth-action-btn")) {
            setButtonBusy(target, true, "处理中...");
            handleAuthAction(target.dataset.action)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        }
    });

    document.addEventListener("click", (event) => {
        const target = event.target.closest(".backup-preview-btn, .backup-delete-btn");
        if (!target) return;
        if (target.classList.contains("backup-preview-btn")) {
            setButtonBusy(target, true, "加载中...");
            openBackupPreview(target.dataset.id)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        } else {
            deleteBackup(target.dataset.id).catch(handleError);
        }
    });

    ui.syncPreviewList?.addEventListener("change", (event) => {
        const checkbox = event.target.closest(".sync-item-checkbox");
        if (!checkbox) return;
        const targetId = checkbox.dataset.targetId;
        if (!targetId) return;
        if (checkbox.checked) {
            state.sync.selectedTargetIds.add(targetId);
        } else {
            state.sync.selectedTargetIds.delete(targetId);
        }
        updateSyncSelectionSummary();
    });

    document.addEventListener("click", (event) => {
        const target = event.target.closest(".scheduled-edit-btn, .scheduled-toggle-btn, .scheduled-delete-btn, .scheduled-run-btn");
        if (!target) return;
        if (target.classList.contains("scheduled-run-btn")) {
            setButtonBusy(target, true, "运行中...");
            runScheduledTask(target.dataset.id)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        } else if (target.classList.contains("scheduled-edit-btn")) {
            const task = state.scheduled.tasks.find((item) => item.id === target.dataset.id);
            if (task) populateScheduledTaskForm(task);
        } else if (target.classList.contains("scheduled-toggle-btn")) {
            setButtonBusy(target, true, target.dataset.paused === "1" ? "启用中..." : "暂停中...");
            toggleScheduledTask(target.dataset.id, target.dataset.paused === "1")
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        } else if (target.classList.contains("scheduled-delete-btn")) {
            setButtonBusy(target, true, "删除中...");
            deleteScheduledTask(target.dataset.id)
                .catch(handleError)
                .finally(() => setButtonBusy(target, false));
        }
    });
}

function connectEvents() {
    const source = new EventSource(`${API_BASE}/events`);
    source.addEventListener("log", (event) => {
        const payload = JSON.parse(event.data);
        const entry = payload.payload || payload;
        appendLog("log", entry);
        const message = entry?.message || "";
        if (message && /同步|刷新|授权/.test(message)) {
            const level = entry.level === "error" ? "error" : entry.level === "success" ? "success" : "loading";
            setActionStatus(message, level, { persist: level === "loading" });
        }
    });
    source.addEventListener("task.updated", () => {
        loadTasks().catch(handleError);
    });
    source.addEventListener("platform.validated", (event) => {
        const payload = JSON.parse(event.data);
        appendLog("platform.validated", payload.payload || payload);
        Promise.all([loadOverview(), loadConfig()]).catch(handleError);
    });
    source.addEventListener("fetch.completed", (event) => {
        const payload = JSON.parse(event.data);
        const result = payload.payload || payload;
        if (!result.sync_refresh) appendLog("fetch.completed", result);
        Promise.all([loadOverview(), loadLibrary(), loadWishlist(), loadTasks()]).catch(handleError);
    });
    source.addEventListener("sync.preview.ready", (event) => {
        const payload = JSON.parse(event.data);
        if (payload.payload) {
            state.sync.preview = payload.payload;
            state.sync.selectedTargetIds = new Set(
                (payload.payload.items || [])
                    .filter(isExecutablePreviewItem)
                    .map((item) => item.target_linking_id)
            );
            ui.syncSummaryText.textContent = `${payload.payload.direction} · 共 ${payload.payload.preview_count} 项`;
            renderSyncItems(payload.payload.items, "preview");
        }
        appendLog("sync.preview.ready", payload.payload || payload);
    });
    source.addEventListener("sync.completed", (event) => {
        const payload = JSON.parse(event.data);
        const isScheduledTask = String(payload.task_id || "").startsWith("scheduled-");
        if (payload.payload) {
            state.sync.result = payload.payload;
            ui.syncSummaryText.textContent = `${payload.payload.direction} · 成功 ${payload.payload.success_count} · 跳过 ${payload.payload.skipped_count} · 失败 ${payload.payload.failed_count}`;
            renderSyncItems(payload.payload.items, "result");
        }
        if (!isScheduledTask) appendLog("sync.completed", payload.payload || payload);
        if (ui.syncLiveProgressBar) ui.syncLiveProgressBar.style.width = "100%";
        if (ui.syncLiveProgressText) {
            ui.syncLiveProgressText.textContent = `完成 · 成功 ${payload.payload?.success_count || 0} · 跳过 ${payload.payload?.skipped_count || 0} · 失败 ${payload.payload?.failed_count || 0}`;
        }
        Promise.all([loadOverview(), loadLibrary(), loadTasks()]).catch(handleError);
    });
    source.addEventListener("sync.progress", (event) => {
        const payload = JSON.parse(event.data);
        const progress = payload.payload || payload;
        const current = Number(progress.current || 0);
        const total = Number(progress.total || 0);
        const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 8;
        if (ui.syncLiveProgress) ui.syncLiveProgress.hidden = false;
        if (ui.syncLiveProgressBar) ui.syncLiveProgressBar.style.width = `${percent}%`;
        if (ui.syncLiveProgressText) ui.syncLiveProgressText.textContent = progress.message || "同步处理中";
        if (ui.syncSummaryText) {
            const counts = [
                progress.success_count !== undefined ? `成功 ${progress.success_count}` : "",
                progress.skipped_count !== undefined ? `跳过 ${progress.skipped_count}` : "",
                progress.failed_count !== undefined ? `失败 ${progress.failed_count}` : "",
            ].filter(Boolean);
            ui.syncSummaryText.textContent = total > 0
                ? `${current} / ${total}${counts.length ? ` · ${counts.join(" · ")}` : ""}`
                : progress.message || "同步处理中";
        }
        if (progress.phase === "item.completed" && progress.item) {
            state.sync.liveItems.push(progress.item);
            state.sync.result = {
                direction: progress.direction,
                success_count: progress.success_count || 0,
                skipped_count: progress.skipped_count || 0,
                failed_count: progress.failed_count || 0,
                items: state.sync.liveItems,
            };
            renderSyncItems(state.sync.liveItems, "result");
        }
        const shouldLog =
            progress.phase === "execution.prepared" ||
            progress.phase === "rate_limit.wait" ||
            progress.status === "failed" ||
            (total > 0 && current === total) ||
            (progress.phase === "item.completed" && current % 10 === 0);
        if (shouldLog) appendLog("sync.progress", progress);
        setActionStatus(progress.message || "同步处理中", progress.status === "failed" ? "warning" : "loading", {
            persist: true,
        });
    });
    source.addEventListener("scheduled.task.updated", () => {
        loadScheduledTasks().catch(handleError);
    });
    source.addEventListener("scheduled.task.log", (event) => {
        const payload = JSON.parse(event.data);
        appendLog("scheduled.task.log", payload.payload || payload);
    });
    source.onerror = () => {
        const now = Date.now();
        if (now - state.logs.lastSseErrorAt < 30000) return;
        state.logs.lastSseErrorAt = now;
        appendLog("sse.error", { message: "事件流暂时断开，浏览器会自动重连。" });
    };
}

function handleError(error) {
    console.error(error);
    appendLog("error", { message: error?.message || String(error) });
    setActionStatus(error?.message || String(error), "error");
}

async function refreshStep(label, loader) {
    try {
        await loader();
        return true;
    } catch (error) {
        appendLog("error", { message: `${label}加载失败：${error?.message || String(error)}` });
        return false;
    }
}

async function refreshAll() {
    const results = await Promise.all([
        refreshStep("服务状态", loadHealth),
        refreshStep("配置", loadConfig),
        refreshStep("概览", loadOverview),
        refreshStep("片库", loadLibrary),
        refreshStep("想看", loadWishlist),
        refreshStep("任务", loadTasks),
        refreshStep("定时任务", loadScheduledTasks),
    ]);
    if (results.some((ok) => !ok)) {
        setActionStatus("部分数据加载失败，已保留可用页面；请查看左侧日志", "warning");
    }
    return results.every(Boolean);
}

async function init() {
    applyTheme();
    setAppLoading(true);
    setLibraryView(state.library.view);
    setWishlistView(state.wishlist.view);
    renderTraktDeviceAuthPanel();
    hideScheduledTaskForm();
    bindEvents();
    connectEvents();
    try {
        const loaded = await refreshAll();
        if (loaded) {
            const configuredCount = (state.platforms || []).filter(
                (platform) => platform.auth_type !== "csv" && platform.status?.config_present
            ).length;
            if (configuredCount === 0) {
                setActionStatus("欢迎使用 CineRecord · 请先在设置中连接至少一个平台", "warning");
            } else {
                setActionStatus("已加载最新账号和片库状态", "success", { reset: true, timeout: 2500 });
            }
        }
    } catch (error) {
        handleError(error);
    } finally {
        setAppLoading(false);
    }
}

document.addEventListener("DOMContentLoaded", init);
