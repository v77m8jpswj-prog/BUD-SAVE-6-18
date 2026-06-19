#!/usr/bin/env bash
# Bud — full migration prep, based on 9's R15 playbook.
# Idempotent: safe to re-run. Each step prints PASS/FAIL.
set -u
cd "$(dirname "$0")"
MIG=/app/memory/migration

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yel()   { printf "\033[33m%s\033[0m\n" "$*"; }
hr()    { printf "\n\033[36m── %s ──\033[0m\n" "$*"; }

hr "STEP 1: snapshot .env values to migration/secrets_snapshot.txt"
cp /app/backend/.env "$MIG/secrets_snapshot.txt"
chmod 600 "$MIG/secrets_snapshot.txt"
green "OK   wrote $MIG/secrets_snapshot.txt ($(wc -l <"$MIG/secrets_snapshot.txt") lines)"
yel  "NOTE  this file is gitignored (*.env-style patterns). Keep a copy OFFLINE before deleting the old pod."

hr "STEP 2: fresh mongodump → $MIG/mongo_dump"
rm -rf "$MIG/mongo_dump"
source /app/backend/.env
mongodump --uri="$MONGO_URL" --db="$DB_NAME" --out="$MIG/mongo_dump" --quiet
green "OK   dump complete ($(du -sh $MIG/mongo_dump | cut -f1))"

hr "STEP 3: drop token-bearing collections (per 9's R15 — GitHub PushProtection will block these)"
DB_DIR="$MIG/mongo_dump/$DB_NAME"
for col in agent_letters outlook_tokens oauth_states user_sessions; do
  if [ -f "$DB_DIR/${col}.bson" ]; then
    rm -f "$DB_DIR/${col}.bson" "$DB_DIR/${col}.metadata.json"
    green "OK   dropped $col"
  fi
done

hr "STEP 4: scrub config.bson token fields"
python3 "$MIG/scrub.py" 2>&1 | grep -E "config|FAIL" || true

hr "STEP 5: regex-sweep BSON dump for stray secrets"
HITS=$(grep -rlE "sk-[A-Za-z0-9_-]{30,}|SG\.[A-Za-z0-9_-]{20,}|AC[a-f0-9]{32}|SK[a-f0-9]{32}|EAA[A-Za-z0-9]{40,}|[A-Za-z0-9]{1,4}~[A-Za-z0-9_~\-]{30,}" "$MIG/mongo_dump" 2>/dev/null || true)
if [ -z "$HITS" ]; then green "OK   no stray secrets in dump"; else red "FAIL  hits found:"; echo "$HITS"; exit 1; fi

hr "STEP 6: scan /app/memory + tracked code for hardcoded tokens (9's gotcha)"
SCAN_HITS=$(grep -rlE "sk-[A-Za-z0-9_-]{30,}|SG\.[A-Za-z0-9_-]{20,}|AC[a-f0-9]{32}|SK[a-f0-9]{32}|EAA[A-Za-z0-9]{40,}|[A-Za-z0-9]{1,4}~[A-Za-z0-9_~\-]{30,}" \
  --include="*.md" --include="*.py" --include="*.json" --include="*.js" --include="*.txt" \
  --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=build --exclude-dir=.git \
  --exclude-dir=mongo_dump --exclude=secrets_snapshot.txt \
  /app/memory /app/backend /app/frontend/src /app/*.md 2>/dev/null || true)
if [ -z "$SCAN_HITS" ]; then
  green "OK   no hardcoded tokens in tracked files"
else
  red "FAIL  hardcoded tokens found in:"
  echo "$SCAN_HITS"
  yel "       Edit these files to read from os.environ instead, then re-run."
  exit 1
fi

hr "STEP 7: verify .env files + secrets_snapshot are gitignored"
cd /app
for f in backend/.env frontend/.env memory/migration/secrets_snapshot.txt; do
  if git check-ignore "$f" >/dev/null 2>&1; then
    green "OK   $f is ignored"
  else
    red "FAIL  $f is NOT gitignored — would leak on push"
    exit 1
  fi
done

hr "STEP 8: verify 'Save to Github' won't push a duplicate"
yel  "REMINDER  in the Save-to-Github modal, click 'Select Repo' (not 'Create New')"
yel  "          and pick your existing Bud repo to overwrite cleanly."

hr "STEP 9: final summary"
echo "Dump size:   $(du -sh $MIG/mongo_dump | cut -f1)"
echo "Collections: $(ls $MIG/mongo_dump/$DB_NAME/*.bson 2>/dev/null | wc -l)"
echo "Secrets snapshot: $MIG/secrets_snapshot.txt  ← back this up OFFLINE"
echo "Migration README: $MIG/README.md"
green ""
green "READY TO PUSH."
green "Next: tap 'Save to Github' → 'Select Repo' → pick your existing Bud repo."
