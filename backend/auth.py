"""Bud — Emergent-managed Google Auth.

Single-user-for-now: ALLOWED_EMAILS env (comma-separated) gates first-time
sign-in. Doc's email is the only one in there at deploy. When he markets
later we add more.

Routes:
  POST /api/auth/session   — exchange session_id (from URL hash) for a session_token
  GET  /api/auth/me        — return current user or 401
  POST /api/auth/logout    — clear session + cookie

REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

USERS_COL = "users"
SESSIONS_COL = "user_sessions"
SESSION_TTL_DAYS = 7
EMERGENT_SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


def _allowlist() -> list[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "doc@drunderhood.com")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


async def _resolve_session(db, session_token: Optional[str]) -> Optional[dict]:
    if not session_token:
        return None
    s = await db[SESSIONS_COL].find_one({"session_token": session_token}, {"_id": 0})
    if not s:
        return None
    expires_at = s.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        return None
    user = await db[USERS_COL].find_one({"user_id": s["user_id"]}, {"_id": 0})
    return user


async def require_user(request: Request) -> dict:
    """FastAPI dependency. Returns the current Doc user or raises 401."""
    db = request.app.state.db
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
    user = await _resolve_session(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


class SessionRequest(BaseModel):
    session_id: str


@router.post("/session")
async def exchange_session(payload: SessionRequest, request: Request, response: Response):
    """Frontend posts the session_id from the URL hash here. Backend calls
    Emergent's session-data endpoint, stores the user + session, sets the
    httpOnly cookie."""
    db = request.app.state.db
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(EMERGENT_SESSION_DATA_URL, headers={"X-Session-ID": payload.session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail=f"emergent session lookup failed: {r.status_code}")
    data = r.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="no email returned from emergent auth")

    allowed = _allowlist()
    if email not in allowed:
        raise HTTPException(status_code=403, detail=f"{email} is not on the access list for Bud")

    # upsert user
    now = datetime.now(timezone.utc)
    existing = await db[USERS_COL].find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db[USERS_COL].update_one(
            {"email": email},
            {"$set": {
                "name": data.get("name") or existing.get("name"),
                "picture": data.get("picture") or existing.get("picture"),
                "last_login_at": now,
            }},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db[USERS_COL].insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "created_at": now,
            "last_login_at": now,
        })

    session_token = data.get("session_token") or uuid.uuid4().hex
    expires_at = now + timedelta(days=SESSION_TTL_DAYS)
    await db[SESSIONS_COL].insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": now,
    })

    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )

    user_doc = await db[USERS_COL].find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user_doc, "expires_at": expires_at.isoformat()}


@router.get("/me")
async def me(request: Request):
    db = request.app.state.db
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
    user = await _resolve_session(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


@router.post("/logout")
async def logout(request: Request, response: Response):
    db = request.app.state.db
    token = request.cookies.get("session_token")
    if token:
        await db[SESSIONS_COL].delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ----------------------- middleware -----------------------

# Paths under /api/* that are PUBLIC (don't require Doc session).
# Each entry is matched as a prefix.
PUBLIC_PREFIXES = (
    "/api/health",
    "/api/auth/",
    "/api/agent-mail/inbox",     # 9 / OG → Bud (X-Agent-Token)
    "/api/agent-mail/config",    # used to bootstrap peer config; no secrets in response
    "/api/sms/inbound",          # Twilio / 9 forward (X-Sms-Shared-Secret)
    "/api/outlook/oauth/",       # Microsoft hits the callback
)


async def auth_middleware(request: Request, call_next):
    """Protect every /api/* route except the explicit PUBLIC_PREFIXES.
    Non-/api/* (the React bundle) passes through."""
    path = request.url.path or "/"
    if not path.startswith("/api/"):
        return await call_next(request)
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    db = request.app.state.db
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
    user = await _resolve_session(db, token)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "not authenticated"})
    # stash user on request state for downstream use
    request.state.user = user
    return await call_next(request)
