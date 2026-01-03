# agent.md - AI Agent Development Guide

> This file serves as the primary context and memory for AI Agents working on CineRecord Hub. It facilitates rapid onboarding and context restoration.

## 🎯 Project Overview

**CineRecord Hub** is a local, privacy-first movie data synchronization tool. It acts as a central hub to sync ratings and watch history across multiple platforms.

**Supported Platforms:**
- **Douban**: Webview/Cookie auth, full sync.
- **IMDb**: Webview/Cookie auth, full sync.
- **Trakt**: OAuth Device Flow, full sync.
- **TMDB**: API Key + Session auth, rating sync.
- **Letterboxd**: CSV import/export.

## 🚀 Quick Start

```bash
cd /Users/gawaintan/workSpace/Python/CineRecord
python web/app.py
# Access at http://127.0.0.1:8000
```

## 📁 Key Files & Architecture

| File/Directory | Responsibility |
|----------------|----------------|
| `web/app.py` | Flask backend entry, Socket.IO event handlers, main API logic. |
| `web/logic.py` | Core synchronization logic (diff calculation, rating normalization). |
| `web/static/script.js` | Frontend SPA logic, Socket.IO client, UI state management. |
| `web/static/scheduled_tasks.js` | Scheduler frontend logic (Cron tasks). |
| `web/templates/index.html` | Single Page Application (SPA) HTML structure. |
| `scrapers/` | Individual platform scraper modules (Douban, IMDb, Trakt, TMDB). |
| `web/auth_helper.py` | macOS-specific Webview authentication helper. |

### 🔧 Core Mechanisms

#### 1. Communication (Socket.IO)
The frontend and backend communicate exclusively via Socket.IO for real-time feedback.
- **Frontend**: `socket.emit('event_name', data)`
- **Backend**: `@socketio.on('event_name')`
- **Updates**: Backend pushes updates via `emit('log', ...)` or specific event channels.

#### 2. Authentication Strategy
- **Douban/IMDb**: Uses `auth_helper.py` to launch a native macOS Webview. It intercepts cookies from `NSHTTPCookieStorage` after user login. Fallback to manual Cookie pasting in Settings.
- **Trakt**: Standard OAuth 2.0 Device Flow. User enters a code on the Trakt website.
- **TMDB**: v3 API Key + Session ID flow.

#### 3. Task Scheduler
- **Frontend**: `scheduled_tasks.js` manages the UI for creating Cron-based tasks.
- **Backend**: `apscheduler` (BackgroundScheduler) executes sync jobs asynchronously.

## ⚠️ Known Functionality Status

| Feature | Status | Note |
|---------|--------|------|
| **Sync Engine** | ✅ Stable | Handles large datasets via pagination (10/page) to prevent timeout. |
| **Scheduler** | ✅ Stable | Supports recurring syncs (Daily, Weekly, etc.). |
| **Douban Auth** | ⚠️ Flaky | Webview cookie capture sometimes requires manual "Done" click. |
| **UI/UX** | ✅ Polished | Dark mode, modular cards, accessible Settings. |

## 🔧 Common Maintenance Tasks

### Adding a New Platform
1.  **Scraper**: Create `scrapers/new_platform.py`. Implement `get_ratings()` and `mark_rate()`.
2.  **Logic**: Update `web/logic.py` to include the new platform in `merge_data()`.
3.  **UI**: Add card in `index.html` (Accounts tab) and logic in `script.js`.
4.  **Logo**: Add logo asset or emoji.

### Localization (i18n)
-   All UI text must be keys in `web/static/i18n.js`.
-   Use `data-i18n="key"` attributes in HTML.
-   Don't hardcode text in JS/HTML.

## 🔗 Related Documentation
-   `README.md`: User-facing documentation.
-   `ROADMAP.md`: Project milestones and future plans.
