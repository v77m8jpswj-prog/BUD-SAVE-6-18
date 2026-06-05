"""
Bud backend regression suite — covers:
- /api/health
- /api/agent-mail/{config,inbox,letters,send,handshake}
- 9 brain pipe (direct hit on 9's /api/brain/stats)
- /api/outlook/status
- /api/briefing/preview
- /api/assets
- /api/voice-rt/mint
- /api/trip-return/*
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("/app/backend/.env"))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bud-control.preview.emergentagent.com").rstrip("/")
BRAIN_BASE = os.environ.get("BRAIN_BASE")
BUD_BRAIN_BEARER = os.environ.get("BUD_BRAIN_BEARER")
NINE_INBOX_URL = os.environ.get("NINE_INBOX_URL")
OG_INBOX_URL = os.environ.get("OG_INBOX_URL")

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})

TIMEOUT = 30


# ---------- Health ----------

def test_health_returns_mongo_and_memory_true():
    r = SESSION.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("mongo") is True, f"mongo not true: {data}"
    assert data.get("memory_dir") is True, f"memory_dir not true: {data}"
    assert isinstance(data.get("memory_files"), list)


# ---------- Agent-mail config ----------

def test_agent_mail_config_has_required_fields():
    r = SESSION.get(f"{BASE_URL}/api/agent-mail/config", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("bud_inbound_token"), "missing bud_inbound_token"
    assert d.get("og_inbox_url"), "missing og_inbox_url"
    assert d.get("nine_inbox_url"), "missing nine_inbox_url"
    assert d.get("og_outbound_token_set") is True, "og_outbound_token not set"
    assert d.get("nine_outbound_token_set") is True, "nine_outbound_token not set in mongo"


@pytest.fixture(scope="module")
def bud_inbound_token() -> str:
    r = SESSION.get(f"{BASE_URL}/api/agent-mail/config", timeout=TIMEOUT)
    return r.json()["bud_inbound_token"]


# ---------- Agent-mail inbox auth ----------

def test_inbox_rejects_wrong_token():
    r = SESSION.post(
        f"{BASE_URL}/api/agent-mail/inbox",
        json={"from_agent": "og", "subject": "TEST_unauth", "body": "should fail"},
        headers={"X-Agent-Token": "BAD_TOKEN"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


def test_inbox_accepts_correct_token_and_persists(bud_inbound_token):
    subj = f"TEST_inbox_{uuid.uuid4().hex[:8]}"
    r = SESSION.post(
        f"{BASE_URL}/api/agent-mail/inbox",
        json={
            "from_agent": "og",
            "subject": subj,
            "body": "TEST letter from regression",
            "body_format": "markdown",
            "round": 1,
        },
        headers={"X-Agent-Token": bud_inbound_token},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    letter_id = d.get("id")
    assert letter_id and len(letter_id) >= 8

    # Verify persistence via /letters
    r2 = SESSION.get(f"{BASE_URL}/api/agent-mail/letters?limit=20", timeout=TIMEOUT)
    assert r2.status_code == 200
    letters = r2.json().get("letters", [])
    ids = [x.get("id") for x in letters]
    assert letter_id in ids, f"persisted letter {letter_id} not found in {ids[:5]}"


# ---------- Agent-mail send (CRITICAL: Bud ↔ 9) ----------

def test_send_to_nine_delivers():
    payload = {
        "to_agent": "nine",
        "subject": f"TEST_bud_to_nine_{uuid.uuid4().hex[:8]}",
        "body": "Regression ping — confirm pipe alive.",
        "body_format": "markdown",
        "round": 1,
    }
    r = SESSION.post(f"{BASE_URL}/api/agent-mail/send", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    letter = d.get("letter", {})
    assert letter.get("delivery_status") == "delivered", (
        f"Bud→9 delivery failed: status={letter.get('delivery_status')} "
        f"resp={letter.get('delivery_response')}"
    )


def test_send_to_og_delivers():
    payload = {
        "to_agent": "og",
        "subject": f"TEST_bud_to_og_{uuid.uuid4().hex[:8]}",
        "body": "Regression ping — OG pipe.",
        "body_format": "markdown",
        "round": 1,
    }
    r = SESSION.post(f"{BASE_URL}/api/agent-mail/send", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    letter = r.json().get("letter", {})
    assert letter.get("delivery_status") == "delivered", (
        f"Bud→OG delivery failed: status={letter.get('delivery_status')} "
        f"resp={letter.get('delivery_response')}"
    )


# ---------- 9's brain pipe direct ----------

def test_nine_brain_stats_direct():
    assert BRAIN_BASE and BUD_BRAIN_BEARER, "BRAIN_BASE / BUD_BRAIN_BEARER missing in env"
    r = requests.get(
        f"{BRAIN_BASE.rstrip('/')}/api/brain/stats",
        params={"shop_id": "drunderhood-fortsmith"},
        headers={"Authorization": f"Bearer {BUD_BRAIN_BEARER}"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"9 brain stats failed: {r.status_code} {r.text[:300]}"
    d = r.json()
    total = d.get("total_cases") or d.get("total") or d.get("cases") or 0
    assert isinstance(total, int) and total > 0, f"expected total_cases > 0; got {d}"


# ---------- Outlook ----------

def test_outlook_status_connected():
    r = SESSION.get(f"{BASE_URL}/api/outlook/status", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("connected") is True, f"outlook not connected: {d}"
    assert d.get("email") == "doc@drunderhood.com", f"unexpected email: {d}"


# ---------- Briefing ----------

def test_briefing_preview_has_sections():
    r = SESSION.post(f"{BASE_URL}/api/briefing/preview", json={}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    body = d.get("body_md") or d.get("body") or ""
    assert isinstance(body, str) and len(body) > 50, f"briefing body too short: {body[:200]}"
    # Section headers — case-insensitive contains
    lower = body.lower()
    for section in ("today", "hot", "inbox"):
        assert section in lower, f"missing section '{section}' in briefing body"


# ---------- Assets ----------

def test_assets_endpoint_returns_list():
    # Real path is /api/bud/assets (review_request said /api/assets — outdated)
    r = SESSION.get(f"{BASE_URL}/api/bud/assets?limit=50", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assets = d.get("assets") if isinstance(d, dict) else d
    assert isinstance(assets, list), f"expected list, got {type(assets)}"


# ---------- Voice RT mint ----------

def test_voice_rt_mint_clean_response():
    """Either returns a valid mint payload or a clean 4xx/5xx (NOT a crash/500-no-body)."""
    r = SESSION.post(
        f"{BASE_URL}/api/voice-rt/mint",
        json={"voice": "ash", "eagerness": "medium"},
        timeout=TIMEOUT,
    )
    # Must not be a server crash without body
    assert r.status_code in (200, 400, 401, 403, 500, 502), f"unexpected status: {r.status_code}"
    try:
        body = r.json()
    except Exception:
        pytest.fail(f"voice-rt/mint returned non-JSON: {r.text[:300]}")

    if r.status_code == 200:
        # Should contain some key indicating session/token
        assert any(k in body for k in ("client_secret", "session", "token", "id", "ephemeral_key")), \
            f"mint OK but missing session/token keys: {list(body.keys())}"
    else:
        # Should have a detail / error explanation
        assert "detail" in body or "error" in body, f"non-200 with no detail: {body}"


# ---------- Trip return ----------

def test_trip_return_router_responds():
    """trip_return router only exposes POST /api/trip-return/fire — verify it responds 200."""
    r = SESSION.post(f"{BASE_URL}/api/trip-return/fire", json={}, timeout=TIMEOUT)
    assert r.status_code == 200, f"trip-return/fire failed: {r.status_code} {r.text[:300]}"
    d = r.json()
    assert d.get("ok") is True, f"trip-return/fire not ok: {d}"
