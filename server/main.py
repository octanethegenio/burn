"""Burn — local Cursor API credit dashboard."""

from __future__ import annotations

import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import cursor_client, store
from .auth import load_session

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIST = ROOT / "web" / "dist"
SYNC_LOCK = threading.Lock()
_BROWSER_ACTIVITY_LOCK = threading.Lock()
_LAST_BROWSER_ACTIVITY = time.monotonic()


def note_browser_activity() -> None:
    global _LAST_BROWSER_ACTIVITY
    with _BROWSER_ACTIVITY_LOCK:
        _LAST_BROWSER_ACTIVITY = time.monotonic()


def seconds_since_browser_activity() -> float:
    with _BROWSER_ACTIVITY_LOCK:
        return time.monotonic() - _LAST_BROWSER_ACTIVITY

# Models that look like Auto / router buckets — hidden when api_only=true
AUTO_MODEL_RE = re.compile(
    r"(^|-)(auto|default|composer-1)(-|$)|agent.?router|cursor-small",
    re.I,
)


def _to_ms(value: Any) -> str:
    if value is None:
        raise ValueError("missing timestamp")
    if isinstance(value, (int, float)):
        return str(int(value))
    s = str(value)
    if s.isdigit():
        return s
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return str(int(dt.timestamp() * 1000))


_EFFORTS = ("xxhigh", "xhigh", "high", "medium", "low", "max")
_EFFORT_ALIASES = {"high", "xhigh", "xxhigh"}


def _split_model(name: str) -> tuple[str, str | None, bool]:
    """stem, effort, has_cursor_prefix — e.g. cursor-grok-4.5-high → (grok-4.5, high, True)."""
    n = name.lower().strip()
    has_cursor = n.startswith("cursor-")
    if has_cursor:
        n = n[len("cursor-") :]
    for prefix in ("api-", "agent-"):
        if n.startswith(prefix):
            n = n[len(prefix) :]
    for effort in _EFFORTS:
        suf = f"-{effort}"
        if n.endswith(suf):
            return n[: -len(suf)], effort, has_cursor
    return n, None, has_cursor


def _match_event_to_agg(event_model: str, agg_names: list[str]) -> str | None:
    """Map event model ids onto aggregation modelIntent rows for request counting."""
    if event_model in agg_names:
        return event_model

    e_stem, e_effort, e_cursor = _split_model(event_model)
    scored: list[tuple[int, str]] = []
    for agg in agg_names:
        a_stem, a_effort, a_cursor = _split_model(agg)
        if e_stem != a_stem:
            continue
        score = 0
        # Prefer same cursor-/non-cursor family (events often omit cursor-; aggs use xhigh)
        if e_cursor == a_cursor:
            score += 25
        if e_effort == a_effort:
            score += 50
        elif (
            e_effort
            and a_effort
            and e_effort in _EFFORT_ALIASES
            and a_effort in _EFFORT_ALIASES
        ):
            score += 45  # high ↔ xhigh (UI vs aggregate naming)
        elif e_effort is None and a_effort is None:
            score += 50
        else:
            continue
        scored.append((score, agg))

    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][1]


def _intish(v: Any) -> int:
    if v is None:
        return 0
    return int(float(v))


def _event_cost_cents(ev: dict[str, Any]) -> float:
    if ev.get("chargedCents") is not None:
        return float(ev["chargedCents"])
    tu = ev.get("tokenUsage") or {}
    if tu.get("totalCents") is not None:
        return float(tu["totalCents"])
    return 0.0


def _event_id(ev: dict[str, Any], idx: int) -> str:
    value = f"{ev.get('timestamp')}:{ev.get('model')}:{_event_cost_cents(ev):.6f}:{idx}"
    return sha256(value.encode()).hexdigest()[:32]


def sync_now() -> dict[str, Any]:
    session = load_session()
    me = cursor_client.auth_me(session)
    summary = cursor_client.usage_summary(session)
    period = cursor_client.current_period_usage(session)

    start_ms = _to_ms(summary.get("billingCycleStart") or period.get("billingCycleStart"))
    end_ms = _to_ms(summary.get("billingCycleEnd") or period.get("billingCycleEnd"))
    user_id = int(me["id"])

    agg = cursor_client.aggregated_usage(
        session, user_id=user_id, start_ms=start_ms, end_ms=end_ms
    )
    events = cursor_client.all_filtered_events(
        session, user_id=user_id, start_ms=start_ms, end_ms=end_ms
    )

    # Request counts from events (fuzzy name match to aggregation intents)
    counts: dict[str, int] = {}
    for ev in events:
        m = ev.get("model") or "unknown"
        counts[m] = counts.get(m, 0) + 1

    by_model: dict[str, dict[str, Any]] = {}
    for row in agg.get("aggregations") or []:
        model = row.get("modelIntent") or row.get("model") or "unknown"
        cur = by_model.get(model)
        if cur is None:
            by_model[model] = {
                "model": model,
                "input_tokens": _intish(row.get("inputTokens")),
                "output_tokens": _intish(row.get("outputTokens")),
                "cache_read_tokens": _intish(row.get("cacheReadTokens")),
                "cache_write_tokens": _intish(row.get("cacheWriteTokens")),
                "cost_cents": float(row.get("totalCents") or 0),
                "tier": row.get("tier"),
                "request_count": 0,
            }
        else:
            cur["input_tokens"] += _intish(row.get("inputTokens"))
            cur["output_tokens"] += _intish(row.get("outputTokens"))
            cur["cache_read_tokens"] += _intish(row.get("cacheReadTokens"))
            cur["cache_write_tokens"] += _intish(row.get("cacheWriteTokens"))
            cur["cost_cents"] += float(row.get("totalCents") or 0)

    # Attach request counts without inventing extra cost rows
    agg_names = list(by_model.keys())
    for event_model, n in counts.items():
        matched = _match_event_to_agg(event_model, agg_names)
        if matched:
            by_model[matched]["request_count"] += n

    model_rows = list(by_model.values())
    official_total = float(agg.get("totalCostCents") or sum(r["cost_cents"] for r in model_rows))

    event_rows = []
    for idx, ev in enumerate(events):
        tu = ev.get("tokenUsage") or {}
        event_rows.append(
            {
                "id": _event_id(ev, idx),
                "ts_ms": int(ev.get("timestamp") or 0),
                "model": ev.get("model") or "unknown",
                "kind": ev.get("kind"),
                "cost_cents": _event_cost_cents(ev),
                "input_tokens": _intish(tu.get("inputTokens")),
                "output_tokens": _intish(tu.get("outputTokens")),
                "cache_read_tokens": _intish(tu.get("cacheReadTokens")),
            }
        )
    event_rows.sort(key=lambda row: row["ts_ms"], reverse=True)
    event_rows = event_rows[:5000]

    plan_usage = period.get("planUsage") or {}

    store.replace_snapshot(
        model_rows,
        event_rows,
        account={
            "email": me.get("email") or session.email,
        },
        period={
            "start": summary.get("billingCycleStart"),
            "end": summary.get("billingCycleEnd"),
            "membership": summary.get("membershipType"),
            "plan_usage": {"apiPercentUsed": plan_usage.get("apiPercentUsed")},
            "display_message": period.get("displayMessage")
            or summary.get("namedModelSelectedDisplayMessage"),
            "total_cost_cents": official_total,
        },
    )

    return {
        "models": len(model_rows),
        "events": len(event_rows),
        "total_cost_cents": official_total,
    }


def _is_auto_model(name: str) -> bool:
    return bool(AUTO_MODEL_RE.search(name))


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init_db()
    yield


app = FastAPI(title="Burn", version="0.1.0-beta.6", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    host = request.headers.get("host", "").partition(":")[0].lower()
    if host not in {"127.0.0.1", "localhost"}:
        return PlainTextResponse("Invalid host", status_code=400)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-Burn-Request") != "1":
            return PlainTextResponse("Forbidden", status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; img-src 'self' data:; "
        "script-src 'self'; connect-src 'self'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "burn"}


@app.post("/api/heartbeat", status_code=204)
def heartbeat() -> None:
    note_browser_activity()


@app.get("/api/status")
def status() -> dict[str, Any]:
    try:
        session = load_session()
        auth_ok = True
        auth_error = None
        preview = {
            "email": session.email,
        }
    except Exception as e:  # noqa: BLE001
        auth_ok = False
        auth_error = "Cursor session unavailable."
        preview = None

    return {
        "auth_ok": auth_ok,
        "auth_error": auth_error,
        "session": preview,
        "account": store.get_meta("account"),
        "period": store.get_meta("period"),
        "last_synced_at": store.get_meta("last_synced_at"),
        "has_data": bool(store.list_models()),
    }


@app.post("/api/sync")
def sync() -> dict[str, Any]:
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A sync is already running.")
    try:
        result = sync_now()
    except cursor_client.CursorAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Sync failed. Check Cursor sign-in and retry.") from e
    finally:
        SYNC_LOCK.release()
    return {"ok": True, **result, "last_synced_at": store.get_meta("last_synced_at")}


@app.get("/api/summary")
def summary(api_only: bool = True) -> dict[str, Any]:
    models = store.list_models()
    if api_only:
        models = [m for m in models if not _is_auto_model(m["model"])]

    period = store.get_meta("period") or {}
    # Prefer Cursor's official cycle total when showing all aggregated models
    if api_only:
        total = sum(float(m["cost_cents"]) for m in models)
    else:
        total = float(period.get("total_cost_cents") or sum(float(m["cost_cents"]) for m in models))

    return {
        "account": store.get_meta("account"),
        "period": period,
        "last_synced_at": store.get_meta("last_synced_at"),
        "api_only": api_only,
        "total_cost_cents": total,
        "total_cost_usd": total / 100.0,
        "models": [
            {
                **m,
                "cost_usd": float(m["cost_cents"]) / 100.0,
                "is_auto": _is_auto_model(m["model"]),
            }
            for m in models
        ],
        "events": store.list_events(),
    }


# Production: serve Vite build
if WEB_DIST.exists():
    assets = WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = (WEB_DIST / full_path).resolve()
        if full_path and candidate.is_relative_to(WEB_DIST.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
