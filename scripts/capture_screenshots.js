#!/usr/bin/env node

/**
 * Automated Screenshot Generator for CineRecord
 * Captures high-resolution Retina screenshots for documentation in both Chinese and English.
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
            height: 900,
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
        const dashPath = path.join(OUTPUT_DIR, `dashboard_${lang.suffix}.png`);
        await page.screenshot({ path: dashPath });
        console.log(`     Saved: ${dashPath}`);

        // 2. Library (Data) Tab
        console.log('  -> Library');
        await page.evaluate(() => {
            if (typeof openTab === 'function') openTab('data');
        });
        await wait(1200);
        const libPath = path.join(OUTPUT_DIR, `library_${lang.suffix}.png`);
        await page.screenshot({ path: libPath });
        console.log(`     Saved: ${libPath}`);

        // 3. Wishlist Tab
        console.log('  -> Wishlist');
        await page.evaluate(() => {
            if (typeof openTab === 'function') openTab('wishlist');
        });
        await wait(1200);
        const wishPath = path.join(OUTPUT_DIR, `wishlist_${lang.suffix}.png`);
        await page.screenshot({ path: wishPath });
        console.log(`     Saved: ${wishPath}`);

        // 4. Sync Tab
        console.log('  -> Sync');
        await page.evaluate(async () => {
            if (typeof openTab === 'function') openTab('sync');
            const previewBtn = document.getElementById('preview-sync-btn');
            if (previewBtn) previewBtn.click();
        });
        await wait(2500);
        const syncPath = path.join(OUTPUT_DIR, `sync_${lang.suffix}.png`);
        await page.screenshot({ path: syncPath });
        console.log(`     Saved: ${syncPath}`);
    }

    await browser.close();

    console.log('\n✨ All screenshots captured successfully in docs/images/!\n');
}

capture().catch((err) => {
    console.error('Error capturing screenshots:', err);
    process.exit(1);
});
