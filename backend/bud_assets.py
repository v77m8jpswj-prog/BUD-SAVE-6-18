"""Bud — Quick Assets.

Any content Bud generates for Doc to USE elsewhere (email body, message,
code snippet, login info, talking points, customer reply, etc.) goes here
with a one-click copy button on the dashboard.

Rule: NEVER dump multi-line content in chat. Push it here. Chat is for
instructions; the dashboard is for content.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/bud/assets", tags=["assets"])
COLLECTION = "bud_assets"


class AssetCreate(BaseModel):
    title: str
    content: str
    kind: str = "text"  # text | email | code | snippet | address | login | url
    related_url: Optional[str] = None
    note: Optional[str] = None


class Asset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str
    kind: str = "text"
    related_url: Optional[str] = None
    note: Optional[str] = None
    archived: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@router.get("")
async def list_assets(request: Request, include_archived: bool = False, limit: int = 50):
    db = request.app.state.db
    q = {} if include_archived else {"archived": False}
    cursor = db[COLLECTION].find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"assets": items, "count": len(items)}


@router.post("")
async def create_asset(payload: AssetCreate, request: Request):
    db = request.app.state.db
    asset = Asset(**payload.model_dump())
    await db[COLLECTION].insert_one(asset.model_dump())
    return asset


@router.post("/{asset_id}/archive")
async def archive_asset(asset_id: str, request: Request):
    db = request.app.state.db
    r = await db[COLLECTION].update_one({"id": asset_id}, {"$set": {"archived": True}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"ok": True}


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, request: Request):
    db = request.app.state.db
    r = await db[COLLECTION].delete_one({"id": asset_id})
    return {"ok": True, "deleted": r.deleted_count}
