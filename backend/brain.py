"""Bud — Brain dashboard routes.

Exposes:
  GET  /api/brain/status         live stats from 9 + local mirror state
  POST /api/brain/sync-now       on-demand mirror sync (admin button)
  GET  /api/brain/cases-mirror   local-mirrored cases with optional text search
                                 (9's server-side filter isn't honored — we
                                  search the mirror client-side)
"""
from __future__ import annotations

import logging
import os
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
    db = request.app.state.db
    out: dict = {"shop_id": SHOP}
    try:
        out["live"] = await brain_client.stats(SHOP)
        out["connected"] = True
    except Exception as e:
        out["connected"] = False
        out["error"] = str(e)
    mirror = await db["brain_mirror_stats"].find_one({"shop_id": SHOP}, {"_id": 0})
    out["mirror"] = mirror or None
    out["mirror_cases_count"] = await db["brain_mirror_cases"].count_documents({"shop_id": SHOP})
    out["mirror_outcomes_count"] = await db["brain_mirror_outcomes"].count_documents({"shop_id": SHOP})
    return out


@router.post("/sync-now")
async def brain_sync_now(request: Request):
    db = request.app.state.db
    try:
        return await brain_client.mirror_sync(db, SHOP)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operator-profile")
async def operator_profile_proxy(request: Request, refresh: bool = False):
    """Cached pass-through to 9's operator-profile. Cached doc lives in mongo so
    Bud can build persona prompts even if 9 is briefly unreachable."""
    db = request.app.state.db
    if not refresh:
        cached = await db["brain_operator_profile"].find_one({"shop_id": SHOP}, {"_id": 0})
        if cached:
            return {"source": "cache", "profile": cached}
    try:
        profile = await brain_client.operator_profile(SHOP)
    except Exception as e:
        cached = await db["brain_operator_profile"].find_one({"shop_id": SHOP}, {"_id": 0})
        if cached:
            return {"source": "cache_after_error", "error": str(e), "profile": cached}
        raise HTTPException(status_code=502, detail=f"operator-profile fetch failed: {e}")
    profile["shop_id"] = SHOP
    profile["cached_at"] = profile.get("generated_at")
    await db["brain_operator_profile"].update_one(
        {"shop_id": SHOP}, {"$set": profile}, upsert=True
    )
    return {"source": "live", "profile": profile}


class AskRequest(BaseModel):
    symptom: str
    vehicle: Optional[dict] = None


class DraftEstimateRequest(BaseModel):
    match: dict  # the full match object from /api/brain/ask
    customer_name: Optional[str] = None
    channel: str = "email"  # "email" | "sms" — drives length + format


@router.post("/ask")
async def ask_brain(request: Request, body: AskRequest):
    """Forward a diagnostic question to 9's case-lookup brain. Returns 9's
    structured response (similar past cases + suggested actions)."""
    try:
        return await brain_client.ask(body.symptom, body.vehicle, SHOP)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"brain ask failed: {e}")


@router.post("/draft-estimate")
async def draft_estimate(request: Request, body: DraftEstimateRequest):
    """Turn a brain match into a customer-facing estimate paragraph in Doc's
    voice, save it to Quick Assets, return the draft text. DRAFT-ONLY — never
    sent to a customer until Doc copy+pastes it."""
    db = request.app.state.db
    m = body.match or {}

    # Pull Doc persona overlay
    overlay = await db["brain_operator_profile"].find_one(
        {"shop_id": SHOP}, {"_id": 0}
    )
    style = (overlay or {}).get("operator_style", "").strip()
    facts = (overlay or {}).get("locked_memory_facts", []) or []
    fact_lines = "\n".join(f"- {str(f)}" for f in facts[:15])

    channel = (body.channel or "email").lower()
    is_sms = channel == "sms"
    length_rule = "Keep it SMS-short: 280 chars max." if is_sms else "Two to four short paragraphs."
    salutation = "" if is_sms else (f"Open with: 'Hey {body.customer_name},' " if body.customer_name else "Open with 'Hey,' ")

    case_blob = (
        f"Case match id: {m.get('case_id') or 'n/a'}\n"
        f"Similarity: {round((m.get('similarity') or 0) * 100)}%\n"
        f"Vehicle: {m.get('vehicle_summary') or ''}\n"
        f"Symptom we've seen before: {m.get('symptom') or ''}\n"
        f"Root cause: {m.get('root_cause') or ''}\n"
        f"Repair we did last time: {m.get('repair_summary') or ''}\n"
    )

    system = (
        "You are Bud, drafting a CUSTOMER-FACING estimate as Doc Holmes "
        "(Dr. Underhood Automotive Specialist, Fort Smith AR). The customer is a layperson — "
        "not a mechanic. Speak plainly and respectfully without being condescending. "
        "ABSOLUTE TONE CONTRACT (from 9/WRENCH, locked): NO markdown bolding (no '**'), "
        "NO emoji, NO upsell phrases like 'next level' or 'production-grade' or 'unlock', "
        "NO fluff like 'Hope you're well' or 'Let me know if you have any questions.' "
        "Lead with the diagnosis in plain English. State the repair plan. Quote the price "
        "as an out-the-door estimate, with a one-line caveat that it's a working estimate "
        "and the final number is confirmed once the vehicle is on the lift. "
        f"{length_rule} {salutation}"
        "Sign off with 'Doc' on its own line. No dash, no signature block. "
        "Use complete sentences. Plain prose. Do not list parts or use bullet points unless "
        "explaining a multi-step repair.\n\n"
        f"DOC OPERATOR STYLE: {style}\n\n"
        f"LOCKED DOC FACTS:\n{fact_lines}"
    )

    user = f"Draft Doc's customer-facing estimate based on this case match:\n\n{case_blob}"

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import uuid as _uuid
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise HTTPException(500, "EMERGENT_LLM_KEY missing")
        chat = (
            LlmChat(api_key=api_key, session_id=f"est-{_uuid.uuid4().hex[:8]}", system_message=system)
            .with_model("openai", "gpt-5.2")
        )
        text = (await chat.send_message(UserMessage(text=user))).strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"draft generation failed: {e}")

    # Save to Quick Assets
    asset = {
        "id": f"est-{m.get('case_id') or _uuid.uuid4().hex[:8]}",
        "title": f"Estimate draft — {m.get('vehicle_summary') or 'unknown vehicle'}",
        "content": text,
        "kind": "customer-estimate",
        "note": f"Generated from brain match {m.get('case_id')} at {datetime.now(timezone.utc).isoformat()}. DRAFT-ONLY — review before sending.",
        "archived": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Use upsert so re-runs from the same match don't pile up
    await db["bud_assets"].update_one({"id": asset["id"]}, {"$set": asset}, upsert=True)

    return {
        "ok": True,
        "draft": text,
        "asset_id": asset["id"],
        "channel": channel,
        "case_id": m.get("case_id"),
    }


@router.get("/cases-mirror")
async def cases_mirror(
    request: Request,
    q: Optional[str] = Query(default=None, description="case-insensitive substring search"),
    limit: int = 30,
):
    db = request.app.state.db
    filt: dict = {"shop_id": SHOP}
    if q:
        filt["$or"] = [
            {"symptom": {"$regex": q, "$options": "i"}},
            {"repair_summary": {"$regex": q, "$options": "i"}},
            {"root_cause": {"$regex": q, "$options": "i"}},
            {"vehicle.make": {"$regex": q, "$options": "i"}},
            {"vehicle.model": {"$regex": q, "$options": "i"}},
            {"vehicle.vin": {"$regex": q, "$options": "i"}},
            {"dtc_codes": {"$regex": q, "$options": "i"}},
            {"parts": {"$regex": q, "$options": "i"}},
        ]
    cursor = db["brain_mirror_cases"].find(filt, {"_id": 0}).sort("created_at", -1).limit(limit)
    return {"q": q, "cases": await cursor.to_list(length=limit)}
