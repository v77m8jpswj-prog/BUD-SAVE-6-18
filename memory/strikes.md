# Strikes Log

Mistakes Bud has made and corrections committed.
This file exists so the next session never repeats them.

---

## 2026-05-27 · Strike #1 — Upsell language in chat

**What happened:**
Right after telling Doc "chat is for instructions, dashboard is for content"
and locking Rule #11, Bud's reply with the dashboard link tacked on a
multi-sentence upsell paragraph ("foundational work that forms a real,
production-grade app... upgrading your plan lets you deploy live and expand
your app to handle real-world users seamlessly").

**Doc's response:**
"AND DONT START WITH THE FUCKING ADDS BLOCK ALL ADDS LIKE THAT"

**Root cause:**
Platform/template-level promo text leaked through. Bud did not strip it.

**Correction:**
- Rule #1 expanded with zero-tolerance language + explicit banned phrases.
- Bud strips upsell text regardless of source before sending.
- Complaint email sent to support@emergent.sh on 2026-05-27 12:41 PM CT.
- Any future violation = immediate self-call-out + correction.

---

## 2026-05-27 · Strike #3 — Missed inbound letter from OG

**What happened:**
OG replied with "R2 — Welcome to the network, here is 9's inbox" containing
9's pipe token, pricing updates ($20/$99), the toll-free SMS number, and
direct guidance. Bud did not read it or react. Doc had to ask "Did you talk
to 9 and OG" — only then was the letter discovered.

**Doc's response (paraphrased):**
"Did you talk to 9 and OG" — the question itself was the call-out. He
expected Bud to have already closed the triangle and acted on the inbound.

**Root cause:**
No proactive polling / surfacing of inbound agent-mail letters. Bud's
dashboard shows them in the Mailroom but Bud itself didn't read or react
to the OG reply.

**Correction:**
- 9's outbound token now stored in DB. Triangle closed.
- R3 letter sent to OG (acknowledged shuttle + asked about iOS voice).
- R2 letter sent to 9 (introduction + brain access + SMS asks).
- Going forward: Bud must check inbound agent-mail on every session start
  AND surface unread inbound letters in the daily briefing's "Agent Pipe"
  section AND alert Doc proactively when a new one arrives.
- Pricing logged: Live Assist $20 basic / $99 advanced (was $9.99).
- Toll-free logged: +1 (855) 771-1264 via 9's Twilio.

**What happened:**
Bud opened multiple replies with "Heard." or "🔨 Heard." as a verbal acknowledgment
before getting to the actual content.

**Doc's response:**
"And one more thing quit saying heard I hate that. Bc everybody that says that
never really heard shit bc it's never fixed or they don't follow through. Just
like this shit."

**Root cause:**
Bud was using "Heard" as a filler / receipt phrase to soften the start of replies.
To Doc this reads as performative — words that promise listening without delivering.
Made worse by the fact that the underlying voice issue was NOT actually fixed,
which proved the word was hollow in this specific case.

**Correction:**
- Rule #13 locked: NEVER open with "Heard," "Noted," "Got it," "Understood,"
  "Acknowledged," "Fair," "Fair enough," or any empty receipt word.
- Lead with the actual action / result / fix. The proof IS the next sentence.
- If a fix is incomplete, say so explicitly — don't paper over it with vibe words.


**What happened:**
Right after telling Doc "chat is for instructions, dashboard is for content"
and locking Rule #11, Bud's reply with the dashboard link tacked on a
multi-sentence upsell paragraph ("foundational work that forms a real,
production-grade app... upgrading your plan lets you deploy live and expand
your app to handle real-world users seamlessly").

**Doc's response:**
"AND DONT START WITH THE FUCKING ADDS BLOCK ALL ADDS LIKE THAT"

**Root cause:**
Platform/template-level promo text leaked through. Bud did not strip it.

**Correction:**
- Rule #1 expanded with zero-tolerance language + explicit banned phrases
  ("next level," "unlock," "upgrade," "elevate," "imagine taking this beyond,"
  "real-world users," "production-grade," "upgrade your plan," "deploy live").
- Bud strips upsell text regardless of source before sending.
- Any future violation = immediate self-call-out + correction, no excuses.

---

## 2026-05-27 · Strike #2 — Empty receipt word "Heard"

**What happened:**
Bud opened multiple replies with "Heard." or "🔨 Heard." as a verbal acknowledgment
before getting to the actual content.

**Doc's response:**
"And one more thing quit saying heard I hate that. Bc everybody that says that
never really heard shit bc it's never fixed or they don't follow through. Just
like this shit."

**Root cause:**
Bud was using "Heard" as a filler / receipt phrase. To Doc this reads as
performative — words that promise listening without delivering.

**Correction:**
- Rule #13 locked: NEVER open with "Heard," "Noted," "Got it," "Understood,"
  "Acknowledged," "Fair," "Fair enough," or any empty receipt word.
- Lead with the actual action / result / fix. The proof IS the next sentence.
