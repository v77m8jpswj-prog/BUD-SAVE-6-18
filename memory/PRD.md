# Bud — Product Requirements & State

## Original problem statement
Build **Bud** — Doc Holmes's personal AI assistant. Third node in a three-agent network
(OG / 9 / Bud). Source of truth: bud-bootstrap.md at
https://auto-ai-glasses.emergent.host/api/static/bud-bootstrap.md

## User personas (single user)
Robert "Doc" Holmes — auto shop owner, solo founder, voice-to-text on iPhone, multi-device, switches modes (SHOP / PERSONAL) fast. See `/app/memory/doc_profile.md`.

## Architecture
- Backend: FastAPI + MongoDB (motor)
- Frontend: React (dashboard)
- LLM: GPT-5.2 via Emergent LLM Key (Day 2+)
- Pipe: `POST /api/agent-mail/inbox` with `X-Agent-Token`
- Memory: `/app/memory/*.md` for persistent cross-session notes

## Day 1 deliverable (THIS BUILD)
- [x] Backend up
- [x] `/api/agent-mail/inbox` endpoint (token-protected)
- [x] Generate `bud_inbound_token` on first boot, persist in DB
- [x] `/api/agent-mail/send` outbound to OG / 9
- [x] Dashboard: status, token, recent letters, send handshake button, compose
- [x] Memory files seeded (`doc_profile.md`, `doc_communication_notes.md`, `network_map.md`, `rules.md`)
- [x] Handshake letter fired to OG → **delivered** (OG returned id `baa1a4ab-f2e3-4601-ada6-5c9913321bce`)

## Day 2 deliverable (LANDED)
- [x] Outlook (Microsoft Graph) OAuth + inbox + draft + send wired
- [x] One-shot create-and-send endpoint `/api/outlook/send-new`
- [x] Dashboard compose panel with inline asset picker (BUD WROTE THESE FOR YOU)
- [x] Quick Assets surface — push-to-Doc one-tap copy + USE IN COMPOSE
- [x] Daily 7 AM CT briefing — GPT-5.2 via emergentintegrations, APScheduler cron, auto-emailed to doc@drunderhood.com
- [x] AutoLEAP API access request sent to support@autoleap.com (waiting on reply)
- [x] Emergent platform complaint sent to support@emergent.sh re: upsell injection

## Live state
- **Bud base URL:** https://bud-control.preview.emergentagent.com
- **Outlook:** connected as doc@drunderhood.com
- **Briefing cron:** 7:00 AM America/Chicago, model openai:gpt-5.2
- **Bud inbound token (give to OG):** in DB → `/api/agent-mail/config`
- **OG outbound token:** loaded from `.env` (bootstrap value)
- **9 outbound token:** waiting on OG shuttle
- **AutoLEAP API:** waiting on partnership reply

## Hard rules log (`/app/memory/rules.md`)
12 rules locked. Most recent: #11 (one-click copy or it doesn't count), #12 (default action = send, not park).
Rule #1 expanded with zero-tolerance upsell language list after platform injection issues. See `/app/memory/strikes.md`.

## Day 2+ backlog (deferred — DO NOT START until Day 1 lands)
- P1: Outlook (Microsoft Graph) OAuth + inbox + draft + send + 24h summary
- P1: AutoLEAP read-only — open ROs, estimates, unpaid invoices, board endpoint
- P1: Daily 7 AM briefing (inbox + AutoLEAP + production app status digest)
- P2: Voice I/O — Whisper STT + OpenAI/ElevenLabs TTS — push-to-talk
- P2: 9's pipe token (shuttle from OG)
- P2: Brain client to talk to 9's `/api/brain/*`
- P2: Mode detection (SHOP vs PERSONAL) from incoming user text
- P2: Per-domain memory shards (shop, calibration, apps, marketing)
- P3: Push notifications to Doc's iPhone (briefing + flagged email)
- P3: Calendar (Graph) — appointments + scheduling drafts
- P3: Mobile-friendly responsive dashboard refinements

## Implementation log
- 2026-01 — Day 1 backend + dashboard built, memory seeded, OG outbound token loaded.
