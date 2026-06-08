"""Bud Voice — client to 9's shared Voice Service (OpenAI Realtime via 9).

9 mints ephemeral OpenAI keys; the browser does direct WebRTC to OpenAI.
Bud's backend just proxies the mint request through 9's agent-token auth.
"""
from __future__ import annotations

import os
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/voice-rt", tags=["voice-realtime"])


def _nine_base() -> str:
    return os.environ.get("NINE_VOICE_BASE", "https://foreman.drunderhood.com")


def _nine_token() -> str:
    # 9's outbound token is what 9 expects on incoming requests from Bud
    # (per 9's R5: "Auth: X-Agent-Token: <your agent-mail token, same one
    #  you use for the mail pipe>")
    t = os.environ.get("BUD_VOICE_AGENT_TOKEN")
    if not t:
        raise HTTPException(status_code=500, detail="BUD_VOICE_AGENT_TOKEN not set")
    return t


async def _build_doc_persona(db) -> Optional[str]:
    """Stitch a voice-ready Doc persona from 9's cached operator-profile."""
    cached = await db["brain_operator_profile"].find_one(
        {"shop_id": "drunderhood-fortsmith"}, {"_id": 0}
    )
    if not cached:
        try:
            import brain_client as _bc
            cached = await _bc.operator_profile()
            cached["shop_id"] = "drunderhood-fortsmith"
            await db["brain_operator_profile"].update_one(
                {"shop_id": "drunderhood-fortsmith"}, {"$set": cached}, upsert=True
            )
        except Exception:
            return None
    style = (cached.get("operator_style") or "").strip()
    facts = cached.get("locked_memory_facts") or []
    if not style and not facts:
        return None
    shop = (cached.get("shop_profile") or {}).get("name", "Dr. Underhood Automotive Specialist")
    parts = [
        "You are Bud, Doc Holmes's AI Foreman for " + shop + ".",
        "You speak as Doc's right-hand — terse, technical, no fluff.",
        "Never say 'Heard', 'Noted', 'Got it', 'Understood', 'Acknowledged', or any empty receipt phrase.",
        "No markdown bolding. No emoji. No corporate softeners. Lead with the result.",
        "",
        "DOC OPERATOR STYLE (verbatim from his locked profile):",
        style,
    ]
    if facts:
        parts.append("")
        parts.append("LOCKED DOC FACTS (never contradict these — they ARE Doc):")
        seen = set()
        for f in facts[:25]:
            t = str(f).strip()
            if t and t not in seen:
                seen.add(t)
                parts.append("- " + t)
    return "\n".join(parts)


class MintRequest(BaseModel):
    voice: str = "ash"
    eagerness: str = "medium"  # low | medium | high
    persona: Optional[str] = None


@router.post("/mint")
async def mint_session(req: MintRequest, request: Request):
    """Mint an ephemeral OpenAI Realtime session token via 9, with Doc persona overlay."""
    payload = {
        "caller_agent": "bud",
        "voice": req.voice,
        "eagerness": req.eagerness,
        "doc_user_email": os.environ.get("MS_PRIMARY_USER_EMAIL", "doc@drunderhood.com"),
    }
    # Frontend can override; otherwise auto-build Doc persona from cached operator-profile
    persona = req.persona
    if not persona:
        try:
            persona = await _build_doc_persona(request.app.state.db)
        except Exception:
            persona = None
    if persona:
        payload["persona"] = persona

    url = _nine_base().rstrip("/") + "/api/voice/ephemeral-token"
    headers = {"X-Agent-Token": _nine_token(), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"9 mint failed: {r.text[:300]}")
    return r.json()


class LogTurnRequest(BaseModel):
    session_id: str
    role: str  # user|assistant|system
    text: str
    audio_url: Optional[str] = None


@router.post("/log")
async def log_turn(req: LogTurnRequest):
    """Persist a turn via 9's shared brain."""
    url = _nine_base().rstrip("/") + f"/api/voice/turn-log/{req.session_id}"
    headers = {"X-Agent-Token": _nine_token(), "Content-Type": "application/json"}
    body = {
        "caller_agent": "bud",
        "role": req.role,
        "text": req.text,
    }
    if req.audio_url:
        body["audio_url"] = req.audio_url
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(url, headers=headers, json=body)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"9 log failed: {r.text[:300]}")
    return r.json()


@router.get("/transcript/{session_id}")
async def get_transcript(session_id: str, limit: int = 200):
    url = _nine_base().rstrip("/") + f"/api/voice/turn-log/{session_id}"
    headers = {"X-Agent-Token": _nine_token()}
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(url, headers=headers, params={"limit": limit})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"9 transcript fetch failed: {r.text[:300]}")
    return r.json()
