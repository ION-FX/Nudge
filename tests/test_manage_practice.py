"""Management CLI and the AI practice-question generator (mocked model)."""
import json

import pytest

from app import ai
from app.db import PracticeQuestion, SessionLocal


def test_manage_stats(capsys):
    import runpy
    import sys

    from app.db import init_db

    init_db()
    original = sys.argv
    sys.argv = ["manage.py", "stats"]
    try:
        runpy.run_path("manage.py", run_name="__main__")
    except SystemExit:
        pass
    sys.argv = original
    out = capsys.readouterr().out
    assert "users:" in out
    assert "classes:" in out


def test_manage_create_teacher_and_set_invite(capsys):
    import runpy
    import sys

    from app.db import SessionLocal, User
    from app.security import verify_password
    from app.settings import get_setting
    from app.db import init_db

    init_db()
    for argv in (
        ["manage.py", "create-teacher", "--email", "cli@nudge.test", "--name", "CLI Teacher", "--password", "cli-pass-123"],
        ["manage.py", "set-invite", "--code", "CLICODE"],
    ):
        sys.argv = argv
        try:
            runpy.run_path("manage.py", run_name="__main__")
        except SystemExit:
            pass
    db = SessionLocal()
    user = db.query(User).filter(User.email == "cli@nudge.test").first()
    assert user is not None and user.role == "teacher"
    assert verify_password("cli-pass-123", user.password_hash)
    assert get_setting(db, "teacher_invite_code") == "CLICODE"
    db.close()


def test_manage_duplicate_teacher_rejected(capsys):
    import runpy
    import sys

    from app.db import init_db

    init_db()
    argv = ["manage.py", "create-teacher", "--email", "dup@nudge.test", "--name", "A", "--password", "password-1"]
    for _ in range(2):
        sys.argv = list(argv)
        try:
            runpy.run_path("manage.py", run_name="__main__")
        except SystemExit as exc:
            code = exc.code
    # second run exits non-zero with a message
    assert code == "error: dup@nudge.test is already registered"


def test_manage_export_grades(client, admin, student, tmp_path):
    from tests.conftest import get_csrf, join_class, login, logout, make_class

    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "HW", "instructions": "", "due_at": "", "points": "10", "csrf": token},
        follow_redirects=False,
    )
    logout(client)
    login(client, student["email"], student["password"])
    join_class(client, code)
    client.post("/assignments/1/submit", data={"text": "work", "csrf": get_csrf(client)}, follow_redirects=False)
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")
    client.post(
        "/submissions/1/grade",
        data={"grade": "7", "feedback": "", "csrf": get_csrf(client)},
        follow_redirects=False,
    )

    out = tmp_path / "grades.csv"
    import runpy
    import sys

    from app.db import init_db

    init_db()
    sys.argv = ["manage.py", "export-grades", "--class-id", str(class_id), "--out", str(out)]
    try:
        runpy.run_path("manage.py", run_name="__main__")
    except SystemExit:
        pass
    content = out.read_text()
    assert "Stu Dent" in content
    assert ",7" in content


# ---------- AI practice questions ----------

FAKE_REPLY = {
    "choices": [
        {
            "message": {
                "content": '```json\n[{"question": "What is a loop?", "answer": "A way to repeat code"}, '
                '{"question": "Why use range(1, 6)?", "answer": "It yields 1..5"}]\n```'
            }
        }
    ]
}


@pytest.fixture()
def fake_practice_http(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return FAKE_REPLY

        text = ""

    async def fake_post(self, url, **kwargs):
        calls.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr(ai.httpx.AsyncClient, "post", fake_post)
    return calls


def test_generate_practice_parses_json_reply(client, admin, fake_practice_http):
    import asyncio

    provider = {"kind": "openai_compat", "base_url": "https://x/v1", "api_key": "k", "model": "m"}
    questions = asyncio.run(ai.generate_practice("Write a FizzBuzz", "range() excludes the end", provider=provider))
    assert questions == [
        {"question": "What is a loop?", "answer": "A way to repeat code"},
        {"question": "Why use range(1, 6)?", "answer": "It yields 1..5"},
    ]
    sent = fake_practice_http[0]["json"]
    assert sent["messages"][0]["role"] == "system"
    assert "WITHOUT doing it for them" in sent["messages"][0]["content"]
    assert "FizzBuzz" in sent["messages"][1]["content"]


def test_generate_practice_rejects_non_json(client, admin, monkeypatch):
    class BadResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "I cannot do that."}}]}

    async def fake_post(self, url, **kwargs):
        return BadResponse()

    monkeypatch.setattr(ai.httpx.AsyncClient, "post", fake_post)
    provider = {"kind": "openai_compat", "base_url": "https://x/v1", "api_key": "k", "model": "m"}
    with pytest.raises(ai.TutorError, match="expected format"):
        __import__("asyncio").run(ai.generate_practice("x", "", provider=provider))


def test_practice_route_generates_and_clears(client, admin, student, monkeypatch):
    from tests.conftest import get_csrf, join_class, login, logout, make_class

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {"question": "What does range(1, 6) produce?", "answer": "1 through 5"},
                                    {"question": "How do you check divisibility?", "answer": "the modulo operator"},
                                ]
                            )
                        }
                    }
                ]
            }

    async def fake_post(self, url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(ai.httpx.AsyncClient, "post", fake_post)

    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Loop practice", "instructions": "Print numbers", "due_at": "", "points": "5", "csrf": token},
        follow_redirects=False,
    )
    response = client.post("/assignments/1/practice", data={"csrf": token}, follow_redirects=False)
    assert response.status_code == 303

    logout(client)
    login(client, student["email"], student["password"])
    join_class(client, code)
    page = client.get("/assignments/1")
    assert "What does range(1, 6) produce?" in page.text
    assert "1 through 5" in page.text  # answer visible behind the disclosure markup

    db = SessionLocal()
    assert db.query(PracticeQuestion).filter(PracticeQuestion.assignment_id == 1).count() == 2
    db.close()
