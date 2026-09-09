"""Tutor endpoints: chat lifecycle, ownership, SSE streaming (mocked AI), rate limits."""
import json
import re

import pytest

from app import ai
from app.db import AiChat, AiMessage, SessionLocal
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _setup_class_and_student(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    return class_id


def test_tutor_page_creates_chat(client, admin, student):
    _setup_class_and_student(client, admin, student)
    page = client.get("/classes/1/tutor")
    assert page.status_code == 200
    assert "Nudge helps you" in page.text
    chat_id = page.text.split('data-chat-id="')[1].split('"')[0]
    assert chat_id == "1"  # reused on second visit
    assert client.get("/classes/1/tutor").text.split('data-chat-id="')[1].split('"')[0] == chat_id


def test_new_param_forces_fresh_chat(client, admin, student):
    _setup_class_and_student(client, admin, student)
    first = client.get("/classes/1/tutor").text.split('data-chat-id="')[1].split('"')[0]
    second = client.get("/classes/1/tutor?new=1").text.split('data-chat-id="')[1].split('"')[0]
    assert second != first


def test_conversation_list_and_delete(client, admin, student):
    _setup_class_and_student(client, admin, student)
    client.get("/classes/1/tutor")
    page = client.get("/tutor")
    assert "Class — Test Class" in page.text
    chat_id = page.text.split("chats/")[1].split("/")[0]
    response = client.post(f"/tutor/chats/{chat_id}/delete", data={"csrf": get_csrf(client)}, follow_redirects=False)
    assert response.status_code == 303
    assert "No conversations yet" in client.get("/tutor").text


def test_chat_ownership_enforced(client, admin, student):
    _setup_class_and_student(client, admin, student)
    client.get("/classes/1/tutor")  # creates chat 1 for the student
    # the teacher cannot post into the student's chat
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")
    response = client.post(
        "/api/chats/1/messages",
        json={"content": "hello"},
        headers={"X-CSRF-Token": get_csrf(client)},
    )
    assert response.status_code == 404


def test_message_requires_csrf(client, admin, student):
    _setup_class_and_student(client, admin, student)
    client.get("/classes/1/tutor")
    response = client.post("/api/chats/1/messages", json={"content": "hi"})
    assert response.status_code == 403


def test_message_requires_auth(client, admin):
    logout(client)
    response = client.post("/api/chats/1/messages", json={"content": "hi"})
    assert response.status_code == 401


@pytest.fixture()
def fake_ai(monkeypatch):
    """Replace the OpenRouter stream with a deterministic mock."""
    calls = []

    async def fake_stream(messages, api_key=None, model=None):
        calls.append({"messages": messages, "api_key": api_key, "model": model})
        for word in ["Let", "us", "think"]:
            yield word

    monkeypatch.setattr(ai, "stream_completion", fake_stream)
    return calls


def test_streaming_reply_is_persisted(client, admin, student, fake_ai):
    _setup_class_and_student(client, admin, student)
    chat_id = client.get("/classes/1/tutor").text.split('data-chat-id="')[1].split('"')[0]
    token = get_csrf(client)
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "How do I study for biology?"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    body = response.text
    assert '"type": "delta"' in body and '"type": "done"' in body
    deltas = re.findall(r'"text": "([^"]*)"', body)
    assert "".join(deltas) == "Letusthink"

    db = SessionLocal()
    messages = db.query(AiMessage).filter(AiMessage.chat_id == int(chat_id)).order_by(AiMessage.id).all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "How do I study for biology?"
    assert messages[1].content == "Letusthink"
    db.close()

    # the AI call received the mocked context + key resolution
    from app import config as app_config

    assert fake_ai[0]["api_key"] == app_config.OPENROUTER_API_KEY
    system = fake_ai[0]["messages"][0]
    assert system["role"] == "system"
    assert "never reveal" in system["content"].lower()


def test_failed_stream_persists_nothing(client, admin, student, monkeypatch):
    from app.ai import TutorError

    async def failing_stream(messages, api_key=None, model=None):
        raise TutorError("The free AI pool is busy right now.")
        yield  # pragma: no cover

    monkeypatch.setattr(ai, "stream_completion", failing_stream)
    _setup_class_and_student(client, admin, student)
    chat_id = client.get("/classes/1/tutor").text.split('data-chat-id="')[1].split('"')[0]
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "hello"},
        headers={"X-CSRF-Token": get_csrf(client)},
    )
    assert '"type": "error"' in response.text
    db = SessionLocal()
    assert db.query(AiMessage).count() == 0
    db.close()


def test_rate_limit_returns_error_event(client, admin, student, fake_ai, monkeypatch):
    monkeypatch.setattr(ai, "RATE_LIMIT_MESSAGES", 2)
    _setup_class_and_student(client, admin, student)
    chat_id = client.get("/classes/1/tutor").text.split('data-chat-id="')[1].split('"')[0]
    headers = {"X-CSRF-Token": get_csrf(client)}
    for _ in range(2):
        client.post(f"/api/chats/{chat_id}/messages", json={"content": "go"}, headers=headers)
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": "one too many"}, headers=headers)
    assert "rate limit" in response.text


def test_guardrail_system_prompt_contains_hard_rules(client, admin, student):
    from app.ai import SYSTEM_PROMPT

    assert "Never reveal" in SYSTEM_PROMPT
    assert "answer key" in SYSTEM_PROMPT.lower() or "confidential" in SYSTEM_PROMPT.lower()
    assert "DIFFERENT" in SYSTEM_PROMPT


def test_quiz_context_never_contains_answer_key():
    from app.db import ClassRoom, Quiz, QuizQuestion, User

    db = SessionLocal()
    teacher = User(email="q@x.io", name="T", role="teacher", password_hash="x")
    db.add(teacher)
    db.commit()
    klass = ClassRoom(name="Chem", join_code="CHM001", teacher_id=teacher.id)
    db.add(klass)
    db.commit()
    quiz = Quiz(class_id=klass.id, title="Safety quiz", published=True)
    db.add(quiz)
    db.commit()
    db.add(QuizQuestion(quiz_id=quiz.id, prompt="Who is the fire warden?", correct=json.dumps({"answers": ["Ms. Rivera"]})))
    db.commit()
    chat = AiChat(user_id=teacher.id, class_id=klass.id, quiz_id=quiz.id)
    db.add(chat)
    db.commit()
    context = ai.build_context(db, chat)
    assert "Who is the fire warden?" in context
    assert "Rivera" not in context
    db.close()
