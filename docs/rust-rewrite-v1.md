# Rust Rewrite V1

This branch introduces the first parallel Rust stack for CineRecord without replacing the existing Python/Flask app on `main`.

## Goals

- Keep the Python app runnable on `http://127.0.0.1:8000`
- Run a separate Rust service on `http://127.0.0.1:18000`
- Use isolated v2 storage under `config/v2`, `data/v2`, and `logs/v2`
- Move new frontend communication to `REST + SSE` instead of `Socket.IO`

## Current Scope

Implemented in this initial slice:

- Rust workspace with layered crates:
  - `cinerecord-core`
  - `cinerecord-storage`
  - `cinerecord-platforms`
  - `cinerecord-jobs`
  - `cinerecord-server`
- Axum server bootstrap with static asset serving
- `config/v2/config.toml` bootstrap
- `data/v2/app.db` bootstrap with initial SQLite schema
- `logs/v2/server.log` server logging
- REST endpoints under `/api/v2/*`
- SSE event stream under `/api/v2/events`
- Rust-specific UI entry at `/` using [`web/templates/rust_v2.html`](../web/templates/rust_v2.html) and [`web/static/rust-v2.js`](../web/static/rust-v2.js)
- Real TMDB connection test and rated-movie fetch path
- Trakt movie fetch path
- `tmdb <-> trakt` sync preview pipeline
- `tmdb <-> trakt` sync execute pipeline
- Trakt device-auth API endpoints and config persistence
- TMDB browser auth start/complete endpoints
- Legacy CSV import into the Rust v2 SQLite library for TMDB, Trakt, IMDb, and Douban
- Library pagination on `/api/v2/library`
- Browser-assisted Douban / IMDb auth bridge with cookie validation and config write-back
- CookieCloud sync for Douban / IMDb with key-cookie filtering and safe overwrite rules
- Scheduled sync task CRUD, immediate run, persistent logs, and SSE updates
- Restored desktop-style Rust UI flows for dashboard, data, sync, wishlist, and settings

Partially implemented:

- Trakt requires your own `client_id` and `client_secret` in Rust v2 settings before device auth can start
- TMDB rating write path is implemented, but still depends on a valid user `session_id`
- TMDB browser auth requires you to click approve in the opened TMDB page before completing auth

Not implemented yet:

- Embedded desktop login / WebView auth window
- Full sync pipeline
- Trakt OAuth web callback flow
- IMDb, Letterboxd, Douban full fetch implementations

## Run The Rust Stack

From the repo root:

```bash
rtk cargo run -p cinerecord-server
```

Then open:

- Rust v2: `http://127.0.0.1:18000`
- Python legacy app: `http://127.0.0.1:8000`

## Dev Workflow

- Run shell commands with the `rtk` prefix, for example `rtk cargo check` and `rtk cargo test -p cinerecord-platforms --lib`
- Review this branch with the code review graph MCP so new Rust modules are checked with dependency context instead of only `git diff`

## v2 Storage Layout

The Rust service does not reuse the Python runtime data:

```text
config/v2/config.toml
data/v2/app.db
data/v2/platforms/
data/v2/exports/
logs/v2/server.log
```

You can remove `data/v2/` and restart the Rust server to reinitialize the v2 database.

## API Surface

Implemented endpoints:

- `GET /api/v2/health`
- `GET /api/v2/config`
- `PUT /api/v2/config`
- `GET /api/v2/platforms`
- `POST /api/v2/platforms/{platform}/test`
- `POST /api/v2/platforms/{platform}/browser-auth/start`
- `POST /api/v2/platforms/{platform}/fetch`
- `POST /api/v2/platforms/{platform}/fetch-wishlist`
- `POST /api/v2/platforms/{platform}/import-legacy`
- `POST /api/v2/auth/callback`
- `POST /api/v2/cookiecloud/sync`
- `POST /api/v2/platforms/tmdb/auth/start`
- `POST /api/v2/platforms/tmdb/auth/complete`
- `POST /api/v2/platforms/trakt/device-auth/start`
- `POST /api/v2/platforms/trakt/device-auth/poll`
- `GET /api/v2/library`
- `GET /api/v2/library/{platform}`
- `POST /api/v2/sync/preview`
- `POST /api/v2/sync/execute`
- `GET /api/v2/tasks`
- `POST /api/v2/tasks`
- `PATCH /api/v2/tasks/{task_id}`
- `DELETE /api/v2/tasks/{task_id}`
- `GET /api/v2/scheduled-tasks`
- `POST /api/v2/scheduled-tasks`
- `GET /api/v2/scheduled-tasks/{task_id}`
- `PATCH /api/v2/scheduled-tasks/{task_id}`
- `DELETE /api/v2/scheduled-tasks/{task_id}`
- `POST /api/v2/scheduled-tasks/{task_id}/run`
- `GET /api/v2/scheduled-tasks/logs`
- `GET /api/v2/events`

Current sync support is intentionally limited to `tmdb <-> trakt`. Other sync directions still need platform-specific write implementations.

## Legacy Data Bootstrap

The Rust UI now has an `Import legacy CSV` action for each platform card in the Rust page.

What it does:

- Looks for existing Python-era CSV exports under `data/`
- Parses the matching platform file
- Writes normalized movie records into `data/v2/app.db`
- Emits task and fetch events so the Rust page updates immediately

Validated import paths:

- `tmdb_*_ratings.csv`
- `trakt_*_ratings.csv`
- `imdb_*_ratings.csv`
- `douban_*_ratings.csv`

## Current Validation Notes

Local validation completed for:

- `cargo check`
- `cargo test -p cinerecord-platforms --lib`
- `node --check web/static/rust-v2.js`
- `GET /api/v2/health`
- `GET /api/v2/library?limit=5&offset=0`
- Legacy CSV import into the Rust v2 library
- Scheduled task create / run / log flow
- Browser auth start route for Douban / IMDb

## Next Milestones

1. Finish TMDB end-to-end task and library flows.
2. Add Trakt OAuth and token persistence.
3. Migrate sync preview/execute core logic.
4. Add IMDb and Letterboxd implementations.
5. Tackle Douban last with a constrained PoC.
