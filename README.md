# Burn

Burn is a private local dashboard for Cursor usage and cost by model. It opens in your default browser, reads the session from the Cursor desktop app, and keeps its cache on your computer.

## Run the beta

1. Download the archive for your operating system from [GitHub Releases](https://github.com/octanethegenio/burn/releases).
2. Extract it.
3. On macOS, move `Burn.app` to Applications and open it. On Windows, double-click `Burn.exe`.
4. Burn starts a loopback-only local service and opens `http://127.0.0.1:8765` in your default browser.

Burn has no separate application window. The launcher runs quietly in the background, and the browser is the entire interface. Keep Cursor installed and signed in. Burn exits automatically after no browser tab has connected for ten minutes. Opening the launcher again reopens the dashboard.

The unsigned beta may trigger macOS Gatekeeper or Windows SmartScreen. Verify its SHA-256 file first, then use the operating system's manual approval option only if you trust this repository and downloaded the file from its Releases page.

## Privacy and security

- The service binds to `127.0.0.1`; other devices cannot reach it.
- Burn reads the Cursor access token only during sync and never stores it.
- The local database contains the account email and summarized usage events.
- Burn does not store raw Cursor API payloads, account subject IDs, or Cursor user IDs.
- The frontend contains no analytics, telemetry, remote fonts, or third-party browser requests.
- Host validation, browser security headers, and a custom request header protect local endpoints.

Local cache locations:

- macOS: `~/Library/Application Support/Burn/burn.db`
- Windows: `%LOCALAPPDATA%\Burn\burn.db`
- Linux: `$XDG_DATA_HOME/burn/burn.db`, or `~/.local/share/burn/burn.db`

Burn uses unofficial Cursor dashboard endpoints. Cursor can change them without notice.

## Run from source

Requirements: Python 3.10+, Node.js 18+, and Cursor signed in.

macOS or Linux:

```bash
./run.sh
```

Windows PowerShell:

```powershell
.\run.ps1
```

The production UI builds locally, the service starts on loopback, and your default browser opens automatically. Press `Ctrl+C` in the launching terminal to stop it immediately.

For frontend development, run `./dev.sh` and open `http://127.0.0.1:5173`.

## Verify

```bash
python3 -m unittest discover -s tests -v
cd web && npm ci && npm run check
```

## Package

Install build requirements, then package for the current operating system:

```bash
python3 -m pip install -r requirements.txt -r requirements-build.txt
python3 scripts/package.py
```

The executable, ZIP, and SHA-256 file are written to `release/`. GitHub Actions runs the same tests and packaging process on macOS ARM/Intel, Windows x64, and Linux x64.
