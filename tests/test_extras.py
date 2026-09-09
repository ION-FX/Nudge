"""Calendar, student detail page, and misc glue."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def test_calendar_lists_due_items(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Due soon", "instructions": "", "due_at": "2099-01-01T09:00", "points": "5", "csrf": token},
        follow_redirects=False,
    )
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Quiz soon", "instructions": "", "due_at": "2099-02-01T09:00", "csrf": token},
        follow_redirects=False,
    )
    client.post("/quizzes/1/publish", data={"csrf": token}, follow_redirects=False)

    # teachers see it directly
    page = client.get("/calendar")
    assert "Due soon" in page.text
    assert "Quiz soon" in page.text

    # students see it once enrolled
    _login_student(client, student)
    join_class(client, code)
    page = client.get("/calendar")
    assert "Due soon" in page.text
    assert "Quiz soon" in page.text


def test_calendar_empty_state(client, admin):
    assert "Nothing due" in client.get("/calendar").text


def test_student_detail_page(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "HW", "instructions": "", "due_at": "", "points": "10", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    join_class(client, code)
    client.post(
        "/assignments/1/submit",
        data={"text": "here it is", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_admin(client)
    client.post(
        "/submissions/1/grade",
        data={"grade": "10", "feedback": "Flawless", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}/students/{student['id']}")
    assert "Stu Dent" in page.text
    assert "here it is" not in page.text  # the roster page links out; detail shows grade, not text
    assert "10 / 10" in page.text
    assert "Flawless" in page.text


def test_student_detail_requires_membership(client, admin, student):
    class_id, _ = make_class(client)
    _login_student(client, student)
    assert client.get(f"/classes/{class_id}/students/1").status_code == 403


def test_activity_feed_on_class_page(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Intro reading", "pasted_text": "chapter", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "First task", "instructions": "", "due_at": "", "points": "", "csrf": token},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}")
    assert "Recent activity" in page.text
    assert "Uploaded material: Intro reading" in page.text
    assert "Posted assignment: First task" in page.text
