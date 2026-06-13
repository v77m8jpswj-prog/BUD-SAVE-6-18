"""Bud — Brain dashboard routes (locked-down peer API only).

Exposes:
  GET  /api/brain/status               quick connection check + open-work count
  POST /api/brain/sync-now             refresh local open-work mirror
  GET  /api/brain/peer/open-work       proxy to 9's open-work
  GET  /api/brain/peer/lookup?q=...    proxy to 9's lookup
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

import brain_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brain", tags=["brain"])

SHOP = "drunderhood-fortsmith"


@router.get("/status")
async def brain_status(request: Request):
    out: dict = {"shop_id": SHOP, "mode": "peer-only"}
    try:
        ow = await brain_client.open_work()
        out["connected"] = True
        out["open_count"] = ow.get("open_count", 0)
        out["open_leads_preview"] = (ow.get("open_leads") or [])[:5]
    except Exception as e:
        out["connected"] = False
        out["error"] = str(e)
    return out


@router.post("/sync-now")
async def brain_sync_now(request: Request):
    db = request.app.state.db
    try:
        return await brain_client.mirror_sync(db, SHOP)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/peer/open-work")
async def peer_open_work():
    try:
        return await brain_client.open_work()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"open-work failed: {e}")


@router.get("/peer/lookup")
async def peer_lookup(q: str = Query(..., min_length=1)):
    try:
        return await brain_client.lookup(q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"lookup failed: {e}")
