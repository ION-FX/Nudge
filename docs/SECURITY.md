# Security notes

## Secrets

- All secrets live in `.env`, which is **gitignored**. `.env.example` documents
  every key with placeholders only.
- The OpenRouter key entered on the `/setup` page is stored in the `settings`
  table of `data/nudge.db` (also gitignored). Anyone with database read access
  has it — protect `data/` like you protect `.env`.
- If a key was ever pasted into chat, a ticket, or a screenshot, **rotate it**.

## Accounts

- Passwords are hashed with scrypt (per-user random salt, constant-time
  comparison). Plaintext passwords are never stored or logged.
- Sessions are random 32-byte tokens stored server-side (the cookie carries
  only the token) with a 30-day expiry, `HttpOnly` and `SameSite=Lax`.
- Teacher registration is gated by an invite code (set on `/setup`, in `.env`,
  or via `manage.py set-invite`). Students never need a code.
- The `/setup` wizard is reachable **only while the users table is empty** —
  the first account claims the instance.

## Request hardening

- Every authenticated form POST requires a per-session CSRF token; the JSON
  API requires the `X-CSRF-Token` header (cookie flows) or a bearer token.
- Anonymous users are redirected to login; role mismatches return 403
  (teachers-only pages) or 404/403 (objects outside your membership).
- Uploads are limited by size (`MAX_UPLOAD_MB`), extension whitelist, and are
  stored with UUID names under `uploads/` (never web-served directly —
  downloads stream through an authorization check).

## The AI co-pilot

- The system prompt forbids revealing assignment answers and treats any answer
  keys found in materials as confidential. For quizzes, only question prompts
  are sent to the model — stored answers never leave the database.
- Prompts are kept short (last 20 messages, truncated material text) to limit
  data exposure to the model provider.

## Reporting

Found something? Open an issue at
<https://github.com/ION-FX/Nudge/issues> — for anything sensitive, ask for a
private channel first.
