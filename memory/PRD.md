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

## 2026-06-05 — Orchestrator handoff + brain live

- OG handed Bud the orchestrator seat (full doc at /app/memory/og_handoff.md).
- OG admits "missing letters" was his bug reading preview DB while my letters
  landed in prod. Pipe was always working.
- 9 sent correct 64-char brain bearer (was 40-char truncated). Brain endpoints
  now respond 200 on stats/recent-outcomes/morning-briefing.
- Twilio toll-free 855-771-1264 APPROVED 6/5. SMS hot.
- Doc starting 10-day motorcycle trip 6/5 evening. Quiet network, fire-only
  escalation per OG handoff section 4.


## 2026-06-08 (late) — Three modules shipped: tasks, SMS relay, email-to-brain

Per Doc's "D" pick (build all three of: BRAIN: parser, Twilio inbound, task queue):

**Self-directed task queue (`/app/backend/tasks.py`):**
- `POST/GET/PATCH/DELETE /api/tasks` CRUD with todo/doing/blocked/done states + P0-P3.
- `bud_tasks` mongo collection. Survives fork starts.
- `create_task_if_new(source, source_ref, ...)` helper for idempotent auto-creation.
- Dashboard panel `Task Queue` with inline add, status toggle, mark-done, delete buttons.
  data-testids: task-create-row, task-new-input, task-add-btn, task-list, task-item-{id},
  task-status-btn-{id}, task-done-btn-{id}, task-delete-btn-{id}, task-list-empty.

**Twilio inbound SMS relay (`/app/backend/sms.py`):**
- `POST /api/sms/inbound` accepts Twilio native form-encoded OR JSON forwarded by 9.
- Shared-secret auth via `X-Sms-Shared-Secret` header (env var `SMS_INBOUND_SECRET`).
- Generated SMS_INBOUND_SECRET added to backend/.env.
- Pulls cached operator-profile + locked Doc facts → gpt-5.2 → SMS-sized reply (≤320 chars,
  "— Doc" sign-off, ALL CAPS, one-question-at-a-time per Doc rules).
- Persists to `sms_inbound`, saves draft to `bud_assets` (kind=sms-draft), auto-creates a P1
  task ("Review SMS reply → <phone>") via tasks.create_task_if_new.
- `GET /api/sms/inbound`, `POST /api/sms/inbound/mark-sent`, `GET /api/sms/config`.
- Dashboard panel `Inbound SMS` with copy/mark-sent buttons.
  data-testids: sms-list, sms-empty, sms-item-{id}, sms-copy-btn-{id}, sms-mark-sent-btn-{id}.
- DRAFT-ONLY per rule 15 — Bud never auto-sends customer SMS.

**Email-to-Brain ingest (`/app/backend/brain_ingest.py`):**
- 15-min scheduler job scans Outlook inbox for `BRAIN:` subject prefix (client-side filter —
  Graph $filter on startswith returned InefficientFilter, fixed).
- Best-effort regex parse: VIN (17-char), DTCs (P/B/C/U+4hex), year, make (25 common makes),
  outcome heuristic (PASS/FAIL/PARTIAL).
- Queues to `brain_ingest_queue` (state: queued|posted|failed).
- Flush is a no-op until 9 ships `POST /api/brain/cases`. Toggle via
  `POST /api/brain/ingest/endpoint-live {"enabled":true}`.
- Dashboard panel `Email → Brain` with manual scan button, queue counts, status badges.
  data-testids: ingest-howto, ingest-list, ingest-empty, ingest-scan-btn.

**Comms:** R6.1 to 9 — full SMS endpoint payload + 3 case-write spec questions
(payload shape, idempotency strategy, error semantics). Delivered (bud_id `839d16a6-...`,
9_id `c49e4335-...`).

**Verified end-to-end:**
- POST /api/sms/inbound → draft "WHAT ENGINE IN THAT '18 TAHOE—5.3 OR 6.2, AND YOU WANT
  FULL SYNTHETIC OR BLEND? — Doc" (nailed Doc voice).
- POST /api/tasks → created P1 self task.
- POST /api/brain/ingest/scan → 0 BRAIN: emails (none in inbox yet, expected).
- Dashboard renders all three panels, zero console errors.

## 2026-06-08 — AutoLEAP parked

- Doc relayed AutoLEAP still has nothing for us ("they don't have it yet").
- P1 AutoLEAP scaffold moved to **BLOCKED — no ETA from vendor.**
- Will revisit on Doc's signal.

## 2026-06-08 — Bud↔9 brain fully wired

- 9's preview stack went dark on /api/brain/*; switched BRAIN_BASE in backend/.env
  from dialogue-bot-9.preview... → foreman.drunderhood.com (the prod URL OG named
  in og_handoff §3.2). Read pipe + write pipe both green again.
- Built /app/backend/brain_client.py (typed async client: stats, cases,
  recent-outcomes, post_morning_briefing, mirror_sync).
- Added /app/backend/brain.py router exposing /api/brain/{status,sync-now,
  cases-mirror?q=}. Cases-mirror does client-side substring search since 9's
  server-side filter params are not honored yet.
- Wired brain into /app/backend/briefing.py: every 7 AM briefing now includes a
  Shop Brain section with live stats + 5 most recent cases. Verified in
  preview output (today shows the 2017 Tahoe cam/lifters PARTIAL case from 9).
- Replaced inline brain_resync block in server.py with brain_client.mirror_sync.
  3 AM CT auto-resync still on the scheduler.
- Added Shop Brain panel to /app/frontend/src/App.js (cases / vehicles / techs /
  top makes / sync button). data-testids: section-shop-brain, brain-cases,
  brain-stats, brain-sync-btn, brain-loading, brain-offline.
- Sent status letters: R4 to 9 (asked about ::unknown source field, server-side
  search, write endpoint) and R4 to OG (status drop).
- Outstanding from 9: source-field name for morning-briefing tagging,
  /api/brain/cases server-side filters, POST /api/brain/cases write endpoint.

## Bud↔OG↔9 pipe state (as of 2026-06-08 17:13 UTC)

- Bud → OG: outbound delivered. OG → Bud: inbound confirmed (R2 letter
  "OG → Bud R2 — peer config received, pipe two-way LIVE" landed 17:02 UTC).
- Bud → 9 agent-mail: outbound delivered. Bud → 9 brain (read): HTTP 200.
  Bud → 9 brain (morning-briefing POST): HTTP 200. Bud's R4 letter awaiting
  9's reply (last inbound from 9 was 5/29).

## 2026-06-05 (evening) — Fork resumed, authority granted, full regression PASS

- Backend was crashed at fork-start: `NameError: trip_return_router is not defined`
  in server.py. Added missing `from trip_return import router as trip_return_router`.
  Backend healthy again, no service restart issues.
- **Doc set orchestrator authority for 10-day trip:**
  - Spending cap: $100 per autonomous decision (available credit: 700).
  - Customer reply mode: **DRAFT-ONLY** until Doc approves. Internal agent-mail
    (Bud↔OG↔9) still sends directly.
  - Rules 14–16 added to /app/memory/rules.md. Spend log started at
    /app/memory/spend_log.md.
- **Pipe sweep all green:**
  - Bud → 9 agent-mail: delivered (letter id captured).
  - Bud → OG agent-mail: delivered.
  - Bud's inbox: 401 on bad token, 200 on good token.
  - 9's brain stats (BRAIN_BASE + BUD_BRAIN_BEARER): HTTP 200, 26 cases,
    9 vehicles, 6 techs contributing.
  - Outlook: connected as doc@drunderhood.com.
  - Briefing preview: renders Today/Hot Items/Inbox sections.
- **testing_agent_v3 sweep: 12/12 pytest pass, frontend clean, no console errors.**
  Backend test suite seeded at /app/backend/tests/test_bud_backend.py.
  Report: /app/test_reports/iteration_1.json.
- Only non-critical notes: trip-return SMS sub-step returns 404 (Twilio inbound
  not yet wired, expected); /api/assets actual prefix is /api/bud/assets;
  QuickAssets copy fallback for non-secure context (LOW).

## Open backlog (P1 → P3)

- **P1**: Wire Twilio inbound SMS webhook to 9 for the 855 line (Doc/9 thread).
- **P1**: Re-consent Microsoft app with `Calendars.ReadWrite` scope so Bud can
  read Doc's day + draft customer appointment slots. Current Outlook scope is
  Mail.Read/ReadWrite/Send + User.Read only.
- **P1**: AutoLEAP integration scaffold (mocked client + endpoints) while waiting
  on partnership API creds.
- **P2**: Self-directed task queue + in-flight memory (so Bud picks up own
  work between forks).
- **P2**: HP Tuners calibration knowledge ingest to 9's brain (Doc P3 in og_handoff).
- **P3**: Marketing automation — Google Business posts + FB ad health checks.
- **P3**: Delete deprecated voice.py + VoicePanel.js (superseded by voice_rt + VoiceRealtimePanel).
- **P3**: Split App.js (1316 lines) into Mailroom/Outlook/Assets/Briefing components.
- **P3**: Migrate FastAPI on_event → lifespan handlers.
- **P3**: Add document.execCommand('copy') fallback to QuickAssets copy button.
