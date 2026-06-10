"""Bud — Email-to-Brain ingestion.

Scans Outlook inbox for messages whose subject begins with `BRAIN:`. Each
matched message is parsed and queued in mongo (`brain_ingest_queue`). When 9
ships `POST /api/brain/cases`, the flush job drains queued items into the brain.

Doc's killer feature: he emails himself
  Subject: BRAIN: 2017 Tahoe — lifters held, ran clean 200mi
  Body:    VIN 1GNSCBKC1HR199271
           DTC: P0014, P0017
           Root cause: collapsed lifter bank 2
           Repair: replaced 16 lifters + cam, GM tech bulletin 18-NA-355
           Outcome: PASS — 200 mi follow-up no codes
… and 30 seconds later it's a case in 9's brain.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import outlook as _outlook
import brain_client

router = APIRouter(prefix="/api/brain/ingest", tags=["brain-ingest"])
logger = logging.getLogger(__name__)

QUEUE_COL = "brain_ingest_queue"
SHOP = "drunderhood-fortsmith"

# 9 hasn't shipped POST /api/brain/cases yet. Flip when he does.
_INGEST_FLAG_KEY = "brain.ingest.cases_endpoint_live"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- parsers -------------------------------------------------------------

VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
DTC_RE = re.compile(r"\b([PBCU][0-9A-F]{4})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-4]\d)\b")
MAKES = [
    "chevrolet", "chevy", "gmc", "ford", "ram", "dodge", "jeep", "toyota",
    "honda", "nissan", "subaru", "mazda", "hyundai", "kia", "volkswagen",
    "vw", "bmw", "mercedes", "audi", "lexus", "acura", "buick", "cadillac",
    "lincoln", "tesla",
]


def _parse_brain_email(subject: str, body: str) -> dict:
    """Best-effort field extraction. Anything we can't parse, dump in repair_summary."""
    title = subject.split(":", 1)[1].strip() if ":" in subject else subject.strip()
    blob = body or ""
    out: dict = {
        "id": str(uuid.uuid4()),
        "shop_id": SHOP,
        "title": title,
        "source": "bud-email-ingest",
        "technician_name": "Doc",
        "repair_summary": blob.strip(),
    }
    # VIN
    m = VIN_RE.search(blob)
    if m:
        out["vehicle"] = {"vin": m.group(1).upper()}
    # Year + Make + Model
    y = YEAR_RE.search(title) or YEAR_RE.search(blob)
    lower = (title + "\n" + blob).lower()
    make_hit = next((mk for mk in MAKES if mk in lower), None)
    if y or make_hit:
        out.setdefault("vehicle", {})
        if y:
            out["vehicle"]["year"] = int(y.group(1))
        if make_hit:
            out["vehicle"]["make"] = make_hit.title()
    # DTCs
    dtcs = sorted({d.group(1).upper() for d in DTC_RE.finditer(blob)})
    if dtcs:
        out["dtc_codes"] = dtcs
    # Outcome heuristic
    if re.search(r"\bpass(ed)?\b|\bclean\b|\bran fine\b|\bno codes\b", lower):
        out["outcome"] = "PASS"
    elif re.search(r"\bfail(ed)?\b|\bcame back\b|\bstill\b", lower):
        out["outcome"] = "FAIL"
    elif re.search(r"\bpending\b|\bpartial\b|\bopen\b", lower):
        out["outcome"] = "PARTIAL"
    return out


# --- scanner -------------------------------------------------------------

async def scan_brain_emails(db, limit: int = 25) -> dict:
    """Pull recent inbox, queue any unseen BRAIN: messages."""
    # check we're connected
    tok = await db[_outlook.TOKEN_COL].find_one({"_id": _outlook.PRIMARY_KEY})
    if not tok:
        return {"scanned": 0, "queued": 0, "note": "outlook not connected"}

    # Graph's $filter on startswith(subject) is "InefficientFilter" — pull recent
    # inbox and filter client-side. Cheap because we cap at limit and dedupe.
    params = {
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview",
    }
    r = await _outlook._graph(db, "GET", "/me/mailFolders/Inbox/messages", params=params)
    if r.status_code != 200:
        return {"scanned": 0, "queued": 0, "error": f"Graph {r.status_code}: {r.text[:200]}"}
    all_msgs = (r.json() or {}).get("value", [])
    msgs = [m for m in all_msgs if (m.get("subject") or "").strip().upper().startswith("BRAIN:")]

    queued = 0
    for m in msgs:
        msg_id = m.get("id")
        if not msg_id:
            continue
        if await db[QUEUE_COL].find_one({"outlook_message_id": msg_id}):
            continue
        # fetch full body
        br = await _outlook._graph(
            db, "GET", f"/me/messages/{msg_id}",
            params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview"},
        )
        if br.status_code != 200:
            logger.warning("brain-ingest: graph fetch %s failed: %s", msg_id, br.status_code)
            continue
        full = br.json()
        body_obj = full.get("body") or {}
        body_text = body_obj.get("content") or m.get("bodyPreview") or ""
        # strip HTML if applicable (rough)
        if body_obj.get("contentType", "").lower() == "html":
            body_text = re.sub(r"<[^>]+>", "\n", body_text)
            body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()

        parsed = _parse_brain_email(full.get("subject", ""), body_text)
        parsed["outlook_message_id"] = msg_id
        parsed["received_at"] = full.get("receivedDateTime")
        parsed["from_email"] = ((full.get("from") or {}).get("emailAddress") or {}).get("address")
        parsed["status"] = "queued"
        parsed["queued_at"] = _now()
        await db[QUEUE_COL].insert_one(parsed)
        queued += 1

    return {"scanned": len(msgs), "queued": queued, "at": _now()}


async def flush_queue(db) -> dict:
    """Drain queued items into 9's brain. No-op (returns blocked) until
    POST /api/brain/cases exists upstream."""
    flag = await db["bud_flags"].find_one({"_id": _INGEST_FLAG_KEY})
    if not flag or not flag.get("enabled"):
        pending = await db[QUEUE_COL].count_documents({"status": "queued"})
        return {"flushed": 0, "pending": pending, "blocked_on": "9: POST /api/brain/cases not live"}

    base = (os.environ.get("BRAIN_BASE") or "").rstrip("/")
    token = os.environ.get("BUD_BRAIN_BEARER") or ""
    if not (base and token):
        return {"flushed": 0, "blocked_on": "BRAIN_BASE/BUD_BRAIN_BEARER missing"}

    import httpx
    flushed, failed = 0, 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        # bounded batch — 50 per tick keeps memory predictable
        batch = await db[QUEUE_COL].find({"status": "queued"}).limit(50).to_list(length=50)
        for item in batch:
            payload = {k: v for k, v in item.items() if k not in {"_id", "status", "queued_at", "outlook_message_id", "from_email"}}
            try:
                resp = await client.post(
                    f"{base}/api/brain/cases", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                if resp.status_code in (200, 201):
                    await db[QUEUE_COL].update_one(
                        {"_id": item["_id"]},
                        {"$set": {"status": "posted", "posted_at": _now(), "brain_response": resp.json() if resp.text else {}}},
                    )
                    flushed += 1
                else:
                    await db[QUEUE_COL].update_one(
                        {"_id": item["_id"]},
                        {"$set": {"status": "failed", "last_error": f"HTTP {resp.status_code}: {resp.text[:200]}"}},
                    )
                    failed += 1
            except Exception as e:
                failed += 1
                logger.exception("brain-ingest flush failed: %s", e)
    return {"flushed": flushed, "failed": failed}


# --- routes --------------------------------------------------------------

@router.get("/queue")
async def queue_status(request: Request, limit: int = 50):
    db = request.app.state.db
    counts = {
        "queued": await db[QUEUE_COL].count_documents({"status": "queued"}),
        "posted": await db[QUEUE_COL].count_documents({"status": "posted"}),
        "failed": await db[QUEUE_COL].count_documents({"status": "failed"}),
    }
    items = await db[QUEUE_COL].find(
        {}, {"_id": 0, "repair_summary": 0}
    ).sort("queued_at", -1).limit(limit).to_list(length=limit)
    flag = await db["bud_flags"].find_one({"_id": _INGEST_FLAG_KEY})
    return {"counts": counts, "items": items, "endpoint_live": bool(flag and flag.get("enabled"))}


@router.post("/scan")
async def scan_now(request: Request):
    return await scan_brain_emails(request.app.state.db)


@router.post("/flush")
async def flush_now(request: Request):
    return await flush_queue(request.app.state.db)


class FlagSet(BaseModel):
    enabled: bool


@router.post("/endpoint-live")
async def set_endpoint_live(request: Request, body: FlagSet):
    """Flip when 9 confirms POST /api/brain/cases is live."""
    db = request.app.state.db
    await db["bud_flags"].update_one(
        {"_id": _INGEST_FLAG_KEY},
        {"$set": {"enabled": body.enabled, "updated_at": _now()}},
        upsert=True,
    )
    return {"endpoint_live": body.enabled}
