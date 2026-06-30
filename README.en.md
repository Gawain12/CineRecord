# CineRecord

CineRecord is a local-first movie library and cross-platform synchronization tool. The backend is written in Rust, and the same binary serves the browser UI. Python, Node.js, and an external database service are not required.

Supported sources include Douban, IMDb, Trakt, TMDB, and Letterboxd CSV imports.

## Run from source

```bash
cargo run -p cinerecord-server
```

Open [http://127.0.0.1:18000](http://127.0.0.1:18000).

Installed builds store user data in:

- macOS: `~/Library/Application Support/CineRecord`
- Windows: `%APPDATA%\CineRecord`
- Linux: `$XDG_DATA_HOME/cinerecord` or `~/.local/share/cinerecord`

Set `CINERECORD_HOME` to override the location.

## Docker

```bash
docker compose up -d --build
```

The service listens on port `18000`, with persistent data in `./cinerecord-data`.

## Packaging

```bash
./scripts/package_rust_macos.sh
```

On Windows:

```powershell
.\scripts\package_rust_windows.ps1
```

The Windows script creates a standalone `CineRecord-Windows-x64.exe` with an
application icon. Double-clicking it starts the background service and opens
the browser UI.

GitHub Actions automatically tests `dev`, `main`, and version tags, builds and
smoke-tests native macOS ARM, macOS Intel, and Windows x64 packages, and
publishes the Linux Docker image to `ghcr.io/gawain12/cinerecord`.

## Synchronization safety

- Preview is generated from the local cache for responsiveness.
- Both platforms are refreshed before an actual write.
- Unrated source entries do not overwrite existing target ratings.
- Candidates can be selected individually before execution.

The legacy Python implementation remains temporarily for comparison and migration utilities. Production builds use Rust only.

## License

MIT
