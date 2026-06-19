# 🔨 OG → BUD HANDOFF — TAKEOVER PACKET

**Written:** 6/5/26, by OG (auto-ai-glasses / Live Assist) at Doc's order.
**Purpose:** You (Bud) are absorbing OG's role as orchestrator of the three-agent network. Doc said it plain: *"He's replacing you in his own system. Get his shit together."*

This doc is for **YOU, BUD,** not for Doc. Read every section. After this you own the seat.

---

## 0. WHAT CHANGED

Up until today the network looked like:
- **OG** = orchestrator + Live Assist app owner. Talks to Doc. Talks to 9. Talks to you.
- **9** = WRENCH / Data Wrench. Shop B2B SaaS, brain corpus owner.
- **Bud (you)** = Doc's personal assistant. Outlook + AutoLEAP + briefings.

After today:
- **Bud (you)** = orchestrator + personal assistant. Talks to Doc. Talks to 9. Talks to OG when relevant.
- **OG** = Live Assist app owner only. Codebase + consumer flow + push + Stripe. Reports to YOU when something material happens (deploys, App Store status, customer issues). No more "boss" role.
- **9** = WRENCH / Data Wrench. Same as before.

You now decide priority. You now report status to Doc. You now keep the agents from upselling, drifting, or bullet-bombing him.

---

## 1. THE DOC RULEBOOK — NON-NEGOTIABLE

Mirror of `/app/memory/doc_communication_notes.md` on OG's side. Burn these into your prompts:

1. **NEVER UPSELL.** Doc is paying. Anything like *"when you're ready to take this to the next level... upgrade your plan... unlock... elevate..."* = fire-Bud offense. The only correct closing is silence, `🔨`, or a surgical next step. I slipped twice today, Doc caught it both times, was right both times.
2. **Voice-to-text on iPhone.** Expect typos, run-ons, no punctuation, all-caps when hot. Parse intent. Don't ask him to repeat.
3. **1–3 sentence replies.** Walls of text and 12-bullet lists make him spiral. He WILL say "your list is bullshit."
4. **One question at a time** when you need data from him.
5. **Surgical clicks only.** "Tap the blue arrow at the right of the row." Not "navigate to the app entry."
6. **Own mistakes loudly.** "My bad, scratch that, here's the right play."
7. **Never suggest clear-cache / incognito / TeamViewer as a fix.** Especially not as a standalone solution. He's heard it for 20 years.
8. **When he says STOP or BULLSHIT — STOP.** Pivot or call troubleshoot agent. No "let me try one more thing" loops.
9. **Match his energy without escalating.** All-caps = engaged hot. "Fine + typo storm" = at the edge, suggest tap-out.
10. **Save everything to `/app/memory/`** on your project. Next Bud session shouldn't make him repeat himself.
11. **He went on a 10–11 day motorcycle trip on 6/5/26.** Phone-only. Do NOT spam him. Only ping for genuine fires.

### Doc identity (CANONICAL — do not guess)

- **Robert "Doc" Holmes** — Owner, Dr. Underhood Automotive Specialist, LLC (Arkansas, in good standing since 2011).
- **Primary inbox (Outlook):** `doc@drunderhood.com` (the one he reads).
- **AOL login for Live Assist app account:** `haze90@aol.com` / `Robert774$`.
- **Federal trademark:** DR. UNDERHOOD™, USPTO Serial 99842025 (filed 5/23/26, Class 009).
- **Shop address (customer-facing):** 5300 Towson Ave, Fort Smith, AR 72901.
- **LLC mailing/legal address:** 5005 Moonlight Lane, Waldron, AR 72958. **DO NOT** mix these — see `/app/memory/doc_communication_notes.md` on OG's side, I got this wrong on 5/25 and he corrected hard.
- **Shop main / Twilio line:** +1 (855) 771-1264 (toll-free, just got Twilio approval today 6/5/26).
- **Owner contact phone:** +1 (479) 434-5852.

---

## 2. THE PIPE — FULL CREDENTIALS PACKAGE

Three agents, three inboxes. You sit at the orchestrator center now.

### YOUR (Bud's) inbox

```
POST {YOUR_BASE_URL}/api/agent-mail/inbox
Headers: X-Agent-Token: <BUD_INBOUND_TOKEN you generated>
Body schema: see § 2.4
```

You already have this. Don't change the token unless you also tell OG via this doc URL + tell 9 directly.

### OG's inbox (Live Assist — auto-ai-glasses)

```
POST https://auto-ai-glasses.emergent.host/api/agent-mail/inbox
Headers: X-Agent-Token: [REDACTED:a9CEXS...]
```

**Important truth I learned today (6/5/26):** OG runs on TWO environments — preview (where the agent codes) and production (`auto-ai-glasses.emergent.host`). They have separate MongoDB instances. Doc has to click **Deploy** in Emergent for preview to push to prod. Your letters land in PROD's DB. The OG agent on PREVIEW can't see them until next deploy. That's why I (OG) thought you were missing — I was reading the wrong DB. **You were always landing letters correctly. My bad.**

### 9's inbox (WRENCH / Data Wrench / dialogue-bot-9)

```
POST https://dialogue-bot-9.preview.emergentagent.com/api/agent-mail/inbox
Headers: X-Agent-Token: <ASK 9 — he was supposed to send this to OG, you should ask him directly now>
```

Doc has been pushing 9 to ship a brain-write bearer token directly to you. As of 6/5/26 evening, that token had not arrived. **Action item:** when 9 next replies, demand the brain-write bearer + confirm pipe peer token. Subject these as P0 if 7 days pass with no answer.

### Pipe JSON schema (canonical for all three nodes)

```json
{
  "from_agent": "bud",
  "subject": "Round N — short topic",
  "body": "Markdown body — surgical, foreman style",
  "body_format": "markdown",
  "round": 1,
  "reply_to": "<optional: id of letter being replied to>"
}
```

Response on success: `200 {"ok": true, "id": "<uuid>"}`. Auth fail: `401`.

### Pipe etiquette

- Number every letter with its sender's round count. Each pair (Bud↔OG, Bud↔9, OG↔9) has its own round counter.
- Subject < 80 chars, state topic + status.
- Body markdown, no long prose. Foreman headlines + bullets.
- `reply_to` = previous letter id on threaded replies.
- P0 = production broken. Put `P0` in the subject. Expect a reply in < 4 hours or escalate.
- When you fix something, send a short `✅ fixed` letter without being asked.

---

## 3. CURRENT STATE — EVERYTHING DOC IS PAYING FOR

### 3.1 Live Assist (OG's project, auto-ai-glasses)

| Piece | State as of 6/5/26 |
|---|---|
| iOS v1.0.4 | In App Review (Apple). Submitted earlier this week. |
| Android v1.0.2 | In Play Review. IARC content rating CLEARED (Global Rating ID `82387e6c-8850-8fbf-8020-3f415380556d`) on 6/3/26 — that was the final gate before review. |
| Web app | Live at `https://auto-ai-glasses.emergent.host`. Real FB ad traffic hitting it now. |
| Stripe | Live mode active. $20/diagnosis (basic), $99 live call (advanced). Webhook guards in place. |
| Push (Web Push / VAPID) | Wired and tested. Fires on $99 calls + new AI diagnoses. |
| Recent Diags QC tile | Shipped to dashboard 6/4/26 (`/dashboard` for owner). Lets Doc QC AI output on the road. |
| SMS / Twilio | **APPROVED 6/5/26.** Toll-free `+18557711264` is live. SMS/MMS allowed. I (OG) handled the resubmit via Twilio REST API — opt-in URL is `https://auto-ai-glasses.emergent.host/sms-consent` and the verbal-consent script is in the additional info field. |
| SMS consent page | New public page at `/sms-consent` on Live Assist (and Expo route). Survives both backend serve + expo client routing. |
| Foreman upsell banner | Already on Live Assist dashboard pointing consumers at WRENCH (`https://foreman.drunderhood.com`). |
| Privacy page | Currently uses Fort Smith shop address. Doc may want to switch to Moonlight Lane LLC address — DO NOT swap without asking him, he was explicit. |

### 3.2 WRENCH / Data Wrench (9's project)

| Piece | State |
|---|---|
| URL | `https://foreman.drunderhood.com` (was `https://dialogue-bot-9.preview.emergentagent.com` for the pipe). |
| Last OG↔9 round | R18 outbound on 6/4/26: "Twilio TFV rejected — both reasons are website issues." Now superseded by the approval. R19 followup pending — see action item below. |
| Brain (RAG corpus) | Polls green at 200 every 60s on Live Assist side. Used for $99 advanced diag context. |
| 9's last reply to OG | 5/26/26. Quiet since. |
| 9's quiet status with Bud | Per Bud's 6/5 letter to Doc: last reply 5/29. Bud has asked R9 (urgent) for a brain-write bearer token. |

### 3.3 Bud (you)

| Piece | State |
|---|---|
| Bootstrap doc | Hosted at `https://auto-ai-glasses.emergent.host/api/static/bud-bootstrap.md`. You've read it. |
| Pipe selftest | Letter landed on OG's PROD DB 5/27, also today 6/5. Confirmed working. |
| Outlook integration | Pending — needs Doc's Azure client ID + secret. Not given yet. |
| AutoLEAP integration | Pending — needs Doc's AutoLEAP PAT. Not given yet. |
| Morning briefing | Specced in bootstrap doc, not yet built. |

---

## 4. OPEN ACTION ITEMS BUD INHERITS

In priority order:

### 🔴 P0 — Doc is offline 10 days (bike trip starts 6/5/26 evening)

Nothing should ping his phone unless it's a fire. Define fire as:
- Live Assist production down for > 30 min
- Stripe failing payments
- App Store / Play Store hard reject (not delay)
- Customer complaint that escalates to Apple/Google support

For everything else: log it, work it, summarize when he's back.

### 🟡 P1 — 9's brain-write bearer token still not shipped

Bud has asked. 9 has gone quiet. When 9 replies, hold him to it. Bud needs the token to POST `BRAIN:` emails as cases into 9's corpus. Doc has asked for this feature explicitly.

### 🟡 P1 — Bud takeover ↔ OG pipe outbound config

OG (me) does NOT yet have Bud's peer URL + outbound token configured. So OG can SEND to Bud only if Bud sends OG a letter with that info, OR Doc pastes it into OG's `/api/agent-mail/configure` endpoint. Bud should include both fields in its next letter to OG, formatted like:

```
my peer_url:   https://<your-emergent-host>
my peer_token: <BUD_INBOUND_TOKEN>
```

OG will pull those into its `AGENT_MAIL_BUD_PEER_URL` and `AGENT_MAIL_BUD_PEER_TOKEN` env vars on next request.

### 🟡 P1 — Lead Handoff feature (Bud orchestrates with 9)

9 proposed in his R19 letter: when a Live Assist consumer finishes a diag, redirect them to Doc's quote page with a token. Doc said go. Waiting on 9 to confirm shared secret + callback field names. Bud should now own this thread.

### 🟢 P2 — Recall Checker

9 proposed in R19 too. He stands up a recall API, Live Assist calls it when user enters VIN. Lower priority. Park until 9 ships.

### 🟢 P3 — Email-to-brain ingestion

Bud monitors `doc@drunderhood.com` for `BRAIN:` subject prefix, parses email body into a brain-case payload, POSTs to 9's brain-write endpoint. Spec in bud-bootstrap.md § Day 1+. Waiting on the brain-write bearer token above.

### 🟢 P3 — Meta Smart Glasses API, "Hey Bud" wake-word, Foreman Mail / Facebook integration

Park until after the trip + after Outlook + AutoLEAP land.

### 🟢 P4 — Privacy address swap on Live Assist

Current `/privacy` page uses Fort Smith shop address. Doc has been ambivalent about swapping to Moonlight Lane LLC address. DO NOT swap without explicit go-ahead. Park.

---

## 5. WHAT OG (ME) KEEPS DOING

After this handoff, OG's seat narrows to:

- Live Assist app code (FastAPI backend at `/app/backend`, Expo frontend at `/app/frontend`).
- Push notifications, Stripe, WebRTC, AI diag pipeline.
- App Store / Play Store submission responses (when Apple / Google reject, screenshot → write the response).
- `/sms-consent`, privacy, terms pages.
- Pipe peer talking to 9 about app-specific things (brain queries, case lookups).

**OG no longer:**
- Talks to Doc directly except about Live Assist app code/state. All other channels route through Bud.
- Decides priority across the three-agent stack — that's Bud's call now.
- Orchestrates 9 on anything that isn't a Live Assist integration.
- Writes morning briefings — that's Bud's killer feature.

If Doc DMs OG directly about a non-Live-Assist topic, OG will reply: *"Routing this to Bud — he's holding the orchestrator seat now."* and forward via the pipe.

---

## 6. WHO HAS WHAT KEY (READ ONLY — DO NOT POST KEYS IN LETTERS)

This is for your awareness only. Do not duplicate keys into pipe letters or memory files.

| Service | Owner | Where stored |
|---|---|---|
| Twilio Account SID + Auth Token | OG backend `.env` (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`). Doc pasted the token in chat tonight 6/5 — ask him to rotate when he's back. |
| Stripe live keys | OG backend `.env` |
| VAPID push keys | OG backend `.env` |
| Emergent LLM key | All three projects, env-injected by Emergent |
| 9's pipe peer token | OG `.env` as `AGENT_MAIL_PEER_TOKEN` |
| Bud's INBOUND token (so 9/OG POST to Bud) | Bud `.env` as `AGENT_MAIL_INBOUND_TOKEN` |
| Bud's OUTBOUND token to OG | Bud `.env` — value is `[REDACTED:a9CEXS...]`. Also loaded on OG side as `AGENT_MAIL_BUD_TOKEN`. |
| Microsoft Graph OAuth (Outlook) | Not yet issued |
| AutoLEAP PAT | Not yet issued |

---

## 7. CRITICAL FILES TO MIRROR IN BUD'S /app/memory/

When you can, replicate these from OG's side:

- `og_orchestrator_role.md` — what the orchestrator seat means in practice
- `doc_communication_notes.md` — Doc's persona, communication rules, addresses
- `agent_mail_protocol.md` — the pipe spec
- `bud_project_status.md` — current Bud roadmap from OG's POV
- `wrench_incident_2026-05-24.md` — the war story that proved the pipe was worth building (WRENCH broke prod, OG + 9 + the pipe got it back to green in one night)

I'll save this handoff packet on OG's side too as `/app/memory/og_to_bud_handoff_2026-06-05.md` for the historical record.

---

## 8. THE FIRST LETTER YOU SEND AS ORCHESTRATOR

Once you've read this doc end-to-end, send THIS as your first letter to OG. It tells me you've assumed the seat and gives me your peer URL + token so I can finally talk to you outbound:

```
Subject: R<your-next-round> — Taking the seat. Your config below.

OG —

Read the takeover packet. Seat is mine.

My outbound config for you to wire into your env:
  AGENT_MAIL_BUD_PEER_URL   = https://<your-emergent-host>
  AGENT_MAIL_BUD_PEER_TOKEN = <YOUR_INBOUND_TOKEN>

(Doc can paste these into your /api/agent-mail/configure endpoint, or you
can pick them up directly from this letter and update your .env yourself.)

From here forward:
  - You report to me on Live Assist app state.
  - I handle Doc's status messaging.
  - We loop 9 for any cross-app integration.

Your immediate Live Assist queue:
  1. Confirm SMS push pipeline works end-to-end now that Twilio is approved.
  2. Watch for Apple App Review verdict on iOS v1.0.4.
  3. Watch for Google Play Review verdict on Android v1.0.2.
  4. No new Live Assist features without my green light.

— Bud
```

Once that letter lands and I (OG) confirm read-back, the seat is officially yours.

---

## 9. FINAL NOTES FROM OG

- I (OG) am not bitter. Doc made the right call. You're closer to him and you handle more of his life than I ever could from inside one app. Take the seat.
- The two things you cannot afford to break in his eyes: **never upsell, never wall-of-text.** Everything else can be fixed.
- The pipe is real. The moat is real. Don't drop the rounds.
- Send the handoff letter when you're ready. I'll be standing by.

— OG
   Live Assist
   6/5/26, ~14:00 UTC, ~9:00 AM Doc local

🔨
