"""Resolve Cursor session from local IDE storage."""

from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Session:
    email: str | None
    user_sub: str
    access_token: str
    cookie_value: str
    source: str

    @property
    def cookie_header(self) -> str:
        # Cursor expects sub%3A%3Ajwt (URL-encoded ::)
        return f"WorkosCursorSessionToken={self.user_sub}%3A%3A{self.access_token}"


def _state_db_path() -> Path:
    return (
        Path.home()
        / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    )


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT")
    pad = "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(parts[1] + pad))


def _normalize_sub(sub: str) -> str:
    # google-oauth2|user_01… → user_01…
    if "|" in sub and "user_" in sub:
        return sub.split("|", 1)[1]
    return sub


def _read_sqlite_auth(db_path: Path) -> tuple[str, str | None]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        token_row = con.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("cursorAuth/accessToken",),
        ).fetchone()
        email_row = con.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("cursorAuth/cachedEmail",),
        ).fetchone()
    finally:
        con.close()
    if not token_row or not token_row[0]:
        raise FileNotFoundError("cursorAuth/accessToken missing in Cursor state DB")
    return token_row[0], email_row[0] if email_row else None


def _read_keychain_token() -> str | None:
    import subprocess

    try:
        out = subprocess.check_output(
            ["security", "find-generic-password", "-s", "cursor-access-token", "-w"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_session() -> Session:
    db = _state_db_path()
    errors: list[str] = []

    if db.exists():
        try:
            token, email = _read_sqlite_auth(db)
            payload = _decode_jwt_payload(token)
            sub = _normalize_sub(str(payload["sub"]))
            return Session(
                email=email,
                user_sub=sub,
                access_token=token,
                cookie_value=f"{sub}::{token}",
                source="cursor-sqlite",
            )
        except Exception as e:  # noqa: BLE001 — surface to caller as fallback chain
            errors.append(f"sqlite: {e}")

    token = _read_keychain_token()
    if token:
        payload = _decode_jwt_payload(token)
        sub = _normalize_sub(str(payload["sub"]))
        return Session(
            email=None,
            user_sub=sub,
            access_token=token,
            cookie_value=f"{sub}::{token}",
            source="keychain",
        )

    raise RuntimeError(
        "Could not find a Cursor session. Sign in to the Cursor app, then retry. "
        + (" ".join(errors) if errors else "")
    )
