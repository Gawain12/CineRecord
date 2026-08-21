# 🎬 CineRecord

CineRecord is a local-first cross-platform movie collection manager, rating synchronization, and wishlist organizer.

This project is a complete full-stack rewrite of the original Python version using a high-performance **Rust** backend and local **SQLite** database. The web interface is directly served by a single compiled binary—**no Python, Node.js, or external database services are required**.

<div align="center">
  <img src="docs/images/app_demo_dual.webp" width="800" alt="CineRecord Workflow Demo">
  <p><i>Workflow Walkthrough: Account status, manual/scheduled sync runs (Bilingual Demo)</i></p>
</div>

---

## 📸 Screenshots

<div align="center">
  <img src="docs/images/dashboard_en.png" width="800" alt="Dashboard Preview">
  <p><i>Dashboard: Account connectivity status and overall stats</i></p>

  <br>

  <img src="docs/images/library_en.png" width="800" alt="Library Preview">
  <p><i>Unified Library: Cross-platform movie collection aggregator & search</i></p>

  <br>

  <img src="docs/images/sync_en.png" width="800" alt="Sync Page Preview">
  <p><i>Sync Console: Delta preview, individual item actions, and live SSE logging</i></p>

  <br>

  <img src="docs/images/wishlist_en.png" width="800" alt="Wishlist Preview">
  <p><i>Wishlist: Cross-platform wishlist aggregation, media server matching & multi-site search</i></p>
</div>

---

## ✨ Key Features

### 🌐 Platform Compatibility Matrix

| Platform | Ratings Fetch | Watchlist Fetch | Sync Target | Auth & Integration Method |
| :--- | :---: | :---: | :---: | :--- |
| **🎬 Douban** | ✅ | ✅ | ✅ | Cookie Import & Verification / Web Binding |
| **⭐ IMDb** | ✅ | ✅ | ✅ | Cookie-based connection validation |
| **🎯 Trakt** | ✅ | ✅ | ✅ | Official OAuth Device flow / Two-way sync for ratings and watchlists |
| **🎬 TMDB** | ✅ | ✅ | ✅ | API Key + User Session verification |
| **🎨 CinePersona** | ✅ | ✅ | ✅ | API Key Open API bidirectional ratings & wishlist sync |
| **✉️ Letterboxd** | ✅ (Import) | ✅ (Import) | ⚠️ (Export) | Local `diary.csv` / `watchlist.csv` import/export |
| **🎬 Media Server** | ✅ (Match) | — | — | Emby / Jellyfin / Plex API integration & direct web playback |

### ⚡ Core Capabilities

* **🚀 Lightweight & High Performance**: The compiled binary is only ~10MB with extremely low memory usage (typically ~15MB resident), ensuring instant app startup and fast response times.
* **📊 Unified Library**: Consolidates watched history from all platforms, deduplicates entries using IMDb/TMDb IDs, and enriches data with director, genres, countries, and runtimes.
* **📅 Smart Wishlist**: Aggregate watchlists across different accounts. Features single-site views, cross-platform diff matrices, and **two-way wishlist synchronization**.
* **🔍 Media Server Deduplication & Direct Play**: Connects to your Emby, Jellyfin, or Plex library. Automatically scans your wishlist against your media server to find missing content. Clicking file names directly launches native web playback.
* **🌐 Multi-Site 1-Click Search**: For missing wishlist items, built-in search buttons (KG, HDR, Tik, IN, HDB, OMG, BHD, ADE) provide instant lookups with automatic IMDb ID and title fallbacks.
* **⚙️ Visual Scheduler**: Built-in cron-based background scheduler for automated sync runs with a live log console streaming via SSE.
* **🌍 Bilingual & Adaptive Theme**: Seamless instantaneous Chinese/English switching with polished dark and light themes.
* **🔒 Privacy-First & Offline-First**: Sensitive credentials (Cookies, API keys, OAuth Tokens) are encrypted locally. Zero telemetry code—your data is 100% yours.

---

## 🚀 Quick Start

### Run from Source

Ensure you have the Rust toolchain installed (Rust 1.75+ recommended):

```bash
# 1. Clone the repository
git clone https://github.com/Gawain12/CineRecord.git
cd CineRecord

# 2. Run the Axum server
cargo run -p cinerecord-server
```

Open your browser and navigate to [http://127.0.0.1:18000](http://127.0.0.1:18000).

### Docker Deployment

For running on servers or NAS devices:

```bash
docker compose up -d --build
```
The service will be listening on `http://127.0.0.1:18000`. Persistent database and configuration files are stored locally in the `./cinerecord-data` directory.

---

## 📦 Packaging and Distribution

CineRecord features automated native packaging scripts to bundle everything into standalone desktop apps without external runtimes:

### 🍎 macOS
Runs the packaging script to generate high-resolution `.icns` assets using `sips` and `iconutil`, compile release builds, and wrap them in DMG disk images and ZIP archives:
```bash
./scripts/package_rust_macos.sh
```
* **Output**: `dist-rust/CineRecord.app` / `CineRecord-macOS-arm64.dmg`.
* Double-clicking starts the background daemon and opens the web portal in your default browser.

### 🔌 Windows
Runs the script in PowerShell to embed metadata icons and build a single executable:
```powershell
.\scripts\package_rust_windows.ps1
```
* **Output**: `dist-rust/CineRecord-Windows-x64.exe` and its companion ZIP release.

---

## ⚙️ Configuration & Environment Variables

CineRecord stores configuration, SQLite databases, and logs in standard system paths:
* **macOS**: `~/Library/Application Support/CineRecord`
* **Windows**: `%APPDATA%\CineRecord`
* **Linux**: `$XDG_DATA_HOME/cinerecord` or `~/.local/share/cinerecord`

Behavior can be customized using the following environment variables:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `CINERECORD_HOME` | System Default Path | Overrides the root directory for configuration, databases, and logs. |
| `CINERECORD_HOST` | `127.0.0.1` | IP address to bind the service to. |
| `CINERECORD_PORT` | `18000` | Port number to bind the service to. |
| `CINERECORD_PORTABLE` | `false` | If set to `true`, stores all runtime data in the current working directory (perfect for USB drives). |
| `RUST_LOG` | `info,tower_http=warn` | Log level for the Rust server console. |

---

## 🛡️ Sync Protection Mechanisms

To prevent sync conflicts and data corruption on your target profiles:
1. **Double-Fetch Verification**: Sync previews are initially created from local databases for speed. Before committing writes, a **silent remote refresh** is triggered to verify no newer changes exist on the cloud.
2. **Add-Only Mode**: The sync defaults to "Only New" mode. Local unrated movies will never overwrite existing ratings on target platforms.
3. **TV Show Filter**: Because TMDB, Letterboxd, and CinePersona handle TV show structures differently, sync jobs auto-filter standard multi-season TV shows to avoid messy cross-platform logging.
4. **Itemized Review**: Before running any sync, users can manually select, deselect, or review every single action item in the preview list.

---

## ♻️ Migrating History from Original Python Version

If you are an existing user of the Python version of CineRecord, you don't need to re-fetch all historical data:
1. Open CineRecord and go to the Library page.
2. Click **"Import CSV"**.
3. The server will search for Python-era exports in `data/` (e.g. `douban_*_wish.csv`, `imdb_*_ratings.csv`) and import them into the SQLite database.

---

## 📜 License

[MIT License](./LICENSE)
