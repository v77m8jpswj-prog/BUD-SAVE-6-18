"""Bud — Self-directed task queue.

Persisted across fork starts so Bud picks up his own work between sessions.
Auto-populated from inbound SMS / email / agent-mail events; manually populated
from the dashboard.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

COL = "bud_tasks"
STATUSES = {"todo", "doing", "blocked", "done"}
PRIORITIES = {"P0", "P1", "P2", "P3"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskCreate(BaseModel):
    title: str
    priority: str = "P2"
    status: str = "todo"
    source: str = "manual"
    source_ref: Optional[str] = None
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


async def create_task_if_new(
    db,
    *,
    source: str,
    source_ref: str,
    title: str,
    priority: str = "P2",
    notes: Optional[str] = None,
) -> dict:
    """Idempotent task creation. If a task with this (source, source_ref) already
    exists and isn't done, return it; otherwise insert a new one."""
    existing = await db[COL].find_one(
        {"source": source, "source_ref": source_ref, "status": {"$ne": "done"}},
        {"_id": 0},
    )
    if existing:
        return existing
    doc = {
        "id": str(uuid.uuid4()),
        "title": title,
        "priority": priority if priority in PRIORITIES else "P2",
        "status": "todo",
        "source": source,
        "source_ref": source_ref,
        "notes": notes,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_tasks(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    db = request.app.state.db
    filt: dict = {}
    if status:
        filt["status"] = status
    if priority:
        filt["priority"] = priority
    cursor = db[COL].find(filt, {"_id": 0}).sort([("status", 1), ("priority", 1), ("created_at", -1)]).limit(limit)
    items = await cursor.to_list(length=limit)
    counts = {}
    for s in STATUSES:
        counts[s] = await db[COL].count_documents({"status": s})
    return {"tasks": items, "counts": counts}


@router.post("")
async def create_task(request: Request, body: TaskCreate):
    db = request.app.state.db
    if body.status not in STATUSES:
        raise HTTPException(400, detail=f"status must be one of {sorted(STATUSES)}")
    if body.priority not in PRIORITIES:
        raise HTTPException(400, detail=f"priority must be one of {sorted(PRIORITIES)}")
    doc = {
        "id": str(uuid.uuid4()),
        "title": body.title.strip(),
        "priority": body.priority,
        "status": body.status,
        "source": body.source,
        "source_ref": body.source_ref,
        "notes": body.notes,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/{task_id}")
async def update_task(request: Request, task_id: str, body: TaskUpdate):
    db = request.app.state.db
    patch: dict = {"updated_at": _now()}
    if body.title is not None:
        patch["title"] = body.title.strip()
    if body.priority is not None:
        if body.priority not in PRIORITIES:
            raise HTTPException(400, detail=f"priority must be one of {sorted(PRIORITIES)}")
        patch["priority"] = body.priority
    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(400, detail=f"status must be one of {sorted(STATUSES)}")
        patch["status"] = body.status
    if body.notes is not None:
        patch["notes"] = body.notes
    r = await db[COL].find_one_and_update(
        {"id": task_id}, {"$set": patch}, return_document=True, projection={"_id": 0}
    )
    if not r:
        raise HTTPException(404, detail="task not found")
    return r


@router.delete("/{task_id}")
async def delete_task(request: Request, task_id: str):
    db = request.app.state.db
    r = await db[COL].delete_one({"id": task_id})
    return {"deleted": r.deleted_count}
