"""Bud — Brain dashboard routes (locked-down peer API only).

Exposes:
  GET  /api/brain/status               connection + token check + open-work
  POST /api/brain/sync-now             refresh local open-work mirror
  POST /api/brain/ask                  symptom lookup → ranked closed-case matches
  POST /api/brain/draft-estimate       LLM-draft a customer reply from a match
  GET  /api/brain/peer/ping            proxy to 9's public ping
  GET  /api/brain/peer/whoami          proxy to 9's token check
  GET  /api/brain/peer/open-work       proxy to 9's open-work
  GET  /api/brain/peer/lookup?q=...    proxy to 9's lookup
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

import brain_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brain", tags=["brain"])

SHOP = "drunderhood-fortsmith"


@router.get("/status")
async def brain_status(request: Request):
    """Full brain pipe health check for the dashboard.
    Reports: pipe reachable (ping), token valid (whoami), open-work data.
    """
    db = request.app.state.db
    out: dict = {
        "shop_id": SHOP,
        "mode": "peer-only",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "pipe_ok": False,
        "token_ok": False,
        "connected": False,
        "open_count": 0,
        "open_leads": [],
        "open_leads_preview": [],
        "mirror_cases_count": 0,
        "errors": {},
    }

    try:
        out["mirror_cases_count"] = await db["brain_mirror_cases"].count_documents({})
    except Exception:
        pass

    try:
        p = await brain_client.ping()
        out["pipe_ok"] = bool(p.get("ok"))
        out["brain_name"] = p.get("brain")
    except Exception as e:
        out["errors"]["ping"] = str(e)

    try:
        w = await brain_client.whoami()
        out["token_ok"] = bool(w.get("ok"))
        out["peer"] = w.get("peer")
    except Exception as e:
        out["errors"]["whoami"] = str(e)

    try:
        ow = await brain_client.open_work()
        out["connected"] = True
        out["open_count"] = ow.get("open_count", 0)
        leads = ow.get("open_leads") or []
        out["open_leads"] = leads
        out["open_leads_preview"] = leads[:5]
    except Exception as e:
        out["errors"]["open_work"] = str(e)

    # Legacy compat for older UI that read brain.live.*
    out["live"] = {
        "shop_name": "DR UNDERHOOD",
        "open_count": out["open_count"],
        "last_check": out["checked_at"],
    }
    return out


@router.get("/peer/ping")
async def peer_ping():
    try:
        return await brain_client.ping()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ping failed: {e}")


@router.get("/peer/whoami")
async def peer_whoami():
    try:
        return await brain_client.whoami()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"whoami failed: {e}")


@router.post("/sync-now")
async def brain_sync_now(request: Request):
    db = request.app.state.db
    try:
        return await brain_client.mirror_sync(db, SHOP)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/peer/open-work")
async def peer_open_work():
    try:
        return await brain_client.open_work()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"open-work failed: {e}")


@router.get("/peer/lookup")
async def peer_lookup(q: str = Query(..., min_length=1)):
    try:
        return await brain_client.lookup(q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"lookup failed: {e}")


# ---------- /ask + /draft-estimate (rebuilt on top of peer.lookup) ----------

class VehicleHint(BaseModel):
    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None


class AskRequest(BaseModel):
    symptom: str
    vehicle: Optional[VehicleHint] = None


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with",
    "is", "are", "was", "were", "at", "by", "from", "it", "this", "that",
    "has", "have", "had", "but", "as", "be", "been", "being",
}


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in _STOP}


def _vehicle_summary(v: dict) -> str:
    if not v:
        return ""
    parts = [v.get("year"), v.get("make"), v.get("model")]
    if v.get("engine"):
        parts.append(v["engine"])
    return " ".join(p for p in parts if p).strip()


def _score(symptom_tokens: set[str], case: dict) -> float:
    hay = " ".join([
        case.get("symptom") or "",
        case.get("repair_summary") or "",
        case.get("root_cause") or "",
    ])
    ht = _tokens(hay)
    if not symptom_tokens or not ht:
        return 0.0
    inter = symptom_tokens & ht
    if not inter:
        return 0.0
    # Jaccard-ish but biased toward symptom recall
    return round(len(inter) / max(len(symptom_tokens), 1), 3)


@router.post("/ask")
async def brain_ask(body: AskRequest):
    """Symptom → ranked closed-case matches from 9's lookup."""
    sym = (body.symptom or "").strip()
    if not sym:
        raise HTTPException(status_code=400, detail="symptom required")

    v = body.vehicle.model_dump() if body.vehicle else {}
    # 9's lookup is picky: multi-token queries with year often return 0.
    # Try progressive fallback queries until we get hits.
    queries: list[str] = []
    if v.get("make") and v.get("model"):
        queries.append(f"{v['make']} {v['model']}")
    if v.get("model"):
        queries.append(v["model"])
    if v.get("make"):
        queries.append(v["make"])
    # Last-resort: first meaningful symptom token
    first = next(iter(_tokens(sym)), "")
    if first:
        queries.append(first)
    # De-dupe while preserving order
    seen = set()
    queries = [q for q in queries if not (q in seen or seen.add(q))]
    if not queries:
        queries = [sym[:30]]

    result = {"closed_cases": []}
    q_used = queries[0]
    for q in queries:
        try:
            r = await brain_client.lookup(q)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"lookup failed: {e}")
        if (r.get("closed_cases") or []) or (r.get("leads") or []):
            result = r
            q_used = q
            break
        result = r
        q_used = q

    cases = result.get("closed_cases") or []
    st = _tokens(sym)

    matches = []
    for c in cases:
        sc = _score(st, c)
        matches.append({
            "case_id": c.get("id"),
            "vehicle_summary": _vehicle_summary(c.get("vehicle") or {}),
            "symptom": c.get("symptom"),
            "root_cause": c.get("root_cause"),
            "repair_summary": c.get("repair_summary"),
            "technician_name": c.get("technician_name"),
            "outcome": c.get("outcome"),
            "similarity": sc,
        })
    matches.sort(key=lambda m: m["similarity"], reverse=True)

    return {
        "query": q_used,
        "symptom": sym,
        "matches": matches[:8],
        "counts": {"considered": len(cases), "returned": min(len(matches), 8)},
        "is_known": result.get("is_known", False),
    }


class DraftEstimateRequest(BaseModel):
    match: dict
    customer_name: Optional[str] = None
    channel: str = "email"  # email | sms


def _draft_system() -> str:
    return (
        "You are Bud drafting a customer-facing message in Doc Holmes's voice "
        "for Dr. Underhood Automotive Specialist (Fort Smith AR). "
        "TONE: terse, plain prose, no markdown, no emoji, no fluff. "
        "Doc speaks plainly with respect for the customer's time. "
        "HARD RULES: "
        "- NEVER quote a price (we don't have AutoLEAP wired yet). "
        "- NEVER commit to a time or appointment (no shop board access). "
        "- Suggest the customer 'call the shop' or 'reply to schedule a look' instead. "
        "- Reference what we've seen before on similar vehicles when relevant, but do not promise the same diagnosis. "
    )


def _draft_user(match: dict, customer_name: Optional[str], channel: str) -> str:
    veh = match.get("vehicle_summary") or "their vehicle"
    sym = match.get("symptom") or ""
    repair = match.get("repair_summary") or ""
    root = match.get("root_cause") or ""
    name = customer_name or "the customer"
    target_len = "120 words max, with greeting + sign-off" if channel == "email" else "320 chars max, single SMS, no greeting/sign-off"
    return (
        f"Draft a {channel.upper()} to {name} about {veh}. "
        f"Reported symptom: {sym}. "
        f"What we've fixed on similar trucks: {repair} (root cause: {root or 'see history'}). "
        f"Goal: tell them we've seen this pattern, invite them to bring it in for diagnosis. "
        f"NO PRICE. NO APPOINTMENT TIME. Length: {target_len}."
    )


@router.post("/draft-estimate")
async def draft_estimate(body: DraftEstimateRequest, request: Request):
    db = request.app.state.db
    channel = body.channel if body.channel in ("email", "sms") else "email"

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(500, f"LLM library unavailable: {e}")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing")

    session_id = f"draft_{uuid.uuid4().hex[:12]}"
    try:
        chat = (
            LlmChat(api_key=api_key, session_id=session_id, system_message=_draft_system())
            .with_model("openai", "gpt-5.2")
        )
        reply = await chat.send_message(UserMessage(text=_draft_user(body.match, body.customer_name, channel)))
    except Exception as e:
        logger.exception("draft-estimate LLM failed: %s", e)
        raise HTTPException(502, f"draft failed: {e}")

    draft = (reply or "").strip()
    if not draft:
        raise HTTPException(502, "empty draft")

    # Save to bud_assets
    veh = body.match.get("vehicle_summary") or "vehicle"
    title = f"Draft {channel.upper()} · {veh}"
    if body.customer_name:
        title += f" · {body.customer_name}"
    asset = {
        "id": str(uuid.uuid4()),
        "title": title[:120],
        "content": draft,
        "kind": "email" if channel == "email" else "snippet",
        "related_url": None,
        "note": f"draft-estimate · case={body.match.get('case_id','-')} · channel={channel}",
        "archived": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db["bud_assets"].insert_one(asset)

    return {"draft": draft, "asset_id": asset["id"], "channel": channel}
