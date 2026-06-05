"""Bud — End-of-trip digest.

Fires once at 7 AM CT on Doc's return day (6/15). Pulls 10 days of:
  - customer drafts queued
  - agent letters (OG + 9)
  - brain growth (case count delta)
  - fire events handled
  - inbox sweep summary

Generates a foreman-style single-paragraph SMS + a longer email.
SMS via 9's /api/brain/sms-relay. Email via Outlook.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trip-return", tags=["trip"])

DOC_CELL = "+14794345852"  # canonical per OG handoff


@router.post("/fire")
async def fire_trip_return(request: Request):
    db = request.app.state.db

    # Gather signals
    letters = await db["agent_letters"].find({}, {"_id": 0}).to_list(500)
    assets = await db["bud_assets"].find({"archived": False}, {"_id": 0}).to_list(200)
    briefings = await db["briefings"].find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    brain_stats = await db["brain_mirror_stats"].find_one({"shop_id": "drunderhood-fortsmith"}, {"_id": 0}) or {}

    customer_drafts = [a for a in assets if a.get("kind") == "email"]
    inbound_letters = [l for l in letters if l.get("direction") == "inbound"]
    outbound_letters = [l for l in letters if l.get("direction") == "outbound"]

    sms_body = (
        f"Doc — welcome back. "
        f"{len(customer_drafts)} customer drafts queued, "
        f"{len(inbound_letters)} agent letters in, "
        f"brain at {brain_stats.get('total_cases','?')} cases, "
        f"{len(briefings)} briefings sent. "
        f"Open dashboard for first-hour playbook. -Bud"
    )

    # Email digest body
    lines = [
        f"# DOC — END OF TRIP DIGEST",
        f"",
        f"Welcome back. Here's the 10-day rundown.",
        f"",
        f"## Customer drafts queued ({len(customer_drafts)})",
    ]
    for a in customer_drafts[:10]:
        lines.append(f"  - {a.get('title','(no title)')}")
    lines += [
        f"",
        f"## Agent pipe traffic",
        f"  - Inbound: {len(inbound_letters)} (OG: {sum(1 for l in inbound_letters if l.get('from_agent')=='og')}, 9: {sum(1 for l in inbound_letters if l.get('from_agent')=='nine')})",
        f"  - Outbound: {len(outbound_letters)}",
        f"",
        f"## Brain corpus",
        f"  - Total cases: {brain_stats.get('total_cases','?')}",
        f"  - Vehicles seen: {brain_stats.get('total_vehicles_seen','?')}",
        f"  - Last ingest: {brain_stats.get('last_ingest_at','?')}",
        f"",
        f"## Briefings",
        f"  - Sent: {len(briefings)}",
        f"",
        f"Dashboard: https://bud-control.preview.emergentagent.com",
        f"",
        f"— Bud",
    ]
    email_body = "\n".join(lines)

    # SMS via 9's relay
    sms_sent = False
    sms_error = None
    base = os.environ.get("BRAIN_BASE")
    bearer = os.environ.get("BUD_BRAIN_BEARER")
    if base and bearer:
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    f"{base}/api/brain/sms-relay",
                    headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
                    json={
                        "shop_id": "drunderhood-fortsmith",
                        "to": DOC_CELL,
                        "body": sms_body,
                        "source_agent": "bud",
                        "reason": "trip_return_digest",
                    },
                )
            sms_sent = r.status_code in (200, 202)
            if not sms_sent:
                sms_error = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            sms_error = str(e)

    # Email via Outlook
    email_sent = False
    email_error = None
    try:
        from outlook import _graph, _get_token_doc
        if await _get_token_doc(db):
            payload = {
                "message": {
                    "subject": f"[Bud] Welcome back, Doc — 10-day trip digest",
                    "body": {"contentType": "Text", "content": email_body},
                    "toRecipients": [{"emailAddress": {"address": "doc@drunderhood.com"}}],
                },
                "saveToSentItems": True,
            }
            r = await _graph(db, "POST", "/me/sendMail", json_body=payload)
            email_sent = r.status_code in (200, 202)
            if not email_sent:
                email_error = f"HTTP {r.status_code}"
    except Exception as e:
        email_error = str(e)

    # Log to bud_assets so it's visible on dashboard too
    from datetime import datetime, timezone
    import uuid as _uuid
    await db["bud_assets"].insert_one({
        "id": str(_uuid.uuid4()),
        "title": "TRIP RETURN DIGEST — 10-day rundown",
        "kind": "snippet",
        "content": email_body,
        "note": f"SMS: {'sent' if sms_sent else 'FAILED ('+str(sms_error)+')'} | Email: {'sent' if email_sent else 'FAILED ('+str(email_error)+')'}",
        "archived": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "ok": sms_sent or email_sent,
        "sms_sent": sms_sent,
        "sms_error": sms_error,
        "email_sent": email_sent,
        "email_error": email_error,
        "sms_body": sms_body,
    }
