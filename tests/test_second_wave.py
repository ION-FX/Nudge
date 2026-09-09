"""Second wave: edge cases across auth, materials, tutor context, and the API."""
from app import ai
from app.extract import extract_text
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    get_csrf,
    join_class,
    login,
    login_as,
    logout,
    make_class,
)


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    login_as(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def _get_token(client):
    client.post("/profile/api-token", data={"csrf": get_csrf(client)}, follow_redirects=False)
    page = client.get("/profile")
    return page.text.split("<code>")[1].split("</code>")[0].strip()


def test_registration_normalizes_email_case(client, admin):
    response = client.post(
        "/register",
        data={"name": "Caps", "email": "MiXeD@Nudge.Test", "password": "password1", "role": "student", "teacher_code": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    # the lowercase version is now taken
    dup = client.post(
        "/register",
        data={"name": "Again", "email": "mixed@nudge.test", "password": "password1", "role": "student", "teacher_code": ""},
    )
    assert dup.status_code == 400


def test_join_code_case_insensitive(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    response = join_class(client, code.lower())
    assert response.status_code == 303


def test_password_change_requires_minimum_length(client, admin):
    token = get_csrf(client)
    response = client.post(
        "/profile/password",
        data={"current": "admin-pass-1", "new": "short", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "at least 8" in client.get("/profile", follow_redirects=True).text


def test_extract_json_file():
    data = b'{"topic": "loops", "count": 3}'
    text = extract_text("quiz.json", data)
    assert "loops" in text


def test_extract_empty_file():
    assert extract_text("empty.txt", b"") == ""


def test_material_text_survives_title_edit(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Keeper", "pasted_text": "precious content", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}?tab=materials")
    material_id = __import__("re").search(r"materials/(\d+)", page.text).group(1)
    client.post(
        f"/materials/{material_id}/edit",
        data={"title": "Renamed", "description": "", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    page = client.get(f"/materials/{material_id}")
    assert "precious content" in page.text


def test_quiz_question_points_bounded(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        "/classes/1/quizzes/new",
        data={"title": "Bounds", "instructions": "", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    for points, expect_ok in (("0", True), ("999", True), ("abc", True)):
        client.post(
            "/quizzes/1/questions",
            data={"prompt": f"q {points}", "kind": "truefalse", "correct_tf": "true", "points": points, "csrf": token},
            follow_redirects=False,
        )
    page = client.get("/quizzes/1")
    # all three parsed, but out-of-bounds values clamp to 1..100 defaults
    assert page.text.count("pt") >= 3
    section = page.text.split("Questions")[1].split("Add a question")[0]
    assert "100 pts" in section  # 999 clamped to the 1..100 range
    assert "999 pts" not in section


def test_grade_notification_link_targets_assignment(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Link check", "instructions": "", "due_at": "", "points": "5", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    client.post("/assignments/1/submit", data={"text": "x", "csrf": get_csrf(client)}, follow_redirects=False)
    _login_admin(client)
    client.post(
        "/submissions/1/grade",
        data={"grade": "4", "feedback": "", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_student(client, student)
    feed = client.get("/notifications")
    assert 'href="/assignments/1"' in feed.text


def test_tutor_quiz_context_includes_materials_too(client, admin, student):
    from app.db import AiChat, ClassRoom, Material, Quiz, SessionLocal, User

    db = SessionLocal()
    teacher = db.query(User).filter(User.email == "admin@nudge.test").first()
    klass = ClassRoom(name="Ctx", join_code="CTX001", teacher_id=teacher.id)
    db.add(klass)
    db.commit()
    db.add(Material(class_id=klass.id, title="Guide", text_content="Photosynthesis uses light."))
    quiz = Quiz(class_id=klass.id, title="Light quiz", published=True)
    db.add(quiz)
    db.commit()
    chat = AiChat(user_id=teacher.id, class_id=klass.id, quiz_id=quiz.id)
    db.add(chat)
    db.commit()
    context = ai.build_context(db, chat)
    assert "Light quiz" in context
    assert "Photosynthesis uses light." in context
    db.close()


def test_api_material_and_search(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Searchable reading", "pasted_text": "uniquebodytext", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    api_token = _get_token(client)
    detail = client.get(
        "/api/v1/materials/1", headers={"Authorization": f"Bearer {api_token}"}
    ).json()
    assert detail["title"] == "Searchable reading"
    assert detail["ai_readable"] is True

    hits = client.get(
        "/api/v1/search?q=uniquebodytext", headers={"Authorization": f"Bearer {api_token}"}
    ).json()
    assert hits["results"]["materials"][0]["id"] == 1

    # outsiders get nothing
    _login_student(client, student)
    student_token = _get_token(client)
    empty = client.get(
        "/api/v1/search?q=uniquebodytext", headers={"Authorization": f"Bearer {student_token}"}
    ).json()
    assert empty["results"]["materials"] == []


def test_csrf_enforced_on_material_delete(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Guarded", "pasted_text": "x", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}?tab=materials")
    material_id = __import__("re").search(r"materials/(\d+)", page.text).group(1)
    response = client.post(f"/materials/{material_id}/delete", data={"csrf": "wrong"}, follow_redirects=False)
    assert response.status_code == 403
