#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="0.1.0-beta.1"
BUILD_DIR="$ROOT/build/macos"
APP_DIR="$ROOT/release/Burn.app"
ARTIFACT="$ROOT/release/Burn-${VERSION}-macOS-arm64.zip"

rm -rf "$BUILD_DIR" "$APP_DIR" "$ARTIFACT"
mkdir -p "$BUILD_DIR" "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

(cd web && npm ci && npm run check)

python3 -m venv "$BUILD_DIR/venv"
"$BUILD_DIR/venv/bin/pip" install --disable-pip-version-check \
  -r requirements.txt -r requirements-build.txt
"$BUILD_DIR/venv/bin/pyinstaller" \
  --clean \
  --noconfirm \
  --onefile \
  --name burn-server \
  --paths "$ROOT" \
  --add-data "$ROOT/web/dist:web/dist" \
  --distpath "$BUILD_DIR/dist" \
  --workpath "$BUILD_DIR/work" \
  --specpath "$BUILD_DIR" \
  server/launcher.py

swiftc mac/BurnApp.swift \
  -target arm64-apple-macos13.0 \
  -module-cache-path "$BUILD_DIR/swift-module-cache" \
  -framework Cocoa \
  -framework WebKit \
  -o "$APP_DIR/Contents/MacOS/Burn"
cp mac/Info.plist "$APP_DIR/Contents/Info.plist"
cp "$BUILD_DIR/dist/burn-server" "$APP_DIR/Contents/Resources/burn-server"

codesign --force --deep --sign - "$APP_DIR"
ditto -c -k --norsrc --keepParent "$APP_DIR" "$ARTIFACT"
shasum -a 256 "$ARTIFACT" > "$ARTIFACT.sha256"

echo "$ARTIFACT"
