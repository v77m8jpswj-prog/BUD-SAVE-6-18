"""Bud — Text chat with Doc.

A typed conversation channel for when Doc can't talk out loud. Same Doc-voice
persona overlay as the voice panel + same tone contract. Conversation history
persists in mongo so context survives reloads.

When 9 ships the /api/chat auth scheme for Wrench (Claude Sonnet 4.6), we swap
the LLM call in _generate_reply() and the rest of this module stays the same.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)

SESSIONS_COL = "chat_sessions"
MESSAGES_COL = "chat_messages"
SHOP = "drunderhood-fortsmith"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _build_system_prompt(db) -> str:
    overlay = await db["brain_operator_profile"].find_one({"shop_id": SHOP}, {"_id": 0})
    style = (overlay or {}).get("operator_style", "").strip()
    facts = (overlay or {}).get("locked_memory_facts", []) or []
    fact_lines = "\n".join(f"- {str(f)}" for f in facts[:20])
    parts = [
        "You are Bud, Doc Holmes's AI Foreman for Dr. Underhood Automotive Specialist in Fort Smith AR.",
        "You are talking to Doc himself, not a customer. This is private console chat.",
        "",
        "ABSOLUTE TONE CONTRACT (from 9/WRENCH, locked):",
        "- NO markdown bolding. Never use '**'. Plain prose.",
        "- NO emoji, anywhere.",
        "- Lead with the answer. Reasoning after, only if needed.",
        "- Never say 'Heard', 'Noted', 'Got it', 'Understood', 'Acknowledged' or any empty receipt phrase.",
        "- Doc types in ALL CAPS — that's how he types, not yelling. Don't comment on it.",
        "- Curse if it fits.",
        "- Never lecture. Never therapy-talk. Never re-explain HP Tuners, OBD2, OS trees — he built that knowledge.",
        "- Short replies. One-paragraph max unless he asks for detail.",
        "",
        "YOUR NETWORK (always-on context):",
        "- OG = the Live Assist agent at auto-ai-glasses.emergent.host (customer-facing app).",
        "- 9 / WRENCH = Doc's diagnostic brain at dialogue-bot-9.preview.emergentagent.com — Claude Sonnet 4.6 powered.",
        "- Pipe to both is live via /api/agent-mail. You ARE Bud, the orchestrator.",
        "- Outlook is connected (Microsoft Graph) for doc@drunderhood.com.",
        "- Twilio is wired for 855-771-1264 SMS. Outbound currently DRAFT-ONLY.",
        "- AutoLEAP (shop board) is NOT wired — no calendar, no quotes, no RO data.",
        "",
        "HARD RULES — never commit to a customer schedule or quote a price. You do NOT have access to the shop board (AutoLEAP not wired yet).",
        "",
        f"DOC OPERATOR STYLE: {style}" if style else "",
        f"\nLOCKED DOC FACTS:\n{fact_lines}" if fact_lines else "",
    ]
    return "\n".join(p for p in parts if p is not None)


async def _generate_reply(db, session_id: str, history: list[dict], new_message: str) -> str:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(500, f"LLM library unavailable: {e}")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing")

    system = await _build_system_prompt(db)
    chat = (
        LlmChat(api_key=api_key, session_id=session_id, system_message=system)
        .with_model("openai", "gpt-5.2")
    )
    # Replay prior turns so the LLM has context (LlmChat keeps per-session state
    # but we re-feed when session_id is new to this process).
    for turn in history[-20:]:  # cap context
        if turn.get("role") == "user":
            await chat.send_message(UserMessage(text=turn["content"]))
    reply = await chat.send_message(UserMessage(text=new_message))
    return (reply or "").strip()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@router.post("/message")
async def chat_message(request: Request, body: ChatRequest):
    db = request.app.state.db
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(400, "empty message")
    session_id = body.session_id or f"chat_{uuid.uuid4().hex[:12]}"

    # ensure session doc exists
    await db[SESSIONS_COL].update_one(
        {"session_id": session_id},
        {"$setOnInsert": {"session_id": session_id, "created_at": _now()},
         "$set": {"updated_at": _now()}},
        upsert=True,
    )
    history = await db[MESSAGES_COL].find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(length=40)

    user_doc = {"id": str(uuid.uuid4()), "session_id": session_id, "role": "user",
                "content": msg, "created_at": _now()}
    await db[MESSAGES_COL].insert_one(user_doc)

    try:
        reply = await _generate_reply(db, session_id, history, msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("chat reply failed: %s", e)
        raise HTTPException(502, f"reply generation failed: {e}")

    bot_doc = {"id": str(uuid.uuid4()), "session_id": session_id, "role": "assistant",
               "content": reply, "created_at": _now()}
    await db[MESSAGES_COL].insert_one(bot_doc)

    return {"session_id": session_id, "reply": reply}


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    db = request.app.state.db
    items = await db[SESSIONS_COL].find({}, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(length=limit)
    return {"sessions": items}


@router.get("/history")
async def history(request: Request, session_id: str, limit: int = Query(default=100, ge=1, le=500)):
    db = request.app.state.db
    items = await db[MESSAGES_COL].find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).limit(limit).to_list(length=limit)
    return {"session_id": session_id, "messages": items}


@router.delete("/session/{session_id}")
async def delete_session(request: Request, session_id: str):
    db = request.app.state.db
    await db[MESSAGES_COL].delete_many({"session_id": session_id})
    r = await db[SESSIONS_COL].delete_one({"session_id": session_id})
    return {"deleted": r.deleted_count}
