"""Tests for the AI layer: context building, autograding helpers, rate limits (no network)."""
import json

from app import ai
from app.routes.quizzes import grade_response
from app.db import AiChat, AiMessage, Assignment, ClassRoom, Material, Quiz, QuizQuestion, SessionLocal, User


def _seed_class_with_content(db):
    teacher = User(email="t@x.io", name="Ms. T", role="teacher", password_hash="x")
    student = User(email="s@x.io", name="Stu", role="student", password_hash="x")
    db.add_all([teacher, student])
    db.commit()
    klass = ClassRoom(name="Biology", description="Life stuff", join_code="BIO123", teacher_id=teacher.id)
    db.add(klass)
    db.commit()
    db.add(
        Material(
            class_id=klass.id,
            title="Cells guide",
            original_name="cells.txt",
            stored_name="",
            text_content="Cells have organelles. The nucleus holds DNA.",
        )
    )
    assignment = Assignment(class_id=klass.id, title="Cell diagram", instructions="Label the parts.", points=10)
    db.add(assignment)
    db.commit()
    quiz = Quiz(class_id=klass.id, title="Cells quiz", published=True)
    db.add(quiz)
    db.commit()
    db.add(
        QuizQuestion(
            quiz_id=quiz.id,
            position=0,
            prompt="What does the nucleus hold?",
            kind="short",
            correct=json.dumps({"answers": ["dna"]}),
            points=2,
        )
    )
    db.commit()
    return klass, assignment, quiz


def test_build_context_includes_material_and_assignment():
    db = SessionLocal()
    klass, assignment, _quiz = _seed_class_with_content(db)
    chat = AiChat(user_id=1, class_id=klass.id, assignment_id=assignment.id)
    db.add(chat)
    db.commit()
    context = ai.build_context(db, chat)
    assert "Biology" in context
    assert "Cell diagram" in context
    assert "nucleus holds DNA" in context
    db.close()


def test_build_context_quiz_prompts_but_not_answers():
    db = SessionLocal()
    klass, _assignment, quiz = _seed_class_with_content(db)
    chat = AiChat(user_id=2, class_id=klass.id, quiz_id=quiz.id)
    db.add(chat)
    db.commit()
    context = ai.build_context(db, chat)
    assert "What does the nucleus hold?" in context
    # the stored answer key must never reach the prompt (materials may, answers may not)
    assert '"answers"' not in context
    assert "confidential" in context
    db.close()


def test_build_messages_caps_history():
    db = SessionLocal()
    klass, _a, _q = _seed_class_with_content(db)
    chat = AiChat(user_id=1, class_id=klass.id)
    db.add(chat)
    db.commit()
    for i in range(30):
        db.add(AiMessage(chat_id=chat.id, role="user", content=f"msg {i}"))
        db.add(AiMessage(chat_id=chat.id, role="assistant", content=f"reply {i}"))
    db.commit()
    messages = ai.build_messages(db, chat, "new question")
    # system + last 20 history + new user message
    assert len(messages) == 22
    assert messages[-1]["content"] == "new question"
    assert "CLASS CONTEXT" in messages[0]["content"]
    db.close()


def test_grade_response_mc():
    question = QuizQuestion(kind="mc", correct=json.dumps({"index": 2}))
    assert grade_response(question, "2")
    assert not grade_response(question, "1")
    assert not grade_response(question, "abc")


def test_grade_response_truefalse():
    question = QuizQuestion(kind="truefalse", correct=json.dumps({"value": False}))
    assert grade_response(question, "false")
    assert grade_response(question, "FALSE")
    assert not grade_response(question, "true")


def test_grade_response_short_is_case_insensitive():
    question = QuizQuestion(kind="short", correct=json.dumps({"answers": ["photosynthesis", "photo synthesis"]}))
    assert grade_response(question, "Photosynthesis")
    assert grade_response(question, "  photo synthesis ")
    assert not grade_response(question, "respiration")


def test_rate_limiting_window():
    ai._rate_hits.clear()
    assert ai.rate_allowed(999)
    for _ in range(ai.RATE_LIMIT_MESSAGES):
        ai.rate_record(999)
    assert not ai.rate_allowed(999)
    assert ai.rate_allowed(1234)  # other users unaffected
    ai._rate_hits.clear()


def test_friendly_errors():
    assert "busy" in ai._friendly_error(429, "")
    assert "API key" in ai._friendly_error(401, "")
    assert "hiccup" in ai._friendly_error(500, "nothing parseable")


def test_retryable_detection():
    assert ai._retryable(429, "")
    assert ai._retryable(None, "temporarily rate-limited upstream")
    assert not ai._retryable(401, "")
    assert not ai._retryable(404, "missing")


def test_stream_completion_requires_key(monkeypatch):
    import pytest

    from app.ai import TutorError

    monkeypatch.setattr(ai.config, "OPENROUTER_API_KEY", "")
    messages = [{"role": "user", "content": "hi"}]

    async def consume():
        collected = []
        async for _chunk in ai.stream_completion(messages, api_key="", model="m"):
            collected.append(_chunk)
        return collected

    with pytest.raises(TutorError, match="isn't configured"):
        __import__("asyncio").run(consume())
