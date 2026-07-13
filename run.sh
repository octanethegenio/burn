#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -d web/node_modules ]]; then
  (cd web && npm install)
fi

.venv/bin/uvicorn server.main:app --reload --host 127.0.0.1 --port 8765 &
API_PID=$!
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT

cd web
npm run dev -- --host 127.0.0.1
