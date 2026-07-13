#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="0.1.0-beta.2"
BUILD_DIR="$ROOT/build/macos"
APP_DIR="$ROOT/release/Burn.app"
ARTIFACT="$ROOT/release/Burn-${VERSION}-macOS-arm64.zip"
CODESIGN_IDENTITY="${BURN_CODESIGN_IDENTITY:--}"
NOTARY_PROFILE="${BURN_NOTARY_PROFILE:-}"

rm -rf "$BUILD_DIR" "$APP_DIR" "$ARTIFACT" "$ARTIFACT.sha256"
mkdir -p "$BUILD_DIR" "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

(cd web && npm ci && npm run check)

python3 -m venv "$BUILD_DIR/venv"
"$BUILD_DIR/venv/bin/pip" install --disable-pip-version-check \
  -r requirements.txt -r requirements-build.txt
pyinstaller_args=(
  --clean
  --noconfirm
  --onefile
  --name burn-server
  --paths "$ROOT"
  --add-data "$ROOT/web/dist:web/dist"
  --distpath "$BUILD_DIR/dist"
  --workpath "$BUILD_DIR/work"
  --specpath "$BUILD_DIR"
)
if [[ "$CODESIGN_IDENTITY" != "-" ]]; then
  pyinstaller_args+=(--codesign-identity "$CODESIGN_IDENTITY")
fi
"$BUILD_DIR/venv/bin/pyinstaller" \
  "${pyinstaller_args[@]}" \
  server/launcher.py

swiftc mac/BurnApp.swift \
  -target arm64-apple-macos13.0 \
  -module-cache-path "$BUILD_DIR/swift-module-cache" \
  -framework Cocoa \
  -framework WebKit \
  -o "$APP_DIR/Contents/MacOS/Burn"
cp mac/Info.plist "$APP_DIR/Contents/Info.plist"
cp "$BUILD_DIR/dist/burn-server" "$APP_DIR/Contents/Resources/burn-server"

if [[ "$CODESIGN_IDENTITY" == "-" ]]; then
  codesign --force --sign - "$APP_DIR/Contents/Resources/burn-server"
  codesign --force --sign - "$APP_DIR/Contents/MacOS/Burn"
  codesign --force --sign - "$APP_DIR"
  echo "warning: built with ad-hoc signing; public downloads will trigger Gatekeeper" >&2
else
  codesign --force --options runtime --timestamp --sign "$CODESIGN_IDENTITY" \
    "$APP_DIR/Contents/Resources/burn-server"
  codesign --force --options runtime --timestamp --sign "$CODESIGN_IDENTITY" \
    "$APP_DIR/Contents/MacOS/Burn"
  codesign --force --options runtime --timestamp --sign "$CODESIGN_IDENTITY" "$APP_DIR"
fi

codesign --verify --deep --strict --verbose=2 "$APP_DIR"
ditto -c -k --norsrc --keepParent "$APP_DIR" "$ARTIFACT"

if [[ -n "$NOTARY_PROFILE" ]]; then
  if [[ "$CODESIGN_IDENTITY" == "-" ]]; then
    echo "BURN_NOTARY_PROFILE requires BURN_CODESIGN_IDENTITY" >&2
    exit 1
  fi
  xcrun notarytool submit "$ARTIFACT" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP_DIR"
  xcrun stapler validate "$APP_DIR"
  rm -f "$ARTIFACT"
  ditto -c -k --norsrc --keepParent "$APP_DIR" "$ARTIFACT"
  spctl --assess --type execute --verbose=2 "$APP_DIR"
elif [[ "$CODESIGN_IDENTITY" != "-" ]]; then
  echo "warning: Developer ID signed but not notarized; set BURN_NOTARY_PROFILE" >&2
fi

shasum -a 256 "$ARTIFACT" > "$ARTIFACT.sha256"

echo "$ARTIFACT"
