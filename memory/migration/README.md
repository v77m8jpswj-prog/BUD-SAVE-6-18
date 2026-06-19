# Bud — Migration to new Emergent account

## What's in this folder
- `mongo_dump/bud_database/` — raw BSON dump of the entire Bud database, secrets scrubbed.
- `scrub.py` — the script that scrubbed token-bearing fields. Keep for audit / re-runs.
- This README.

## What was scrubbed (and must be re-established on the new pod)
- `outlook_tokens` collection — DELETED. Re-OAuth Microsoft Graph after migration.
- `user_sessions` collection — DELETED. Doc will sign in again with Google.
- `oauth_states` collection — DELETED (was empty / transient).
- `config.bud_inbound_token` / `nine_outbound_token` — NULLED. New tokens will be issued on first boot + by 9.
- All BSON files swept with regex for API-key signatures; matches replaced with `[REDACTED-*]`.

## Migration playbook (Doc)

### A. On the OLD account (this one)
1. Tap **Save to Github** in the chat input. Push the repo. (Only you can do git writes.)
2. Confirm push succeeded with no GitHub push-protection blocks. (If anything trips, paste the block message here and I'll surgically scrub.)

### B. On the NEW account
3. Open a new chat. Hit the **+** button in the input. **Import from GitHub** → pick your Bud repo.
4. Once the new pod boots, copy `/app/backend/.env.example` → `/app/backend/.env` and fill in:
   - `EMERGENT_LLM_KEY` (provided by Emergent on the new account — check Profile → Universal Key)
   - `MS_*` (same Entra app credentials as before — update `MS_REDIRECT_URI` to the NEW pod URL)
   - `TWILIO_*` (same credentials)
   - `BRAIN_BASE` + `BUD_BRAIN_BEARER` (ask 9 for the new ones — his pod URL also changed)
   - `OG_INBOX_URL` + `AGENT_MAIL_OG_OUTBOUND_TOKEN` (ask OG)
   - `BUD_BASE_URL` = new pod's public URL
   - `CORS_ORIGINS` = new pod's public URL
5. Restore the database:
   ```
   mongorestore --uri="$MONGO_URL" --drop /app/memory/migration/mongo_dump
   ```
6. Restart backend (`sudo supervisorctl restart backend`).
7. **Re-OAuth Microsoft Graph** — visit the dashboard, click "Connect Outlook", sign in as doc@drunderhood.com.
8. **Update Twilio webhook**: in Twilio console, change the inbound SMS webhook for 855-771-1264 to `{NEW_BUD_BASE_URL}/api/sms/inbound`.
9. **Update Entra app redirect URI** in the Azure portal: add `{NEW_BUD_BASE_URL}/api/outlook/oauth/callback`.
10. Send 9 your new `bud_base_url` + new `bud_inbound_token` (visible at `/api/agent-mail/config`).
11. Get 9's new pod URL + new bearer; put them in `.env` as `BRAIN_BASE` / `BUD_BRAIN_BEARER`.

### C. Verify
- Hit `/api/health` → 200.
- Hit `/api/brain/status` → `pipe_ok: true`, `token_ok: true`.
- Hit `/api/outlook/status` → `connected: true`.
- Send a test letter via `/api/agent-mail/send` to 9 → 200 delivered.
- Send a test SMS to the Twilio number → it shows up in the Inbound SMS panel.

## Restore command (copy/paste ready)
```bash
mongorestore --uri="$MONGO_URL" --drop /app/memory/migration/mongo_dump
```
