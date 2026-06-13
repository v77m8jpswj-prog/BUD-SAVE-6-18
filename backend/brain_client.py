"""Bud → 9 brain client (locked-down peer API).

Only two endpoints exposed by 9 as of the R-lockdown:
  GET /api/brain/peer/lookup?q=<query>
  GET /api/brain/peer/open-work

All other /api/brain/* endpoints are 401 and off-limits. Do not call them.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

DEFAULT_SHOP = "drunderhood-fortsmith"  # kept for legacy callers; new endpoints don't need it


def _cfg() -> tuple[str, str]:
    base = (os.environ.get("BRAIN_BASE") or "").rstrip("/")
    token = os.environ.get("BUD_BRAIN_BEARER") or ""
    if not base or not token:
        raise RuntimeError("BRAIN_BASE / BUD_BRAIN_BEARER not configured")
    return base, token


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def lookup(q: str) -> dict:
    """Search customers/vehicles. Returns recent leads + closed repair cases."""
    base, token = _cfg()
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{base}/api/brain/peer/lookup", params={"q": q}, headers=_h(token))
    r.raise_for_status()
    return r.json()


async def open_work() -> dict:
    """What's in the shop right now."""
    base, token = _cfg()
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{base}/api/brain/peer/open-work", headers=_h(token))
    r.raise_for_status()
    return r.json()


# --- legacy shims -------------------------------------------------------
# Old call-sites in briefing.py / etc. don't crash if they still reference
# these. They return empty / no-op so the rest of Bud keeps working.

async def stats(shop_id: str = DEFAULT_SHOP) -> dict:
    return {}


async def recent_outcomes(shop_id: str = DEFAULT_SHOP, limit: int = 50) -> list:
    return []


async def cases(shop_id: str = DEFAULT_SHOP, limit: int = 50, skip: int = 0) -> dict:
    return {"cases": []}


async def operator_profile(*args, **kwargs) -> dict:
    raise RuntimeError("operator-profile endpoint locked down by 9 — use cached overlay")


async def ask(*args, **kwargs) -> dict:
    raise RuntimeError("/api/brain/ask is locked down — use peer.lookup instead")


async def post_morning_briefing(*args, **kwargs) -> dict:
    raise RuntimeError("morning-briefing endpoint locked down")


async def mirror_sync(db, shop_id: str = DEFAULT_SHOP) -> dict:
    """Legacy: now just refreshes open-work into local mirror."""
    out = {"shop_id": shop_id, "mode": "peer-only"}
    try:
        ow = await open_work()
        await db["brain_mirror_open_work"].delete_many({})
        if ow.get("open_leads"):
            await db["brain_mirror_open_work"].insert_many(ow["open_leads"])
        out["open_work"] = {"ok": True, "count": ow.get("open_count", 0)}
    except Exception as e:
        out["open_work"] = {"ok": False, "error": str(e)}
    return out
