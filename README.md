# Burn

Local dashboard for **Cursor API credit burn** — per model, current billing cycle. Reads your Cursor IDE session and pulls the same usage data as cursor.com/dashboard.

No CSV export. No cloud. Session stays on your machine.

## Requirements

- macOS (reads Cursor’s local login from `state.vscdb`)
- Python 3.10+
- Node 18+ (for the UI)
- Cursor app signed in

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web && npm install && cd ..
```

## Run

Terminal 1 — API:

```bash
source .venv/bin/activate
uvicorn server.main:app --reload --host 127.0.0.1 --port 8765
```

Terminal 2 — UI:

```bash
cd web && npm run dev
```

Open **http://localhost:5173**. It auto-syncs on first load.

## What you get

- Total `$` burned this billing cycle
- Per-model table (tokens + cost), sorted by spend
- Recent usage events
- **Sync now** refreshes from Cursor
- **Hide Auto-ish** filters obvious Auto/router model names

## Notes

- Uses unofficial Cursor dashboard endpoints (`get-aggregated-usage-events`, `get-filtered-usage-events`). They can change.
- Auth comes from `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` (`cursorAuth/accessToken`), with macOS keychain fallback.
- Cached snapshot lives in `data/burn.db` (gitignored).
