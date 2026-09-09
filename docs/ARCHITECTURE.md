# Architecture

## One request, end to end

```
browser ──> uvicorn (ASGI)
              └─ FastAPI app (app/__init__.py: create_app)
                   ├─ setup gate middleware  → redirects everything to /setup
                   │                           until the users table has a row
                   ├─ routers (app/routes/*) → page handlers, Jinja2 responses
                   ├─ API router (app/api.py)→ /api/v1 JSON, bearer-token auth
                   ├─ static mount           → /static (css + js, self-hosted)
                   └─ exception handlers     → PageRedirect, HTTPException pages
```

Every page handler follows the same shape:

```python
user, sess = page_user(request, db)      # logs in or bounces to /login
klass = db.get(ClassRoom, cid)           # load + 404
ensure_class_member(db, user, klass)     # 403 for outsiders
...queries...
return render(request, db, "template.html", **context)
```

`render` (app/web.py) injects the common context: `user`, `csrf`, `flash`,
`unread` notification count, and `now`.

## Module map

| Module | Responsibility |
| --- | --- |
| `app/config.py` | `.env` loading; paths overridable via `NUDGE_*` env vars (used by tests) |
| `app/db.py` | SQLAlchemy models, engine, `init_db()` with additive column migrations |
| `app/security.py` | scrypt password hashing, session rows, CSRF helpers, flash cookies |
| `app/deps.py` | auth context, membership guards, form parsers, `PageRedirect` |
| `app/web.py` | Jinja2 environment, template filters, `render`/`redirect` helpers |
| `app/settings.py` | key/value settings table; resolvers that fall back from DB to `.env` |
| `app/ai.py` | system prompt, context builder, OpenRouter SSE client, 429 retries, practice-question generator |
| `app/extract.py` | text extraction (txt/md/csv/json/py + pypdf for PDF) |
| `app/notify.py` | notification fan-out helpers |
| `app/routes/*` | one module per feature area |
| `app/api.py` | bearer-token JSON API under `/api/v1` |

## Data model

`users`, `user_sessions`, `classes`, `enrollments`, `materials`, `assignments`,
`submissions`, `announcements`, `notifications`, `quizzes`, `quiz_questions`,
`quiz_attempts`, `quiz_answers`, `practice_questions`, `ai_chats`,
`ai_messages`, `settings`.

## Migrations

`init_db()` runs `Base.metadata.create_all` (creates missing tables) and then
`_ensure_columns()`, which inspects `PRAGMA table_info` and issues
`ALTER TABLE … ADD COLUMN` for anything missing. This keeps upgrades to new
versions **additive and in-place** — existing instances keep their data. Delete
`data/nudge.db` to start from scratch (the `/setup` wizard reappears).

## Why server-rendered?

The whole UI is Jinja2 templates + one stylesheet + ~130 lines of vanilla JS
(the chat streamer). That means:

- no npm/`node_modules` to audit,
- no build step between edit and reload,
- HTML that works without JavaScript except live chat streaming.

## The tutor data flow

1. `GET /assignments/{id}/tutor` finds or creates an `ai_chats` row bound to
   (user, class, assignment).
2. `POST /api/chats/{id}/messages` (session + CSRF header) assembles the model
   messages: `SYSTEM_PROMPT` + class context (materials text, assignment brief,
   quiz prompts — never quiz answers) + last 20 messages + the new message.
3. `ai.stream_completion` opens an SSE stream to OpenRouter and yields deltas;
   they are re-emitted to the browser as `data: {"type": "delta", …}` events.
4. On success both messages are persisted; on upstream 429 the request retries
   with backoff (if nothing was streamed yet) before returning an error event.
