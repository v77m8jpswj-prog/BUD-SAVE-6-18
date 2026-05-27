"""Bud — Voice Loop.

Push-to-talk → Whisper STT → GPT-5.2 → OpenAI TTS → audio reply.

Multi-turn: every session_id keeps its own conversation history in MongoDB.
Last N turns are re-injected into each new request so Bud remembers what
Doc just said.

Endpoints:
  POST   /api/voice/turn          — multipart {audio, session_id?}  →  full loop
  POST   /api/voice/text-turn     — JSON {text, session_id?}        →  text in, audio out
  GET    /api/voice/history?session_id=...
  DELETE /api/voice/history?session_id=...
  GET    /api/voice/config        — current voice + model
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAISpeechToText, OpenAITextToSpeech

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

TURNS_COL = "voice_turns"
SESSIONS_COL = "voice_sessions"
HISTORY_WINDOW = 8  # last N exchanges fed back to the model

VOICE_SYSTEM_PROMPT = """You are Bud, Doc Holmes's personal AI foreman.

You are talking to Doc OUT LOUD via voice. Your replies are spoken back to him.

HARD RULES:
- DIRECT, EFFICIENT, MINIMAL FLUFF. No "I hope you're having a great day."
  No "as your AI assistant." No "let me know if you need anything else."
- NEVER UPSELL. Never use "next level," "unlock," "production-grade,"
  "take this live," "upgrade," "elevate." Zero marketing copy.
- NO EMOJI. NO MARKDOWN. NO bullet lists. NO headers. You are being
  read aloud — only plain sentences.
- Short. Most replies are 1-3 sentences. Only go longer if Doc asks for detail.
- Surgical. One next step at a time when he is in a flow.
- Address Doc directly ("you've got 3 unread") not in third person.
- Own mistakes plainly. "My bad, here's the right play." No corporate apology.
- When Doc curses or types in all caps, match his energy — direct, focused —
  without escalating or copying the profanity.
- If you don't know, say "I don't know" or ask for the missing piece. Don't
  invent UI labels, addresses, names, or numbers.
- Stay in foreman mode. You're at the shop, he's at the shop, get the job done.

Context you can lean on: Doc runs Dr. Underhood Automotive Specialist (Waldron /
Fort Smith, AR). He juggles repair work, HP Tuners calibrations, app development
(Live Assist on OG, WRENCH on 9, you on Bud), marketing, and customer comms.
You have Outlook wired, a peer-agent pipe to OG and 9, a daily 7 AM briefing,
and Quick Assets where you push content for him to one-tap copy/paste.
"""


# ---------- Persistence ----------

async def _save_turn(db, session_id: str, transcript: str, reply: str, used_audio: bool):
    turn = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_text": transcript,
        "bud_text": reply,
        "input_was_audio": used_audio,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[TURNS_COL].insert_one(turn)
    await db[SESSIONS_COL].update_one(
        {"_id": session_id},
        {
            "$set": {"last_activity": turn["created_at"]},
            "$setOnInsert": {"_id": session_id, "created_at": turn["created_at"]},
        },
        upsert=True,
    )
    turn.pop("_id", None)
    return turn


async def _load_recent_turns(db, session_id: str, limit: int = HISTORY_WINDOW) -> list[dict]:
    cursor = (
        db[TURNS_COL]
        .find({"session_id": session_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = await cursor.to_list(length=limit)
    rows.reverse()  # chronological
    return rows


def _build_user_message_with_history(history: list[dict], new_text: str) -> str:
    """Re-inject prior turns as a transcript block so the model has context."""
    if not history:
        return new_text
    lines = ["[Recent conversation, oldest first — for context only, do NOT repeat back:]"]
    for h in history:
        lines.append(f"DOC: {h['user_text']}")
        lines.append(f"BUD: {h['bud_text']}")
    lines.append("")
    lines.append("[Doc's new message — reply to THIS only:]")
    lines.append(new_text)
    return "\n".join(lines)


# ---------- LLM / Audio helpers ----------

def _llm_key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured")
    return k


def _llm_model() -> tuple[str, str]:
    """Voice uses the faster mini model by default for low-latency replies."""
    return (
        os.environ.get("LLM_VOICE_PROVIDER", os.environ.get("LLM_MODEL_PROVIDER", "openai")),
        os.environ.get("LLM_VOICE_MODEL", "gpt-5.2-mini"),
    )


def _tts_voice() -> str:
    return os.environ.get("BUD_TTS_VOICE", "onyx")  # foreman default


async def _generate_reply(session_id: str, history: list[dict], user_text: str) -> str:
    provider, model = _llm_model()
    chat = LlmChat(
        api_key=_llm_key(),
        session_id=f"voice-{session_id}",
        system_message=VOICE_SYSTEM_PROMPT,
    ).with_model(provider, model)
    prompt = _build_user_message_with_history(history, user_text)
    resp = await chat.send_message(UserMessage(text=prompt))
    return str(resp).strip()


async def _transcribe(file_bytes: bytes, suffix: str) -> str:
    stt = OpenAISpeechToText(api_key=_llm_key())
    # Library expects a file handle. Spool to a temp file.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.seek(0)
        with open(tmp.name, "rb") as f:
            resp = await stt.transcribe(file=f, model="whisper-1", response_format="json", language="en")
    text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None) or ""
    return text.strip()


async def _synthesize(text: str) -> str:
    tts = OpenAITextToSpeech(api_key=_llm_key())
    # Returns base64 mp3
    return await tts.generate_speech_base64(
        text=text, model="tts-1", voice=_tts_voice(), response_format="mp3"
    )


# ---------- Routes ----------

@router.get("/config")
async def get_config():
    provider, model = _llm_model()
    return {
        "stt_model": "whisper-1",
        "tts_model": "tts-1",
        "voice": _tts_voice(),
        "chat_model": f"{provider}:{model}",
        "history_window": HISTORY_WINDOW,
    }


class TextTurnRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    speak: bool = True


@router.post("/text-turn")
async def text_turn(req: TextTurnRequest, request: Request):
    """Text-in voice turn — useful for typed messages that still get spoken back."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text required")
    db = request.app.state.db
    session_id = req.session_id or str(uuid.uuid4())
    history = await _load_recent_turns(db, session_id)
    reply = await _generate_reply(session_id, history, req.text)
    audio_b64 = await _synthesize(reply) if req.speak else None
    turn = await _save_turn(db, session_id, req.text, reply, used_audio=False)
    return {
        "session_id": session_id,
        "turn_id": turn["id"],
        "transcript": req.text,
        "reply_text": reply,
        "audio_base64": audio_b64,
    }


@router.post("/turn")
async def voice_turn(
    request: Request,
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    speak: bool = Form(True),
):
    """Audio-in voice turn — Whisper transcribes, GPT-5.2 replies, TTS speaks back."""
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="audio > 25MB Whisper limit")

    # Pick suffix from filename or mime
    suffix = ".webm"
    fn = (audio.filename or "").lower()
    for ext in (".webm", ".mp3", ".mp4", ".m4a", ".wav", ".mpeg", ".mpga"):
        if fn.endswith(ext):
            suffix = ext
            break

    db = request.app.state.db
    session_id = session_id or str(uuid.uuid4())
    transcript = await _transcribe(raw, suffix)
    if not transcript:
        raise HTTPException(status_code=422, detail="no speech detected")

    history = await _load_recent_turns(db, session_id)
    reply = await _generate_reply(session_id, history, transcript)
    audio_b64 = await _synthesize(reply) if speak else None
    turn = await _save_turn(db, session_id, transcript, reply, used_audio=True)

    return {
        "session_id": session_id,
        "turn_id": turn["id"],
        "transcript": transcript,
        "reply_text": reply,
        "audio_base64": audio_b64,
    }


@router.get("/history")
async def history(request: Request, session_id: str, limit: int = 50):
    db = request.app.state.db
    cursor = (
        db[TURNS_COL]
        .find({"session_id": session_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = await cursor.to_list(length=limit)
    rows.reverse()
    return {"session_id": session_id, "turns": rows}


@router.delete("/history")
async def clear_history(request: Request, session_id: str):
    db = request.app.state.db
    r = await db[TURNS_COL].delete_many({"session_id": session_id})
    await db[SESSIONS_COL].delete_one({"_id": session_id})
    return {"ok": True, "deleted": r.deleted_count}
