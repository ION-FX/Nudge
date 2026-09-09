# Running the tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

## What's covered

| File | Area |
| --- | --- |
| `test_security.py` | scrypt hashing, session expiry, CSRF helper, flash cookies, setup gate |
| `test_settings.py` | DB settings vs `.env` fallback resolution |
| `test_extract.py` (in `test_materials.py`) | text extraction, bad UTF-8, truncation, binary rejection |
| `test_ai.py` | context building (incl. quiz answer-key confidentiality), history cap, autograding rules, rate limits, error mapping, 429 retry classification |
| `test_setup_auth.py` | setup wizard, teacher invite gate, login/logout, CSRF, profile |
| `test_classes.py` | class lifecycle: create/join/edit/archive/regen-code/remove, announcements |
| `test_assignments.py` | submit → grade → notification loop, late flags, resubmission, edit/delete |
| `test_materials.py` | upload, extraction badge, download, edit, delete, access control |
| `test_quizzes.py` | builder, publish fan-out, auto-grading, single attempt, teacher attempts view |
| `test_api.py`, `test_api_extras.py` | bearer-token auth, class/assignment/quiz reads, API grading + submission, membership enforcement |
| `test_manage_practice.py` | `manage.py` commands, AI practice-question generator (mocked model) |
| `test_gradebook_search.py` | gradebook matrix + CSV, notifications, search scoping |
| `test_extras.py` | calendar, student detail page, activity feed |

## Test isolation

`tests/conftest.py` points the app at a throwaway database and uploads
directory **before** importing anything (`NUDGE_DB_PATH` / `NUDGE_UPLOAD_DIR` /
`NUDGE_DATA_DIR`), drops and recreates the schema for every test, and disables
the startup model check (`NUDGE_SKIP_MODEL_CHECK`) so the suite runs offline.

The OpenRouter stream is always mocked in tests — no network, no quota use:

```python
async def fake_stream(messages, api_key=None, model=None):
    yield "Let"; yield "us"; yield "think"
monkeypatch.setattr(ai, "stream_completion", fake_stream)
```

`make_class` / `join_class` / `login_as` helpers switch sessions explicitly
because one cookie jar is shared across a test client.
