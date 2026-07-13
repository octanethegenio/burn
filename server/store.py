"""Private, local SQLite cache for synced usage snapshots."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LEGACY_DB_PATH = ROOT / "data" / "burn.db"


def _data_dir(
    *, platform: str | None = None, home: Path | None = None, env: dict[str, str] | None = None
) -> Path:
    platform = platform or sys.platform
    home = home or Path.home()
    env = os.environ if env is None else env
    override = env.get("BURN_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Burn"
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Burn"
    return Path(env.get("XDG_DATA_HOME", home / ".local" / "share")) / "burn"


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "burn.db"
MIGRATE_LEGACY = "BURN_DATA_DIR" not in os.environ

_EVENT_COLUMNS = """
  id TEXT PRIMARY KEY,
  ts_ms INTEGER NOT NULL,
  model TEXT NOT NULL,
  kind TEXT,
  cost_cents REAL NOT NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cache_read_tokens INTEGER NOT NULL
"""


def _prepare_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        DATA_DIR.chmod(0o700)
    except OSError:
        pass

    if MIGRATE_LEGACY and DB_PATH != LEGACY_DB_PATH and not DB_PATH.exists() and LEGACY_DB_PATH.exists():
        source = sqlite3.connect(f"file:{LEGACY_DB_PATH}?mode=ro", uri=True)
        destination = sqlite3.connect(DB_PATH)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()


def connect() -> sqlite3.Connection:
    _prepare_data_dir()
    con = sqlite3.connect(DB_PATH, timeout=10)
    try:
        DB_PATH.chmod(0o600)
    except OSError:
        pass
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 10000")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def init_db() -> None:
    with connect() as con:
        con.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS models (
              model TEXT PRIMARY KEY,
              input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL,
              cache_read_tokens INTEGER NOT NULL,
              cache_write_tokens INTEGER NOT NULL,
              cost_cents REAL NOT NULL,
              tier INTEGER,
              request_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events ({_EVENT_COLUMNS});
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_ms DESC);
            CREATE INDEX IF NOT EXISTS idx_events_model ON events(model);
            """
        )

        event_columns = {
            row["name"] for row in con.execute("PRAGMA table_info(events)").fetchall()
        }
        expected_event_columns = {
            "id",
            "ts_ms",
            "model",
            "kind",
            "cost_cents",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
        }
        safe_previous_columns = expected_event_columns - {"cache_read_tokens"}
        if event_columns == safe_previous_columns:
            con.execute(
                "ALTER TABLE events ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0"
            )
        elif event_columns != expected_event_columns:
            # Old rows can contain account identifiers in raw_json and id.
            con.executescript(
                f"""
                DROP TABLE events;
                CREATE TABLE events ({_EVENT_COLUMNS});
                CREATE INDEX idx_events_ts ON events(ts_ms DESC);
                CREATE INDEX idx_events_model ON events(model);
                """
            )

        account = _get_meta(con, "account")
        if isinstance(account, dict):
            safe_account = {
                key: account.get(key)
                for key in ("email",)
                if account.get(key) is not None
            }
            _set_meta(con, "account", safe_account)


def _set_meta(con: sqlite3.Connection, key: str, value: Any) -> None:
    con.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, separators=(",", ":"))),
    )


def _get_meta(con: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return default if not row else json.loads(row["value"])


def get_meta(key: str, default: Any = None) -> Any:
    with connect() as con:
        return _get_meta(con, key, default)


def replace_snapshot(
    models: list[dict[str, Any]],
    events: list[dict[str, Any]],
    account: dict[str, Any],
    period: dict[str, Any],
) -> float:
    """Replace a full sync in one transaction so readers never see mixed data."""
    synced_at = time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM models")
        con.executemany(
            """
            INSERT INTO models(
              model, input_tokens, output_tokens, cache_read_tokens,
              cache_write_tokens, cost_cents, tier, request_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["model"],
                    row["input_tokens"],
                    row["output_tokens"],
                    row["cache_read_tokens"],
                    row["cache_write_tokens"],
                    row["cost_cents"],
                    row.get("tier"),
                    row.get("request_count", 0),
                )
                for row in models
            ],
        )
        con.execute("DELETE FROM events")
        con.executemany(
            """
            INSERT INTO events(
              id, ts_ms, model, kind, cost_cents, input_tokens, output_tokens,
              cache_read_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["ts_ms"],
                    row["model"],
                    row.get("kind"),
                    row["cost_cents"],
                    row["input_tokens"],
                    row["output_tokens"],
                    row.get("cache_read_tokens", 0),
                )
                for row in events
            ],
        )
        _set_meta(con, "account", account)
        _set_meta(con, "period", period)
        _set_meta(con, "last_synced_at", synced_at)
    return synced_at


def list_models() -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute("SELECT * FROM models ORDER BY cost_cents DESC").fetchall()
    return [dict(row) for row in rows]


def list_events(limit: int = 2000) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 5000))
    with connect() as con:
        rows = con.execute(
            "SELECT id, ts_ms, model, kind, cost_cents, input_tokens, output_tokens, "
            "cache_read_tokens "
            "FROM events ORDER BY ts_ms DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def count_events() -> int:
    with connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM events").fetchone()
    return int(row["n"])
