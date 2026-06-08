"""Bud — Brain dashboard routes.

Exposes:
  GET  /api/brain/status         live stats from 9 + local mirror state
  POST /api/brain/sync-now       on-demand mirror sync (admin button)
  GET  /api/brain/cases-mirror   local-mirrored cases with optional text search
                                 (9's server-side filter isn't honored — we
                                  search the mirror client-side)
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
    db = request.app.state.db
    out: dict = {"shop_id": SHOP}
    try:
        out["live"] = await brain_client.stats(SHOP)
        out["connected"] = True
    except Exception as e:
        out["connected"] = False
        out["error"] = str(e)
    mirror = await db["brain_mirror_stats"].find_one({"shop_id": SHOP}, {"_id": 0})
    out["mirror"] = mirror or None
    out["mirror_cases_count"] = await db["brain_mirror_cases"].count_documents({"shop_id": SHOP})
    out["mirror_outcomes_count"] = await db["brain_mirror_outcomes"].count_documents({"shop_id": SHOP})
    return out


@router.post("/sync-now")
async def brain_sync_now(request: Request):
    db = request.app.state.db
    try:
        return await brain_client.mirror_sync(db, SHOP)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases-mirror")
async def cases_mirror(
    request: Request,
    q: Optional[str] = Query(default=None, description="case-insensitive substring search"),
    limit: int = 30,
):
    db = request.app.state.db
    filt: dict = {"shop_id": SHOP}
    if q:
        # plain $regex on the obvious case fields
        filt["$or"] = [
            {"symptom": {"$regex": q, "$options": "i"}},
            {"repair_summary": {"$regex": q, "$options": "i"}},
            {"root_cause": {"$regex": q, "$options": "i"}},
            {"vehicle.make": {"$regex": q, "$options": "i"}},
            {"vehicle.model": {"$regex": q, "$options": "i"}},
            {"vehicle.vin": {"$regex": q, "$options": "i"}},
            {"dtc_codes": {"$regex": q, "$options": "i"}},
            {"parts": {"$regex": q, "$options": "i"}},
        ]
    cursor = db["brain_mirror_cases"].find(filt, {"_id": 0}).sort("created_at", -1).limit(limit)
    return {"q": q, "cases": await cursor.to_list(length=limit)}
