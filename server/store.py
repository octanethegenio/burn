"""Local SQLite cache for synced usage snapshots."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "burn.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
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
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY,
              ts_ms INTEGER NOT NULL,
              model TEXT NOT NULL,
              kind TEXT,
              cost_cents REAL NOT NULL,
              input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL,
              cache_read_tokens INTEGER NOT NULL,
              cache_write_tokens INTEGER NOT NULL,
              is_chargeable INTEGER,
              raw_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_ms);
            CREATE INDEX IF NOT EXISTS idx_events_model ON events(model);
            """
        )


def set_meta(key: str, value: Any) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def get_meta(key: str, default: Any = None) -> Any:
    with connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return json.loads(row["value"])


def replace_models(rows: list[dict[str, Any]]) -> None:
    with connect() as con:
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
                    r["model"],
                    r["input_tokens"],
                    r["output_tokens"],
                    r["cache_read_tokens"],
                    r["cache_write_tokens"],
                    r["cost_cents"],
                    r.get("tier"),
                    r.get("request_count", 0),
                )
                for r in rows
            ],
        )


def replace_events(rows: list[dict[str, Any]]) -> None:
    with connect() as con:
        con.execute("DELETE FROM events")
        con.executemany(
            """
            INSERT INTO events(
              id, ts_ms, model, kind, cost_cents, input_tokens, output_tokens,
              cache_read_tokens, cache_write_tokens, is_chargeable, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r["id"],
                    r["ts_ms"],
                    r["model"],
                    r.get("kind"),
                    r["cost_cents"],
                    r["input_tokens"],
                    r["output_tokens"],
                    r["cache_read_tokens"],
                    r["cache_write_tokens"],
                    1 if r.get("is_chargeable") else 0,
                    r["raw_json"],
                )
                for r in rows
            ],
        )


def list_models() -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM models ORDER BY cost_cents DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_events(limit: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        if limit is None:
            rows = con.execute(
                "SELECT id, ts_ms, model, kind, cost_cents, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, is_chargeable "
                "FROM events ORDER BY ts_ms DESC"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, ts_ms, model, kind, cost_cents, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, is_chargeable "
                "FROM events ORDER BY ts_ms DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def mark_synced() -> None:
    set_meta("last_synced_at", time.time())
