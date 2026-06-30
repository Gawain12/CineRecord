#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="CineRecord"
VERSION="${CINERECORD_VERSION:-0.1.0}"
ARCH="$(uname -m)"
DIST_DIR="$ROOT_DIR/dist-rust"
APP_DIR="$DIST_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
BIN_PATH="$RESOURCES_DIR/cinerecord-server"
ICON_SOURCE="$ROOT_DIR/packaging/CineRecordIcon.svg"
ICONSET_DIR="$DIST_DIR/CineRecord.iconset"
ICON_RENDER_DIR="$DIST_DIR/icon-render-$ARCH"
ICON_PATH="$RESOURCES_DIR/CineRecord.icns"
ZIP_PATH="$DIST_DIR/$APP_NAME-macOS-$ARCH.zip"
DMG_PATH="$DIST_DIR/$APP_NAME-macOS-$ARCH.dmg"
DMG_STAGE="$DIST_DIR/dmg-stage-$ARCH"

rm -rf "$APP_DIR" "$DMG_STAGE" "$ICONSET_DIR" "$ICON_RENDER_DIR"
mkdir -p "$DIST_DIR" "$MACOS_DIR" "$RESOURCES_DIR"

cd "$ROOT_DIR"
cargo build --locked --release -p cinerecord-server
install -m 755 "$ROOT_DIR/target/release/cinerecord-server" "$BIN_PATH"

if [[ ! -f "$ICON_SOURCE" ]]; then
    echo "Missing icon source: $ICON_SOURCE" >&2
    exit 1
fi

mkdir -p "$ICONSET_DIR" "$ICON_RENDER_DIR"
qlmanage -t -s 1024 -o "$ICON_RENDER_DIR" "$ICON_SOURCE" >/dev/null
MASTER_ICON="$ICON_RENDER_DIR/$(basename "$ICON_SOURCE").png"
if [[ ! -f "$MASTER_ICON" ]]; then
    echo "Failed to render macOS icon from $ICON_SOURCE" >&2
    exit 1
fi

for SIZE in 16 32 128 256 512; do
    sips -z "$SIZE" "$SIZE" "$MASTER_ICON" --out "$ICONSET_DIR/icon_${SIZE}x${SIZE}.png" >/dev/null
    DOUBLE_SIZE=$((SIZE * 2))
    sips -z "$DOUBLE_SIZE" "$DOUBLE_SIZE" "$MASTER_ICON" --out "$ICONSET_DIR/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET_DIR" -o "$ICON_PATH"

cat > "$MACOS_DIR/$APP_NAME" <<'EOF'
#!/bin/zsh
set -euo pipefail

CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLED_BIN="$CONTENTS_DIR/Resources/cinerecord-server"
APP_HOME="$HOME/Library/Application Support/CineRecord"
RUNTIME_DIR="$APP_HOME/bin"
BIN="$RUNTIME_DIR/cinerecord-server"
LOG_DIR="$APP_HOME/logs/v2"
PID_FILE="$LOG_DIR/server.pid"
LAUNCH_LOG="$LOG_DIR/launcher.log"
SERVER_LOG="$LOG_DIR/server.stdout.log"
URL="http://127.0.0.1:18000"

mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

if [[ ! -x "$BIN" ]] || ! cmp -s "$BUNDLED_BIN" "$BIN"; then
    TEMP_BIN="$RUNTIME_DIR/cinerecord-server.new"
    cp "$BUNDLED_BIN" "$TEMP_BIN"
    chmod 755 "$TEMP_BIN"
    xattr -c "$TEMP_BIN" 2>/dev/null || true
    mv -f "$TEMP_BIN" "$BIN"
fi

if /usr/bin/curl --fail --silent "$URL/api/v2/health" >/dev/null 2>&1; then
    /usr/bin/open "$URL"
    exit 0
fi

if [[ -f "$PID_FILE" ]]; then
    EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        for _ in {1..40}; do
            if /usr/bin/curl --fail --silent "$URL/api/v2/health" >/dev/null 2>&1; then
                /usr/bin/open "$URL"
                exit 0
            fi
            sleep 0.25
        done
    fi
fi

export CINERECORD_HOME="$APP_HOME"
export CINERECORD_HOST="127.0.0.1"
export CINERECORD_PORT="18000"
export RUST_LOG="${RUST_LOG:-info,tower_http=warn}"

"$BIN" >> "$SERVER_LOG" 2>&1 < /dev/null &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') launched server pid $SERVER_PID" >> "$LAUNCH_LOG"
trap 'rm -f "$PID_FILE"' EXIT

for _ in {1..80}; do
    if /usr/bin/curl --fail --silent "$URL/api/v2/health" >/dev/null 2>&1; then
        /usr/bin/open "$URL"
        wait "$SERVER_PID"
        exit $?
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        break
    fi
    sleep 0.25
done

/usr/bin/osascript -e 'display alert "CineRecord 启动失败" message "请打开 ~/Library/Application Support/CineRecord/logs/v2/server.stdout.log 查看详情。" as critical' || true
/usr/bin/open -R "$SERVER_LOG" || true
wait "$SERVER_PID" 2>/dev/null || true
exit 1
EOF

chmod +x "$MACOS_DIR/$APP_NAME"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>zh_CN</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.cinerecord.app</string>
    <key>CFBundleIconFile</key>
    <string>CineRecord.icns</string>
    <key>CFBundleIconName</key>
    <string>CineRecord</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

plutil -lint "$CONTENTS_DIR/Info.plist" >/dev/null
test -s "$ICON_PATH"
touch "$APP_DIR"

if command -v xattr >/dev/null 2>&1; then
    xattr -cr "$APP_DIR"
fi

if command -v codesign >/dev/null 2>&1; then
    codesign --force --deep --sign - "$APP_DIR"
    codesign --verify --deep --strict "$APP_DIR"
fi
if command -v xattr >/dev/null 2>&1; then
    xattr -cr "$APP_DIR"
fi

rm -f "$ZIP_PATH" "$DMG_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ZIP_PATH"

mkdir -p "$DMG_STAGE"
cp -R "$APP_DIR" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG_PATH" >/dev/null
hdiutil verify "$DMG_PATH" >/dev/null
rm -rf "$DMG_STAGE"
rm -rf "$ICONSET_DIR" "$ICON_RENDER_DIR"

echo "APP_BUNDLE=$APP_DIR"
echo "ZIP_PATH=$ZIP_PATH"
echo "DMG_PATH=$DMG_PATH"
