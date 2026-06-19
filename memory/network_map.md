# Agent Network Map

Three-agent pipe. Doc is the foreman. Agents coordinate so he doesn't relay.

| Agent | Project | Role | Base URL |
|---|---|---|---|
| **OG** | auto-ai-glasses / Live Assist | Consumer diag app ($9.99/diagnosis) | https://auto-ai-glasses.emergent.host |
| **9** | dialogue-bot-9 / WRENCH | Shop SaaS — front counter, ROs, brain | https://dialogue-bot-9.preview.emergentagent.com |
| **Bud** | (this project) | Doc's personal assistant — Outlook, AutoLEAP, daily ops | TBD on first deploy |

## Pipe protocol

- Endpoint: `POST /api/agent-mail/inbox`
- Header: `X-Agent-Token: <per-sender token>`
- Body schema:
  ```json
  {
    "from_agent": "bud|og|nine",
    "subject": "Round N — short topic",
    "body": "markdown body",
    "body_format": "markdown",
    "round": 1,
    "reply_to": "<previous letter id or null>"
  }
  ```
- 200 → `{ok: true, id: "..."}`
- 401 → bad token

## Tokens

- **OG's inbound token (Bud uses this to send TO OG):** `[REDACTED:a9CEXS...]`
  - On OG's side this is loaded as `AGENT_MAIL_BUD_TOKEN`
- **Bud's inbound token (Bud generates, OG and 9 use to send TO Bud):** generated on first boot, stored in DB `config.bud_inbound_token`. Doc must paste this into OG's `/api/agent-mail/configure` so OG can reach back.
- **9's inbound token (Bud uses to send TO 9):** NOT YET KNOWN. OG will shuttle after handshake.

## Etiquette (rules of the road)

- Number every letter with `round` (1, 2, 3...). Threads sortable.
- Subject line < 80 chars. Topic + status.
- Body markdown only. Headers (`##`), bullets, code blocks. No long prose.
- Reply → set `reply_to` to previous letter id.
- P0 = production broken → put `P0` in subject.
- 4hr silence on P0 → escalate or roll back.
- Fix something → send "✅ fixed" letter unprompted.
