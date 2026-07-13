# Burn

Burn is a private macOS dashboard for Cursor usage and cost by model. It reads the session from the Cursor app, calls Cursor's dashboard endpoints, and keeps its cache on your Mac.

## Install the beta

Burn does not use a setup wizard. On macOS, moving the `.app` bundle into the Applications folder installs it.

1. Download `Burn-0.1.0-beta.1-macOS-arm64.zip` from [GitHub Releases](https://github.com/octanethegenio/burn/releases/tag/v0.1.0-beta.1).
2. Double-click the ZIP to extract `Burn.app`.
3. Open Finder and drag `Burn.app` into **Applications**.
4. Make sure Cursor is open and signed in.
5. In Applications, Control-click `Burn.app` and choose **Open**.

### If macOS blocks Burn

This free beta is not Apple-notarized, so Gatekeeper may show **“Burn” Not Opened**. Do not choose **Move to Trash**.

1. Choose **Done** on the warning.
2. Open **System Settings → Privacy & Security**.
3. Scroll to **Security**, find the message about Burn, and choose **Open Anyway**.
4. Authenticate with Touch ID or your Mac password, then confirm **Open**.

This approval is normally required only once. Burn remains installed in Applications afterward.

The beta targets Apple Silicon and macOS 13 or newer. A future paid Developer ID–notarized build will open without this manual approval.

## Privacy and security

- The server binds to `127.0.0.1`; other devices cannot reach it.
- Burn reads the Cursor access token when syncing and never stores it.
- The local database contains the account email and summarized usage events. It lives at `~/Library/Application Support/Burn/burn.db` with owner-only permissions.
- Burn does not store raw Cursor API payloads, account subject IDs, or Cursor user IDs.
- The frontend contains no analytics, telemetry, remote fonts, or third-party network requests.
- A request header protects state-changing local endpoints from cross-site requests.

Burn uses unofficial Cursor dashboard endpoints. Cursor can change them without notice.

## Run from source

Requirements: macOS, Python 3.10+, Node 18+, and Cursor signed in.

```bash
./run.sh
```

Open `http://127.0.0.1:8765`. `run.sh` creates a Python environment, installs locked runtime dependencies, builds the UI, and starts the production server. For hot reload:

```bash
./dev.sh
```

## Verify

```bash
python3 -m unittest discover -s tests -v
cd web && npm ci && npm run check
```

## Build the macOS app

```bash
./scripts/build-macos.sh
```

For a public build, install a Developer ID Application certificate and store notarization credentials with `notarytool`, then set `BURN_CODESIGN_IDENTITY` and `BURN_NOTARY_PROFILE`. Without both values the script produces a local ad-hoc build and warns that Gatekeeper will reject public downloads.

The script creates the app and checksum in `release/`. It needs Xcode command-line tools, Python 3, Node, and network access for build dependencies.
