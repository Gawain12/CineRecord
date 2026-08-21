#!/usr/bin/env node

/**
 * Automated Screenshot Generator for CineRecord
 * Captures high-resolution Retina screenshots for documentation in both Chinese and English
 * with full anonymization and privacy protection.
 */

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
const { spawn } = require('child_process');

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const BASE_URL = process.env.CINERECORD_URL || 'http://127.0.0.1:18000';
const OUTPUT_DIR = path.resolve(__dirname, '../docs/images');

async function isServerRunning(url) {
    try {
        const res = await fetch(`${url}/api/v2/health`);
        return res.ok;
    } catch {
        return false;
    }
}

async function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function anonymize(page) {
    await page.evaluate(() => {
        // 1. Sidebar Accounts
        const doubanUser = document.getElementById('summary-id-douban') || document.querySelector('#summary-douban .summary-id');
        if (doubanUser) doubanUser.textContent = 'MovieFan';
        const imdbUser = document.getElementById('summary-id-imdb') || document.querySelector('#summary-imdb .summary-id');
        if (imdbUser) imdbUser.textContent = 'ur12345678';
        const traktUser = document.getElementById('summary-id-trakt') || document.querySelector('#summary-trakt .summary-id');
        if (traktUser) traktUser.textContent = 'trakt_user';
        const tmdbUser = document.getElementById('summary-id-tmdb') || document.querySelector('#summary-tmdb .summary-id');
        if (tmdbUser) tmdbUser.textContent = 'tmdb_user';
        const cpUser = document.getElementById('summary-id-cinepersona') || document.querySelector('#summary-cinepersona .summary-id');
        if (cpUser) cpUser.textContent = 'cinepersona';

        // 2. Settings Account Cards
        const doubanName = document.getElementById('douban-display-name');
        if (doubanName) doubanName.textContent = 'MovieFan';
        const doubanId = document.getElementById('douban-user-id-display');
        if (doubanId) doubanId.textContent = 'moviefan';

        const imdbName = document.getElementById('imdb-display-name');
        if (imdbName) imdbName.textContent = 'IMDb User';
        const imdbId = document.getElementById('imdb-user-id-display');
        if (imdbId) imdbId.textContent = 'ur12345678';

        const traktName = document.getElementById('trakt-display-name');
        if (traktName) traktName.textContent = 'trakt_user';
        const traktId = document.getElementById('trakt-user-id-display');
        if (traktId) traktId.textContent = 'trakt_user';

        const tmdbName = document.getElementById('tmdb-display-name');
        if (tmdbName) tmdbName.textContent = 'tmdb_user';
        const tmdbId = document.getElementById('tmdb-user-id-display');
        if (tmdbId) tmdbId.textContent = '12345678';

        // 3. Settings Inputs & Sensitive fields
        const mediaServerUrl = document.getElementById('media-server-url-input');
        if (mediaServerUrl) mediaServerUrl.value = 'http://192.168.1.100:8096';
        const mediaServerKey = document.getElementById('media-server-key-input');
        if (mediaServerKey) mediaServerKey.value = '••••••••••••••••••••••••••••••••';

        const ccHost = document.getElementById('cookiecloud-host-input');
        if (ccHost) ccHost.value = 'https://cookiecloud.example.com';
        const ccKey = document.getElementById('cookiecloud-key-input');
        if (ccKey) ccKey.value = '••••••••••••••••';
        const ccPass = document.getElementById('cookiecloud-password-input');
        if (ccPass) ccPass.value = '••••••••••••••••';

        // 4. Sidebar & Terminal Logs Sanitization
        const logContainer = document.querySelector('.log-container-sidebar');
        if (logContainer) {
            logContainer.innerHTML = '<p class="info">[15:00:00] CineRecord core ready</p><p class="success">[15:00:01] All platforms connected</p><p class="info">[15:00:02] Local SQLite database loaded</p>';
        }
        const syncTerminal = document.querySelector('.sync-terminal');
        if (syncTerminal) {
            syncTerminal.innerHTML = '<p class="info">[15:05:00] 🚀 Generating sync preview...</p><p class="success">[15:05:01] ✅ Diff preview ready: 1874 items examined</p><p class="success">[15:05:02] ✅ All candidate records analyzed</p>';
        }
    });
}

async function capture() {
    if (!fs.existsSync(CHROME_PATH)) {
        console.error(`Chrome executable not found at: ${CHROME_PATH}`);
        process.exit(1);
    }

    if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    }

    let serverProcess = null;
    const running = await isServerRunning(BASE_URL);
    if (!running) {
        console.log('🚀 CineRecord server is not running, starting it in background...');
        serverProcess = spawn('cargo', ['run', '-p', 'cinerecord-server'], {
            cwd: path.resolve(__dirname, '..'),
            stdio: 'ignore',
            detached: true,
        });

        let ready = false;
        for (let i = 0; i < 30; i++) {
            await wait(1000);
            if (await isServerRunning(BASE_URL)) {
                ready = true;
                break;
            }
        }
        if (!ready) {
            console.error('Failed to connect to CineRecord server after starting.');
            if (serverProcess) serverProcess.kill();
            process.exit(1);
        }
    }

    console.log('🌐 Launching headless browser...');
    const browser = await puppeteer.launch({
        executablePath: CHROME_PATH,
        headless: 'new',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--hide-scrollbars',
            '--disable-web-security',
            '--window-size=1440,920',
        ],
        defaultViewport: {
            width: 1440,
            height: 1000,
            deviceScaleFactor: 2, // Retina 2x
        },
    });

    const page = await browser.newPage();

    // Disable CSS animations for consistent rendering
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);

    console.log(`🔗 Navigating to ${BASE_URL}...`);
    await page.goto(BASE_URL, { waitUntil: 'networkidle2' });
    await wait(1500);

    const languages = [
        { code: 'zh-CN', suffix: 'cn' },
        { code: 'en', suffix: 'en' },
    ];

    for (const lang of languages) {
        console.log(`\n📸 Capturing screenshots for language: ${lang.code} (${lang.suffix})...`);

        // Switch Language
        await page.evaluate((targetLang) => {
            if (window.i18n && window.i18n.switchLanguage) {
                window.i18n.switchLanguage(targetLang);
            }
        }, lang.code);
        await wait(800);

        // 1. Dashboard Tab
        console.log('  -> Dashboard');
        await page.evaluate(() => {
            if (typeof openTab === 'function') openTab('dashboard');
        });
        await wait(1000);
        await anonymize(page);
        const dashPath = path.join(OUTPUT_DIR, `dashboard_${lang.suffix}.png`);
        await page.screenshot({ path: dashPath });
        console.log(`     Saved: ${dashPath}`);

        // 2. Library (Data) Tab
        console.log('  -> Library');
        await page.evaluate(() => {
            if (typeof openTab === 'function') openTab('data');
        });
        await wait(1200);
        await anonymize(page);
        const libPath = path.join(OUTPUT_DIR, `library_${lang.suffix}.png`);
        await page.screenshot({ path: libPath });
        console.log(`     Saved: ${libPath}`);

        // 3. Wishlist Tab
        console.log('  -> Wishlist');
        await page.evaluate(() => {
            if (typeof openTab === 'function') openTab('wishlist');
        });
        await wait(1200);
        await anonymize(page);
        const wishPath = path.join(OUTPUT_DIR, `wishlist_${lang.suffix}.png`);
        await page.screenshot({ path: wishPath });
        console.log(`     Saved: ${wishPath}`);

        // 4. Sync Tab
        console.log('  -> Sync');
        await page.evaluate(async () => {
            if (typeof openTab === 'function') openTab('sync');
            const sourceSelect = document.getElementById('sync-source-select');
            if (sourceSelect) {
                sourceSelect.value = 'douban';
                sourceSelect.dispatchEvent(new Event('change'));
            }
            const targetSelect = document.getElementById('sync-target-select');
            if (targetSelect) {
                targetSelect.value = 'tmdb';
                targetSelect.dispatchEvent(new Event('change'));
            }
            const previewBtn = document.getElementById('preview-sync-btn');
            if (previewBtn) previewBtn.click();
        });
        await wait(3000);
        await page.evaluate((isEnglish) => {
            const formPanel = document.getElementById('scheduled-task-form-panel');
            if (formPanel) formPanel.style.display = 'block';
            const placeholder = document.getElementById('task-form-placeholder') || document.querySelector('.scheduled-right-panel > div:not(#scheduled-task-form-panel)');
            if (placeholder) placeholder.style.display = 'none';

            const nameInput = document.getElementById('scheduled-task-name');
            if (nameInput) nameInput.value = isEnglish ? 'Daily Douban to TMDB Sync' : '每日豆瓣到TMDB增量同步';
            const srcSelect = document.getElementById('scheduled-task-source');
            if (srcSelect) srcSelect.value = 'douban';
            const tgtSelect = document.getElementById('scheduled-task-target');
            if (tgtSelect) tgtSelect.value = 'tmdb';
            const cronInput = document.getElementById('scheduled-task-cron');
            if (cronInput) cronInput.value = '0 2 * * *';

            if (window.i18n && window.i18n.applyTranslations) {
                window.i18n.applyTranslations();
            }
        }, lang.code === 'en');
        await wait(600);
        await anonymize(page);
        const syncPath = path.join(OUTPUT_DIR, `sync_${lang.suffix}.png`);
        await page.screenshot({ path: syncPath });
        console.log(`     Saved: ${syncPath}`);

        // 5. Settings Tab
        console.log('  -> Settings');
        await page.evaluate(() => {
            if (typeof openTab === 'function') openTab('settings');
        });
        await wait(1200);
        await anonymize(page);
        const settingsPath = path.join(OUTPUT_DIR, `settings_${lang.suffix}.png`);
        await page.screenshot({ path: settingsPath });
        console.log(`     Saved: ${settingsPath}`);
    }

    await browser.close();

    console.log('\n✨ All sanitized screenshots captured successfully in docs/images/!\n');
}

capture().catch((err) => {
    console.error('Error capturing screenshots:', err);
    process.exit(1);
});
