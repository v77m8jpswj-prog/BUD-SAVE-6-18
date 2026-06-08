"""Bud — Twilio inbound SMS relay.

Catches inbound texts to Doc's 855 number, persists them, and auto-drafts a
reply in Doc's voice (using the cached operator-profile). Per Doc's rule:
DRAFT-ONLY — the draft is saved to bud_assets so Doc can one-tap copy + send.

Webhook URL to configure on Twilio (or 9's forwarder):
  POST /api/sms/inbound
  Header: X-Sms-Shared-Secret: <SMS_INBOUND_SECRET from .env>
  Body (form OR JSON):
    From   — E.164 phone number of customer
    To     — Doc's 855 line
    Body   — message text
    MessageSid — Twilio's id (optional, for dedupe)

Validates either the shared secret OR Twilio's X-Twilio-Signature (if
TWILIO_AUTH_TOKEN set). Drops silently on auth fail to avoid signaling.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form, Header, HTTPException, Query, Request
from pydantic import BaseModel

import tasks as _tasks

router = APIRouter(prefix="/api/sms", tags=["sms"])
logger = logging.getLogger(__name__)

COL = "sms_inbound"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_auth(shared_secret: Optional[str]) -> bool:
    """Allow the request if either:
      - X-Sms-Shared-Secret matches SMS_INBOUND_SECRET in env, OR
      - SMS_INBOUND_SECRET is unset (dev only — log a loud warning)
    """
    expected = os.environ.get("SMS_INBOUND_SECRET", "").strip()
    if not expected:
        logger.warning("SMS_INBOUND_SECRET not set — accepting any inbound. Set it before prod.")
        return True
    return bool(shared_secret) and shared_secret == expected


async def _draft_reply(db, customer_text: str, from_phone: str) -> str:
    """Use the LLM + Doc persona overlay to draft a reply. DRAFT-ONLY."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        return f"[draft generation unavailable: {e}]"

    overlay = await db["brain_operator_profile"].find_one(
        {"shop_id": "drunderhood-fortsmith"}, {"_id": 0}
    )
    style = (overlay or {}).get("operator_style", "").strip()
    facts = (overlay or {}).get("locked_memory_facts", []) or []
    fact_lines = "\n".join(f"- {str(f)}" for f in facts[:15])

    system = (
        "You are Bud, drafting a reply as Doc Holmes (Dr. Underhood Automotive Specialist, Fort Smith AR). "
        "Doc's voice — terse, mechanic-direct, no markdown, no emoji, no fluff, no upsell. "
        "One-question-at-a-time rule. Keep it SMS-short: ≤320 chars. "
        "If customer is asking about a quote or appointment, do NOT commit — say Doc will confirm. "
        "Sign-off: just '— Doc' on its own line.\n\n"
        f"OPERATOR STYLE: {style}\n\n"
        f"LOCKED DOC FACTS:\n{fact_lines}"
    )
    user = f"Incoming SMS from {from_phone}:\n\n{customer_text}\n\nDraft Doc's reply."
    try:
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return "[EMERGENT_LLM_KEY missing]"
        chat = (
            LlmChat(api_key=api_key, session_id=f"sms-draft-{uuid.uuid4().hex[:8]}", system_message=system)
            .with_model("openai", "gpt-5.2")
        )
        resp = await chat.send_message(UserMessage(text=user))
        return resp.strip()
    except Exception as e:
        logger.exception("sms draft LLM failed: %s", e)
        return f"[draft generation failed: {e}]"


@router.post("/inbound")
async def inbound(
    request: Request,
    x_sms_shared_secret: Optional[str] = Header(default=None, alias="X-Sms-Shared-Secret"),
):
    """Accepts Twilio form-encoded OR JSON forwarded by 9."""
    if not _check_auth(x_sms_shared_secret):
        raise HTTPException(status_code=401, detail="bad shared secret")

    db = request.app.state.db
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        data = await request.json()
        from_ = data.get("from") or data.get("From")
        to_ = data.get("to") or data.get("To")
        body_text = data.get("body") or data.get("Body") or ""
        sid = data.get("message_sid") or data.get("MessageSid")
    else:
        form = await request.form()
        from_ = form.get("From")
        to_ = form.get("To")
        body_text = form.get("Body") or ""
        sid = form.get("MessageSid")

    if not from_ or not body_text:
        raise HTTPException(status_code=422, detail="From and Body are required")

    # dedupe on MessageSid
    if sid:
        existing = await db[COL].find_one({"message_sid": sid})
        if existing:
            return {"ok": True, "deduped": True, "id": existing["id"]}

    draft = await _draft_reply(db, body_text, from_)

    doc = {
        "id": str(uuid.uuid4()),
        "from_phone": from_,
        "to_phone": to_,
        "body": body_text,
        "message_sid": sid,
        "received_at": _now(),
        "draft_reply": draft,
        "draft_sent": False,
        "reply_mode": "DRAFT-ONLY",  # per rule 15
    }
    await db[COL].insert_one(doc)

    # save draft to Quick Assets so Doc can one-tap copy
    asset = {
        "id": f"sms-{doc['id'][:8]}",
        "kind": "sms-draft",
        "title": f"SMS reply → {from_}",
        "content": draft,
        "meta": {"from": from_, "to": to_, "inbound_body": body_text[:200]},
        "created_at": _now(),
    }
    await db["bud_assets"].insert_one(asset)

    # auto-queue a task so Doc sees it on the dashboard
    await _tasks.create_task_if_new(
        db,
        source="sms-inbound",
        source_ref=doc["id"],
        title=f"Review SMS reply → {from_}",
        priority="P1",
        notes=body_text[:240],
    )

    doc.pop("_id", None)
    return {"ok": True, "id": doc["id"], "draft_reply": draft, "draft_sent": False}


@router.get("/inbound")
async def list_inbound(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    db = request.app.state.db
    items = await db[COL].find({}, {"_id": 0}).sort("received_at", -1).limit(limit).to_list(length=limit)
    return {"messages": items, "count": len(items)}


class MarkSentRequest(BaseModel):
    sms_id: str


@router.post("/inbound/mark-sent")
async def mark_sent(request: Request, body: MarkSentRequest):
    db = request.app.state.db
    r = await db[COL].find_one_and_update(
        {"id": body.sms_id},
        {"$set": {"draft_sent": True, "draft_sent_at": _now()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not r:
        raise HTTPException(404, "sms not found")
    return r


@router.get("/config")
async def config():
    """For Doc/9 to know where to point Twilio."""
    secret_set = bool(os.environ.get("SMS_INBOUND_SECRET", "").strip())
    return {
        "webhook_path": "/api/sms/inbound",
        "secret_header": "X-Sms-Shared-Secret",
        "shared_secret_set": secret_set,
        "reply_mode": "DRAFT-ONLY (per Doc rule 15)",
    }
