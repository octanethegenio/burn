"""Unofficial Cursor dashboard API client (session cookie auth)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .auth import Session

BASE = "https://cursor.com"


class CursorAPIError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"Cursor API {status}: {body[:300]}")


def _request(
    session: Session,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Cookie": session.cookie_header,
        "Accept": "application/json",
    }
    if method == "POST":
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://cursor.com"
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raise CursorAPIError(e.code, e.read().decode(errors="replace")) from e


def auth_me(session: Session) -> dict[str, Any]:
    return _request(session, "GET", "/api/auth/me")


def usage_summary(session: Session) -> dict[str, Any]:
    return _request(session, "GET", "/api/usage-summary")


def current_period_usage(session: Session) -> dict[str, Any]:
    return _request(session, "POST", "/api/dashboard/get-current-period-usage", {})


def aggregated_usage(
    session: Session,
    *,
    user_id: int,
    start_ms: str,
    end_ms: str,
) -> dict[str, Any]:
    return _request(
        session,
        "POST",
        "/api/dashboard/get-aggregated-usage-events",
        {
            "teamId": 0,
            "userId": user_id,
            "startDate": start_ms,
            "endDate": end_ms,
        },
    )


def filtered_usage_events(
    session: Session,
    *,
    user_id: int,
    start_ms: str,
    end_ms: str,
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    return _request(
        session,
        "POST",
        "/api/dashboard/get-filtered-usage-events",
        {
            "teamId": 0,
            "userId": user_id,
            "startDate": start_ms,
            "endDate": end_ms,
            "page": page,
            "pageSize": page_size,
        },
    )


def all_filtered_events(
    session: Session,
    *,
    user_id: int,
    start_ms: str,
    end_ms: str,
    page_size: int = 500,
) -> list[dict[str, Any]]:
    page = 1
    events: list[dict[str, Any]] = []
    total = None
    while True:
        data = filtered_usage_events(
            session,
            user_id=user_id,
            start_ms=start_ms,
            end_ms=end_ms,
            page=page,
            page_size=page_size,
        )
        batch = data.get("usageEventsDisplay") or []
        if total is None:
            total = int(data.get("totalUsageEventsCount") or 0)
        events.extend(batch)
        if not batch or len(events) >= total:
            break
        page += 1
        if page > 200:
            break
    return events
