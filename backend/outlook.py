"""Bud — Microsoft Graph / Outlook OAuth + client.

Single-tenant, single-user app. Token cycle:
  /oauth/start  → builds authorize URL with state, redirects to Microsoft
  /oauth/callback → validates state, exchanges code, stores tokens, /me lookup
  /status       → connected/disconnected + expiry
  /inbox        → recent inbox messages (delegated Mail.Read)
  /draft        → createReply on a message, patch body
  /send/{id}    → release a draft from Sent Items
  /disconnect   → wipe stored tokens

Tokens NEVER appear in logs or response bodies.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/outlook", tags=["outlook"])

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPE = "offline_access Mail.Read Mail.Send Mail.ReadWrite User.Read"
TOKEN_COL = "outlook_tokens"
STATE_COL = "oauth_states"
PRIMARY_KEY = "doc@drunderhood.com"


def _tenant() -> str:
    return os.environ["MS_TENANT_ID"]


def _authorize_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/authorize"


def _token_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/token"


# ---------- Token storage ----------

async def _ensure_state_ttl(db):
    try:
        await db[STATE_COL].create_index("created_at", expireAfterSeconds=600)
    except Exception:
        pass


async def _get_token_doc(db) -> Optional[dict]:
    return await db[TOKEN_COL].find_one({"_id": PRIMARY_KEY})


def _expires_at_str(seconds_from_now: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).isoformat()


def _is_expired(token_doc: dict) -> bool:
    exp = token_doc.get("expires_at")
    if not exp:
        return True
    if isinstance(exp, str):
        try:
            exp_dt = datetime.fromisoformat(exp)
        except Exception:
            return True
    else:
        exp_dt = exp
    return datetime.now(timezone.utc) + timedelta(seconds=60) >= exp_dt


async def _store_token(db, payload: dict, user_info: Optional[dict] = None) -> dict:
    """Persist token. Preserve refresh_token + user_info if not returned."""
    existing = await _get_token_doc(db) or {}
    doc = {
        "_id": PRIMARY_KEY,
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token") or existing.get("refresh_token"),
        "expires_at": _expires_at_str(int(payload.get("expires_in", 3600))),
        "scope": payload.get("scope", SCOPE),
        "token_type": payload.get("token_type", "Bearer"),
        "user_id": (user_info or {}).get("id") or existing.get("user_id"),
        "user_principal_name": (
            (user_info or {}).get("userPrincipalName")
            or (user_info or {}).get("mail")
            or existing.get("user_principal_name")
            or PRIMARY_KEY
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[TOKEN_COL].update_one({"_id": PRIMARY_KEY}, {"$set": doc}, upsert=True)
    return doc


async def _refresh(db, token_doc: dict) -> dict:
    refresh_token = token_doc.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token. Reconnect Outlook.")
    data = {
        "client_id": os.environ["MS_CLIENT_ID"],
        "client_secret": os.environ["MS_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": SCOPE,
    }
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(_token_url(), data=data)
    if r.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail=f"Outlook refresh failed ({r.status_code}). Reconnect.",
        )
    return await _store_token(db, r.json())


async def _access_token(db) -> str:
    doc = await _get_token_doc(db)
    if not doc:
        raise HTTPException(status_code=401, detail="Outlook not connected.")
    if _is_expired(doc):
        doc = await _refresh(db, doc)
    return doc["access_token"]


async def _graph(
    db,
    method: str,
    path: str,
    *,
    params=None,
    json_body=None,
    _retried: bool = False,
) -> httpx.Response:
    token = await _access_token(db)
    headers = {"Authorization": f"Bearer {token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.request(
            method, f"{GRAPH_BASE}{path}", headers=headers, params=params, json=json_body
        )
    if r.status_code == 401 and not _retried:
        existing = await _get_token_doc(db)
        if existing:
            await _refresh(db, existing)
        return await _graph(db, method, path, params=params, json_body=json_body, _retried=True)
    return r


# ---------- Routes ----------

@router.get("/status")
async def status(request: Request):
    db = request.app.state.db
    doc = await _get_token_doc(db)
    if not doc:
        return {"connected": False, "email": None, "expires_at": None}
    return {
        "connected": True,
        "email": doc.get("user_principal_name") or PRIMARY_KEY,
        "expires_at": doc.get("expires_at"),
        "needs_refresh": _is_expired(doc),
        "scope": doc.get("scope"),
    }


@router.post("/disconnect")
async def disconnect(request: Request):
    db = request.app.state.db
    await db[TOKEN_COL].delete_many({"_id": PRIMARY_KEY})
    return {"ok": True}


@router.get("/oauth/start")
async def oauth_start(request: Request):
    db = request.app.state.db
    await _ensure_state_ttl(db)
    state = secrets.token_urlsafe(32)
    await db[STATE_COL].insert_one(
        {"_id": state, "created_at": datetime.now(timezone.utc)}
    )
    params = {
        "client_id": os.environ["MS_CLIENT_ID"],
        "response_type": "code",
        "redirect_uri": os.environ["MS_REDIRECT_URI"],
        "response_mode": "query",
        "scope": SCOPE,
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(url=f"{_authorize_url()}?{urlencode(params)}", status_code=302)


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    db = request.app.state.db
    base = os.environ.get("BUD_BASE_URL", "").rstrip("/")

    def back(status_key: str, msg: str = ""):
        suffix = f"&msg={msg}" if msg else ""
        return RedirectResponse(url=f"{base}/?outlook={status_key}{suffix}", status_code=302)

    if error:
        return back("error", error_description or error)
    if not code or not state:
        return back("error", "missing_code_or_state")

    consumed = await db[STATE_COL].delete_one({"_id": state})
    if consumed.deleted_count != 1:
        return back("error", "invalid_state")

    data = {
        "client_id": os.environ["MS_CLIENT_ID"],
        "client_secret": os.environ["MS_CLIENT_SECRET"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.environ["MS_REDIRECT_URI"],
        "scope": SCOPE,
    }
    async with httpx.AsyncClient(timeout=20.0) as c:
        tok_r = await c.post(_token_url(), data=data)
    if tok_r.status_code != 200:
        return back("error", f"token_exchange_{tok_r.status_code}")

    payload = tok_r.json()
    access_token = payload["access_token"]
    async with httpx.AsyncClient(timeout=20.0) as c:
        me_r = await c.get(
            f"{GRAPH_BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    user_info = me_r.json() if me_r.status_code == 200 else None
    await _store_token(db, payload, user_info)
    return back("connected")


@router.get("/inbox")
async def inbox(request: Request, limit: int = 20):
    db = request.app.state.db
    limit = max(1, min(limit, 100))
    params = {
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,conversationId,webLink",
    }
    r = await _graph(db, "GET", "/me/mailFolders/Inbox/messages", params=params)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"Graph error: {r.text[:300]}")
    data = r.json()
    out = []
    for m in data.get("value", []):
        f = (m.get("from") or {}).get("emailAddress") or {}
        out.append({
            "id": m.get("id"),
            "subject": m.get("subject") or "(no subject)",
            "from_name": f.get("name"),
            "from_email": f.get("address"),
            "received_at": m.get("receivedDateTime"),
            "preview": m.get("bodyPreview") or "",
            "is_read": m.get("isRead"),
            "has_attachments": m.get("hasAttachments"),
            "web_link": m.get("webLink"),
        })
    return {"messages": out, "count": len(out)}


class DraftReplyRequest(BaseModel):
    message_id: str
    body: str


@router.post("/draft")
async def create_draft(req: DraftReplyRequest, request: Request):
    db = request.app.state.db
    r = await _graph(db, "POST", f"/me/messages/{req.message_id}/createReply")
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=f"createReply failed: {r.text[:300]}")
    draft = r.json()
    draft_id = draft["id"]
    r2 = await _graph(
        db,
        "PATCH",
        f"/me/messages/{draft_id}",
        json_body={"body": {"contentType": "Text", "content": req.body}},
    )
    if r2.status_code not in (200, 202):
        raise HTTPException(status_code=r2.status_code, detail=f"patch failed: {r2.text[:300]}")
    return {"draft_id": draft_id}


@router.post("/send/{draft_id}")
async def send_draft(draft_id: str, request: Request):
    db = request.app.state.db
    r = await _graph(db, "POST", f"/me/messages/{draft_id}/send")
    if r.status_code not in (200, 202):
        raise HTTPException(status_code=r.status_code, detail=f"send failed: {r.text[:300]}")
    return {"ok": True, "sent_at": datetime.now(timezone.utc).isoformat()}
