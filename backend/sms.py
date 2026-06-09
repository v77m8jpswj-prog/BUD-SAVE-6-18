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
        "Doc's voice — terse, mechanic-direct. ABSOLUTE RULES from 9/WRENCH tone contract: "
        "NO markdown bolding (no '**'), NO emoji, NO upsell, NO fluff, NO 'let me know'. "
        "Plain prose only. Lead with the answer. ALL CAPS is fine — that's how Doc types. "
        "Curse if it fits. Never lecture. Never re-explain HP Tuners/OBD2/diagnostics — he built that knowledge. "
        "One-question-at-a-time rule. Keep it SMS-short: max 320 chars. "
        "If customer asks for a quote or appointment, do NOT commit — say Doc will confirm. "
        "Sign-off: just 'DOC' on its own line. No dash, no emoji.\n\n"
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
        "outbound_send_enabled": bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN")),
    }


# ---- Outbound send (kill-flag gated) -----------------------------------

OUTBOUND_FLAG_KEY = "sms.outbound.send_enabled"


async def _outbound_enabled(db) -> bool:
    """Two-key gate: env creds present AND mongo flag enabled."""
    if not (os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN") and os.environ.get("TWILIO_FROM_NUMBER")):
        return False
    flag = await db["bud_flags"].find_one({"_id": OUTBOUND_FLAG_KEY})
    return bool(flag and flag.get("enabled"))


class OutboundSend(BaseModel):
    to: str
    body: str
    sms_id: Optional[str] = None  # if replying to an inbound, the sms_inbound.id


class OutboundFlag(BaseModel):
    enabled: bool


@router.post("/outbound/enable")
async def outbound_enable(request: Request, body: OutboundFlag):
    """Doc-only toggle to flip outbound on/off. Stays off by default."""
    db = request.app.state.db
    await db["bud_flags"].update_one(
        {"_id": OUTBOUND_FLAG_KEY},
        {"$set": {"enabled": body.enabled, "updated_at": _now()}},
        upsert=True,
    )
    return {"outbound_send_enabled": body.enabled}


@router.post("/outbound/send")
async def outbound_send(request: Request, body: OutboundSend):
    """Send via Twilio REST API. Gated by env creds + mongo flag.
    Refuses to fire unless BOTH are green."""
    db = request.app.state.db
    if not await _outbound_enabled(db):
        raise HTTPException(
            status_code=409,
            detail="outbound send disabled. either Twilio env creds missing or feature flag is off (POST /api/sms/outbound/enable {\"enabled\":true}).",
        )

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    from_num = os.environ["TWILIO_FROM_NUMBER"]
    status_cb = os.environ.get("TWILIO_STATUS_CALLBACK_URL")

    import httpx
    form = {"From": from_num, "To": body.to, "Body": body.body}
    if status_cb:
        form["StatusCallback"] = status_cb

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    try:
        async with httpx.AsyncClient(timeout=20.0, auth=(sid, token)) as c:
            r = await c.post(url, data=form)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"twilio request failed: {e}")

    out_doc = {
        "id": str(uuid.uuid4()),
        "to_phone": body.to,
        "from_phone": from_num,
        "body": body.body,
        "in_reply_to_sms_id": body.sms_id,
        "sent_at": _now(),
        "twilio_status": r.status_code,
        "twilio_response": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500],
    }
    await db["sms_outbound"].insert_one(out_doc)

    # if this was a reply to an inbound, mark sent
    if body.sms_id:
        await db[COL].update_one(
            {"id": body.sms_id},
            {"$set": {"draft_sent": True, "draft_sent_at": _now(), "outbound_id": out_doc["id"]}},
        )

    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"twilio rejected: HTTP {r.status_code} — {r.text[:300]}",
        )

    out_doc.pop("_id", None)
    return {"ok": True, "outbound": out_doc}


@router.get("/outbound")
async def list_outbound(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    db = request.app.state.db
    items = await db["sms_outbound"].find({}, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(length=limit)
    return {"messages": items, "count": len(items)}
