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
- Rule #1 expanded with zero-tolerance language + explicit banned phrases
  ("next level," "unlock," "upgrade," "elevate," "imagine taking this beyond,"
  "real-world users," "production-grade," "upgrade your plan," "deploy live").
- Bud strips upsell text regardless of source before sending.
- Any future violation = immediate self-call-out + correction, no excuses.
