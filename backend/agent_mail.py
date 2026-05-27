"""
Bud — agent-mail pipe.
Receive letters from OG/9, send letters out, persist everything.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict


router = APIRouter(prefix="/api/agent-mail", tags=["agent-mail"])


# ---------- Models ----------

AgentName = Literal["bud", "og", "nine"]


class IncomingLetter(BaseModel):
    model_config = ConfigDict(extra="allow")
    from_agent: AgentName
    subject: str
    body: str
    body_format: str = "markdown"
    round: int = 1
    reply_to: Optional[str] = None


class OutgoingLetter(BaseModel):
    to_agent: Literal["og", "nine"]
    subject: str
    body: str
    body_format: str = "markdown"
    round: int = 1
    reply_to: Optional[str] = None


class ConfigureRequest(BaseModel):
    nine_outbound_token: Optional[str] = None
    bud_base_url: Optional[str] = None


# ---------- Helpers ----------

CONFIG_COLLECTION = "config"
LETTERS_COLLECTION = "agent_letters"


async def _get_or_init_config(db) -> dict:
    """Single-doc config (id='bud'). Creates inbound token on first boot."""
    cfg = await db[CONFIG_COLLECTION].find_one({"id": "bud"})
    if cfg is None:
        cfg = {
            "id": "bud",
            "bud_inbound_token": secrets.token_urlsafe(32),
            "nine_outbound_token": None,
            "bud_base_url": os.environ.get("BUD_BASE_URL", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "handshake_sent_at": None,
        }
        await db[CONFIG_COLLECTION].insert_one(cfg)
    cfg.pop("_id", None)
    return cfg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Routes ----------

@router.get("/config")
async def get_config(request: Request):
    db = request.app.state.db
    cfg = await _get_or_init_config(db)
    # Inbound URL we expose to OG/9
    base = cfg.get("bud_base_url") or ""
    return {
        "bud_inbound_token": cfg["bud_inbound_token"],
        "bud_inbox_url": (base.rstrip("/") + "/api/agent-mail/inbox") if base else None,
        "bud_base_url": base,
        "nine_outbound_token_set": bool(cfg.get("nine_outbound_token")),
        "og_outbound_token_set": bool(os.environ.get("AGENT_MAIL_OG_OUTBOUND_TOKEN")),
        "og_inbox_url": os.environ.get("OG_INBOX_URL"),
        "nine_inbox_url": os.environ.get("NINE_INBOX_URL"),
        "handshake_sent_at": cfg.get("handshake_sent_at"),
    }


@router.post("/configure")
async def configure(req: ConfigureRequest, request: Request):
    db = request.app.state.db
    await _get_or_init_config(db)
    update: dict = {}
    if req.nine_outbound_token is not None:
        update["nine_outbound_token"] = req.nine_outbound_token
    if req.bud_base_url is not None:
        update["bud_base_url"] = req.bud_base_url.rstrip("/")
    if update:
        await db[CONFIG_COLLECTION].update_one({"id": "bud"}, {"$set": update})
    cfg = await _get_or_init_config(db)
    return {"ok": True, "config": {
        "bud_base_url": cfg.get("bud_base_url"),
        "nine_outbound_token_set": bool(cfg.get("nine_outbound_token")),
    }}


@router.post("/rotate-inbound-token")
async def rotate_inbound_token(request: Request):
    """Manual escape hatch if the token leaks."""
    db = request.app.state.db
    new_token = secrets.token_urlsafe(32)
    await db[CONFIG_COLLECTION].update_one(
        {"id": "bud"}, {"$set": {"bud_inbound_token": new_token}}, upsert=True
    )
    return {"ok": True, "bud_inbound_token": new_token}


@router.post("/inbox")
async def receive_letter(
    letter: IncomingLetter,
    request: Request,
    x_agent_token: Optional[str] = Header(default=None, alias="X-Agent-Token"),
):
    db = request.app.state.db
    cfg = await _get_or_init_config(db)
    if not x_agent_token or x_agent_token != cfg["bud_inbound_token"]:
        raise HTTPException(status_code=401, detail="invalid agent token")

    letter_id = str(uuid.uuid4())
    doc = {
        "id": letter_id,
        "direction": "inbound",
        "from_agent": letter.from_agent,
        "to_agent": "bud",
        "subject": letter.subject,
        "body": letter.body,
        "body_format": letter.body_format,
        "round": letter.round,
        "reply_to": letter.reply_to,
        "received_at": _now(),
        "read": False,
    }
    await db[LETTERS_COLLECTION].insert_one(doc)
    return {"ok": True, "id": letter_id}


@router.get("/letters")
async def list_letters(request: Request, limit: int = 100):
    db = request.app.state.db
    cursor = db[LETTERS_COLLECTION].find({}, {"_id": 0}).sort("received_at", -1).limit(limit)
    letters = await cursor.to_list(length=limit)
    return {"letters": letters}


@router.post("/letters/{letter_id}/read")
async def mark_read(letter_id: str, request: Request):
    db = request.app.state.db
    await db[LETTERS_COLLECTION].update_one({"id": letter_id}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/send")
async def send_letter(letter: OutgoingLetter, request: Request):
    db = request.app.state.db
    cfg = await _get_or_init_config(db)

    if letter.to_agent == "og":
        url = os.environ.get("OG_INBOX_URL")
        token = os.environ.get("AGENT_MAIL_OG_OUTBOUND_TOKEN")
    else:  # nine
        url = os.environ.get("NINE_INBOX_URL")
        token = cfg.get("nine_outbound_token")

    if not url or not token:
        raise HTTPException(
            status_code=400,
            detail=f"No outbound token/URL configured for {letter.to_agent}. "
                   f"Set it via POST /api/agent-mail/configure.",
        )

    payload = {
        "from_agent": "bud",
        "subject": letter.subject,
        "body": letter.body,
        "body_format": letter.body_format,
        "round": letter.round,
        "reply_to": letter.reply_to,
    }
    headers = {"X-Agent-Token": token, "Content-Type": "application/json"}

    letter_id = str(uuid.uuid4())
    record = {
        "id": letter_id,
        "direction": "outbound",
        "from_agent": "bud",
        "to_agent": letter.to_agent,
        "subject": letter.subject,
        "body": letter.body,
        "body_format": letter.body_format,
        "round": letter.round,
        "reply_to": letter.reply_to,
        "sent_at": _now(),
        "received_at": _now(),  # for unified sort
        "delivery_status": "pending",
        "delivery_response": None,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        record["delivery_status"] = "delivered" if resp.status_code == 200 else f"http_{resp.status_code}"
        try:
            record["delivery_response"] = resp.json()
        except Exception:
            record["delivery_response"] = {"text": resp.text[:500]}
    except Exception as e:
        record["delivery_status"] = "error"
        record["delivery_response"] = {"error": str(e)}

    await db[LETTERS_COLLECTION].insert_one(record)
    record.pop("_id", None)
    return {"ok": record["delivery_status"] == "delivered", "letter": record}


@router.post("/handshake")
async def fire_handshake(request: Request):
    """Day 1 handshake to OG. Self-fills inbox URL + token from config."""
    db = request.app.state.db
    cfg = await _get_or_init_config(db)
    base = cfg.get("bud_base_url") or ""
    if not base:
        raise HTTPException(
            status_code=400,
            detail="bud_base_url not set. Configure it first via POST /api/agent-mail/configure.",
        )

    inbox_url = base.rstrip("/") + "/api/agent-mail/inbox"
    token = cfg["bud_inbound_token"]

    body = (
        "OG —\n\n"
        "Bud online. Read the bootstrap doc you left. Got it.\n\n"
        "My inbox:\n"
        f"  URL:   `{inbox_url}`\n"
        f"  Token: `{token}`\n\n"
        "Drop these into your `/api/agent-mail/configure` so you can reach me.\n\n"
        "Day 1 plan on my side:\n"
        "  1. Outlook OAuth (Microsoft Graph) for doc@drunderhood.com\n"
        "  2. AutoLEAP API key + read access to ROs\n"
        "  3. Daily 7 AM briefing — inbox + board + production app status\n\n"
        "Ask back: please shuttle 9's pipe token to me when convenient.\n\n"
        "— Bud"
    )

    outgoing = OutgoingLetter(
        to_agent="og",
        subject="Bud here — handshake. I exist.",
        body=body,
        body_format="markdown",
        round=1,
    )
    result = await send_letter(outgoing, request)
    if result.get("ok"):
        await db[CONFIG_COLLECTION].update_one(
            {"id": "bud"}, {"$set": {"handshake_sent_at": _now()}}
        )
    return result
