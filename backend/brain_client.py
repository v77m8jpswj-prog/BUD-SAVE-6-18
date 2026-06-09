"""Bud → 9 brain client.

Typed async functions to read 9's brain corpus (cases, stats, recent outcomes)
and POST briefings back. 9's brain lives at BRAIN_BASE (prod:
https://foreman.drunderhood.com). All calls require BUD_BRAIN_BEARER.

Confirmed surface (2026-06-08):
  GET  /api/brain/stats?shop_id=...
  GET  /api/brain/cases?shop_id=...&limit=&skip=
  GET  /api/brain/recent-outcomes?shop_id=...&limit=
  POST /api/brain/morning-briefing   body={shop_id, ...}

NOT exposed by 9 yet (asked in agent-mail):
  GET  /api/brain/search   — client-side filter via mirror until 9 ships
  POST /api/brain/cases    — write endpoint
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SHOP = "drunderhood-fortsmith"


def _cfg() -> tuple[str, str]:
    base = (os.environ.get("BRAIN_BASE") or "").rstrip("/")
    token = os.environ.get("BUD_BRAIN_BEARER") or ""
    if not base or not token:
        raise RuntimeError("BRAIN_BASE / BUD_BRAIN_BEARER not configured")
    return base, token


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def stats(shop_id: str = DEFAULT_SHOP) -> dict:
    base, token = _cfg()
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{base}/api/brain/stats", params={"shop_id": shop_id}, headers=_h(token))
    r.raise_for_status()
    return r.json()


async def recent_outcomes(shop_id: str = DEFAULT_SHOP, limit: int = 50) -> list[dict]:
    base, token = _cfg()
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{base}/api/brain/recent-outcomes",
            params={"shop_id": shop_id, "limit": limit},
            headers=_h(token),
        )
    r.raise_for_status()
    return r.json().get("events", []) or []


async def cases(shop_id: str = DEFAULT_SHOP, limit: int = 50, skip: int = 0) -> dict:
    base, token = _cfg()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            f"{base}/api/brain/cases",
            params={"shop_id": shop_id, "limit": limit, "skip": skip},
            headers=_h(token),
        )
    r.raise_for_status()
    return r.json()


async def operator_profile(
    shop_id: str = DEFAULT_SHOP,
    chat_limit: int = 200,
    voice_limit: int = 50,
    cases_limit: int = 20,
) -> dict:
    """Pull Doc's full identity payload (shop, operator_style, locked facts, recent
    chat/voice/cases). 9 ships this on PREVIEW first; PROD follows on Doc's next deploy."""
    base, token = _cfg()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            f"{base}/api/brain/operator-profile",
            params={
                "shop_id": shop_id,
                "chat_limit": chat_limit,
                "voice_limit": voice_limit,
                "cases_limit": cases_limit,
            },
            headers=_h(token),
        )
    r.raise_for_status()
    return r.json()


async def post_morning_briefing(
    shop_id: str,
    body_md: str,
    extras: Optional[dict] = None,
) -> dict:
    """POST today's briefing to 9 for ingest into the brain corpus."""
    base, token = _cfg()
    payload = {
        "shop_id": shop_id,
        "from_agent": "bud",
        "source": "bud",
        "author": "bud",
        "briefing_slug": f"bud-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "body_md": body_md,
    }
    if extras:
        payload.update(extras)
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{base}/api/brain/morning-briefing", json=payload, headers=_h(token))
    r.raise_for_status()
    return r.json()


async def ask(symptom: str, vehicle: Optional[dict] = None, shop_id: str = DEFAULT_SHOP) -> dict:
    """Query 9's brain for similar past cases. Returns 9's structured answer
    (top matches + suggested actions). `vehicle` fields must be strings —
    9's Pydantic validator rejects integer year."""
    base, token = _cfg()
    payload: dict = {"shop_id": shop_id, "symptom": symptom}
    if vehicle:
        # coerce year to str for 9's schema
        v = {k: (str(val) if k == "year" else val) for k, val in vehicle.items()}
        payload["vehicle"] = v
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{base}/api/brain/ask", json=payload, headers=_h(token))
    r.raise_for_status()
    return r.json()


async def mirror_sync(db, shop_id: str = DEFAULT_SHOP) -> dict:
    """Pull stats + recent-outcomes + cases into local mongo. Returns a small report."""
    report: dict = {"shop_id": shop_id, "mirrored_at": datetime.now(timezone.utc).isoformat()}
    try:
        s = await stats(shop_id)
        s["mirrored_at"] = report["mirrored_at"]
        await db["brain_mirror_stats"].update_one({"shop_id": shop_id}, {"$set": s}, upsert=True)
        report["stats"] = {"ok": True, "total_cases": s.get("total_cases")}
    except Exception as e:
        report["stats"] = {"ok": False, "error": str(e)}

    try:
        events = await recent_outcomes(shop_id, limit=200)
        if events:
            await db["brain_mirror_outcomes"].delete_many({"shop_id": shop_id})
            await db["brain_mirror_outcomes"].insert_many(events)
        report["recent_outcomes"] = {"ok": True, "count": len(events)}
    except Exception as e:
        report["recent_outcomes"] = {"ok": False, "error": str(e)}

    try:
        page = await cases(shop_id, limit=200, skip=0)
        cs = page.get("cases", []) if isinstance(page, dict) else []
        if cs:
            await db["brain_mirror_cases"].delete_many({"shop_id": shop_id})
            await db["brain_mirror_cases"].insert_many(cs)
        report["cases"] = {
            "ok": True,
            "mirrored": len(cs),
            "total_in_brain": page.get("total") if isinstance(page, dict) else None,
        }
    except Exception as e:
        report["cases"] = {"ok": False, "error": str(e)}

    return report
