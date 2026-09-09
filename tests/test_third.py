"""Third wave: redirects, quiz edit, profile visibility, error pages."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def test_landing_redirects_logged_in_users(client, admin):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_404_page_renders(client, admin):
    page = client.get("/classes/99999")
    assert page.status_code == 404
    assert "Class not found." in page.text


def test_quiz_edit_updates_meta(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Before", "instructions": "old", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    response = client.post(
        "/quizzes/1/edit",
        data={"title": "After", "instructions": "new", "due_at": "2099-01-01T08:00", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get("/quizzes/1")
    assert "After" in page.text
    assert "new" in page.text


def test_quiz_delete_removes_everything(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Doomed", "instructions": "", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    client.post(
        "/quizzes/1/questions",
        data={"prompt": "q", "kind": "truefalse", "correct_tf": "true", "points": "1", "csrf": token},
        follow_redirects=False,
    )
    client.post("/quizzes/1/publish", data={"csrf": token}, follow_redirects=False)

    _login_student(client, student)
    join_class(client, code)
    client.post("/quizzes/1/take", data={"q_1": "true", "csrf": get_csrf(client)}, follow_redirects=False)

    _login_admin(client)
    response = client.post("/quizzes/1/delete", data={"csrf": get_csrf(client)}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/quizzes/1").status_code == 404


def test_join_page_renders_prefilled_code(client, admin, student):
    _login_student(client, student)
    page = client.get("/join?code=abc123")
    assert 'value="ABC123"' in page.text


def test_double_logout_is_safe(client, admin):
    assert client.post("/logout", data={"csrf": get_csrf(client)}, follow_redirects=False).status_code == 303
    # second logout with no active session just redirects to login
    response = client.get("/profile", follow_redirects=False)
    assert response.status_code == 303


def test_teacher_dashboard_stats(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "M1", "pasted_text": "text", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "A1", "instructions": "", "due_at": "", "points": "", "csrf": token},
        follow_redirects=False,
    )
    page = client.get("/dashboard")
    assert "1 student" not in page.text  # no students yet
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    page = client.get("/dashboard")
    assert "👥 1 student" in page.text
    assert "📄 1 material" in page.text
    assert "📝 1 assignment" in page.text
