# Contributing to Nudge

## Ground rules

1. **No npm.** The no-node constraint is a feature. New frontend behavior is
   Jinja2 templates, `style.css`, and vanilla JS in `static/js/`. If you need a
   library, vendor-audit it first and have a very good reason.
2. **Every feature gets tests.** New routes need at least a happy path, an
   authorization check, and one validation failure in `tests/`.
3. **Secrets never enter the repo.** `.env`, `data/`, and `uploads/` are
   gitignored; tests read configuration from environment variables.
4. **Migrations are additive.** Add new tables freely; add columns by
   extending `_NEW_COLUMNS` in `app/db.py` (never by editing an old column).

## Development loop

```bash
make setup          # venv + deps (installs requirements-dev.txt too)
make run            # start the server on 0.0.0.0:8000
make test           # pytest
make lint           # pyflakes over app/, tests/, manage.py, run.py, seed.py
```

The test suite must stay green and pyflakes-clean before any commit.

## Test conventions

- Fixtures come from `tests/conftest.py`: a throwaway database per test,
  `admin` (created through `/setup`), `student`, and session-aware helpers
  (`login_as`, `make_class`, `join_class`, `get_csrf`).
- Never hit the network: mock `ai.stream_completion` / `ai.httpx` when testing
  AI flows.
- Prefer user-visible assertions (page text, redirect targets) over internal
  state, but assert on the database when testing persistence semantics.

## Where to add things

- New page → `app/routes/<area>.py` + `app/templates/<page>.html`
- New JSON capability → `app/api.py` under `/api/v1/...`
- New table → `app/db.py` (model) and, if users need to reach it, both a route
  and tests
- New setting → `app/settings.py` resolver + `.env.example` entry
