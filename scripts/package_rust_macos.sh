#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="CineRecordRust"
DISPLAY_NAME="CineRecordRust"
BUILD_DIR="$ROOT_DIR/build/rust-macos"
DIST_DIR="$ROOT_DIR/dist-rust"
APP_DIR="$DIST_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
APP_ROOT_DIR="$RESOURCES_DIR/app"
BIN_DIR="$APP_ROOT_DIR/bin"
ZIP_PATH="$DIST_DIR/$APP_NAME-mac-arm64.zip"

rm -rf "$BUILD_DIR" "$APP_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$MACOS_DIR" "$BIN_DIR" "$APP_ROOT_DIR/web" "$APP_ROOT_DIR/config/v2" "$APP_ROOT_DIR/data/v2" "$APP_ROOT_DIR/logs/v2"

cd "$ROOT_DIR"
cargo build --release -p cinerecord-server

cp "$ROOT_DIR/target/release/cinerecord-server" "$BIN_DIR/cinerecord-server"
cp -R "$ROOT_DIR/web/static" "$APP_ROOT_DIR/web/static"

cat > "$MACOS_DIR/$APP_NAME" <<'EOF'
#!/bin/zsh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="$APP_DIR/Resources/app"
BIN="$APP_ROOT/bin/cinerecord-server"
LOG_DIR="$APP_ROOT/logs/v2"
PID_FILE="$LOG_DIR/server.pid"
LAUNCH_LOG="$LOG_DIR/launcher.log"
SERVER_LOG="$LOG_DIR/server.stdout.log"

mkdir -p "$LOG_DIR" "$APP_ROOT/config/v2" "$APP_ROOT/data/v2"

if [[ -f "$PID_FILE" ]]; then
    EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${EXISTING_PID}" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        open "http://127.0.0.1:18000"
        exit 0
    fi
fi

cd "$APP_ROOT"
"$BIN" >> "$SERVER_LOG" 2>&1 < /dev/null &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') launched rust server pid $SERVER_PID" >> "$LAUNCH_LOG"
trap 'rm -f "$PID_FILE"' EXIT
(sleep 2; open "http://127.0.0.1:18000") >/dev/null 2>&1 &
wait "$SERVER_PID"
EOF

chmod +x "$MACOS_DIR/$APP_NAME" "$BIN_DIR/cinerecord-server"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>zh_CN</string>
    <key>CFBundleDisplayName</key>
    <string>$DISPLAY_NAME</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.cinerecord.rust</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$DISPLAY_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ZIP_PATH"

echo "APP_BUNDLE=$APP_DIR"
echo "ZIP_PATH=$ZIP_PATH"
