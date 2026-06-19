#!/usr/bin/env bash
# Bud — restore script (RUN ON THE NEW POD, not the old one).
# Prereqs on the new pod:
#   • code imported from GitHub
#   • /app/memory/migration/mongo_dump/ present from the repo
#   • /app/backend/.env populated from the secrets snapshot
set -u
cd "$(dirname "$0")"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yel()   { printf "\033[33m%s\033[0m\n" "$*"; }
hr()    { printf "\n\033[36m── %s ──\033[0m\n" "$*"; }

MIG=/app/memory/migration
DUMP_DIR="$MIG/mongo_dump"

hr "STEP 1: sanity checks"
if [ ! -d "$DUMP_DIR" ]; then red "FAIL  no dump at $DUMP_DIR"; exit 1; fi
if [ ! -f /app/backend/.env ]; then red "FAIL  /app/backend/.env missing — paste it from secrets_snapshot first"; exit 1; fi
source /app/backend/.env
if [ -z "${MONGO_URL:-}" ] || [ -z "${DB_NAME:-}" ]; then red "FAIL  MONGO_URL / DB_NAME unset"; exit 1; fi
green "OK   dump found, .env loaded, target db=$DB_NAME"

hr "STEP 2: mongorestore"
mongorestore --uri="$MONGO_URL" --drop "$DUMP_DIR" --quiet
green "OK   restore complete"
echo "Collections in $DB_NAME:"
mongosh "$MONGO_URL/$DB_NAME" --quiet --eval "db.getCollectionNames().forEach(c => print('  • ' + c + ' (' + db[c].countDocuments() + ')'))"

hr "STEP 3: restart backend"
sudo supervisorctl restart backend 2>&1 | tail -5
sleep 3
green "OK   backend restarted"

hr "STEP 4: smoke tests"
curl -s -o /dev/null -w "  /api/health         %{http_code}\n" "http://localhost:8001/api/health"
curl -s "http://localhost:8001/api/brain/status" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('  brain.pipe_ok      ', d.get('pipe_ok')); print('  brain.token_ok     ', d.get('token_ok')); print('  brain.open_count   ', d.get('open_count'))" 2>/dev/null || echo "  brain status check requires auth — skip"

hr "STEP 5: manual follow-ups (NOT automated — Doc must do these)"
yel "  a. Re-OAuth Microsoft Graph: visit dashboard → Connect Outlook → sign in as doc@drunderhood.com"
yel "  b. Update Entra redirect URI to the NEW pod URL + /api/outlook/oauth/callback"
yel "  c. Update Twilio webhook to NEW pod URL + /api/sms/inbound (use PROD URL once deployed)"
yel "  d. Get fresh BRAIN_BASE + BUD_BRAIN_BEARER from 9, paste into .env, restart backend"
yel "  e. Get fresh OG_INBOX_URL + AGENT_MAIL_OG_OUTBOUND_TOKEN from OG, paste, restart"
yel "  f. Send 9 your new bud_base_url + bud_inbound_token (via agent-mail or DM) so he updates peers"

green ""
green "RESTORE DONE."
echo "Next: tap Deploy once smoke tests are clean."
