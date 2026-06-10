# Bud — Emergent Google Auth Testing Playbook

Saved per playbook instructions. The testing agent should read this before
testing the auth-gated app.

## App context

- Single-user-for-now: allowlist is exactly `doc@drunderhood.com`.
- ALLOWED_EMAILS env var (comma-separated) controls the allowlist on the backend.
- Existing agent-to-agent endpoints (`/api/agent-mail/inbox`, `/api/sms/inbound`)
  use their own X-* token headers and are NOT behind the user session — they're
  called by 9 and OG (and Twilio), not by Doc's browser.
- Health, OAuth callback (Outlook), and all `/api/auth/*` routes are public.
- Everything else under `/api/*` requires a valid Doc session.

## Database collections

- `users` — one document with `user_id`, `email`, `name`, `picture`, `created_at`.
- `user_sessions` — `user_id`, `session_token`, `expires_at` (7 days from create), `created_at`.

## Auth-gated app testing flow

### Step 1 — seed a test session
```
mongosh --eval "
use('bud_database');
var userId = 'user_test_' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'doc@drunderhood.com',
  name: 'Doc Holmes',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

### Step 2 — backend API smoke
```
curl -X GET "https://bud-control.preview.emergentagent.com/api/auth/me" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# expect 200 with the user data

curl -X GET "https://bud-control.preview.emergentagent.com/api/brain/status" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# expect 200 (Doc is allowlisted)

curl -X GET "https://bud-control.preview.emergentagent.com/api/brain/status"
# expect 401 (no auth)
```

### Step 3 — browser flow
- Open the app URL — should show the Sign in with Google gate, NOT the dashboard.
- After signing in with `doc@drunderhood.com`, redirected back to `/`.
- Dashboard should load with user info + logout button visible.
- An unauthorized email should be rejected on the first sign-in with a clear
  "not on the allowlist" error and forced back to the gate.

## Checklist
- [ ] `users.user_id` is a custom UUID, not Mongo `_id`.
- [ ] `user_sessions.user_id` matches `users.user_id` exactly.
- [ ] All user queries use `{"_id": 0}` projection.
- [ ] `/api/auth/me` returns 200 with the user, or 401.
- [ ] Hitting any protected endpoint without a valid session returns 401.
- [ ] `/api/agent-mail/inbox` still accepts the `X-Agent-Token` header from 9 / OG.
- [ ] `/api/sms/inbound` still accepts the `X-Sms-Shared-Secret` header.
- [ ] `/api/outlook/oauth/callback` is reachable without auth (Microsoft hits it).
- [ ] `/api/health` is reachable without auth.

## Success indicators
- `/api/auth/me` returns Doc's user data after Google sign-in.
- Dashboard renders without redirect once authenticated.
- Logout clears the cookie and the dashboard returns to the gate.

## Failure indicators
- 401 on `/api/auth/me` immediately after sign-in (session not stored).
- 401 on `/api/agent-mail/inbox` from 9 or OG (auth middleware overreached).
- "User not found" on /api/auth/me (user_id linkage broken).
