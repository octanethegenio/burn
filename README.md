# Burn

Burn is a private macOS dashboard for Cursor usage and cost by model. It reads the session from the Cursor app, calls Cursor's dashboard endpoints, and keeps its cache on your Mac.

## Install the beta

1. Download `Burn-0.1.0-beta.1-macOS-arm64.zip` from GitHub Releases.
2. Unzip it and move `Burn.app` to Applications.
3. Open Burn while signed in to Cursor.

The beta build targets Apple Silicon and macOS 13 or newer. It uses ad-hoc signing because this release is not notarized. macOS may require you to right-click Burn and choose **Open** the first time.

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

The script creates the app and checksum in `release/`. It needs Xcode command-line tools, Python 3, Node, and network access for build dependencies.
