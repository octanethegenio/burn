#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -d web/node_modules ]]; then
  (cd web && npm ci)
fi

(cd web && npm run build)
exec .venv/bin/python -m server.launcher
