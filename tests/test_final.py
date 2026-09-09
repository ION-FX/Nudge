"""Final batch: misc coverage gaps found during the scale-up."""
import io

from app.extract import extract_text
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def test_unpublished_quiz_not_in_calendar(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Draft quiz", "instructions": "", "due_at": "2099-04-01T09:00", "csrf": token},
        follow_redirects=False,
    )
    page = client.get("/calendar")
    assert "Draft quiz" not in page.text
    client.post("/quizzes/1/publish", data={"csrf": token}, follow_redirects=False)
    assert "Draft quiz" in client.get("/calendar").text


def test_material_description_shows_on_class_card(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Titled", "description": "Week one reading", "pasted_text": "body", "csrf": token},
        files={"file": ("", b"")},
        follow_redirects=False,
    )
    assert "Week one reading" in client.get(f"/classes/{class_id}").text


def test_search_finds_classes_by_name(client, admin, student):
    class_id, code = make_class(client, name="Astrophysics 300")
    _login_student(client, student)
    join_class(client, code)
    page = client.get("/search?q=astrophysics")
    assert "Astrophysics 300" in page.text


def test_announcement_link_has_anchor(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/announcements",
        data={"title": "Anchor test", "body": "", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    feed = client.get("/notifications")
    assert 'href="/classes/1#announcements"' in feed.text


def test_extract_csv_with_quoted_commas():
    text = extract_text("data.csv", b'name,score\n"doe, jane",99\n')
    assert '"doe, jane"' in text


def test_api_me_for_student_role(client, admin, student):
    _login_student(client, student)
    client.post("/profile/api-token", data={"csrf": get_csrf(client)}, follow_redirects=False)
    token = client.get("/profile").text.split("<code>")[1].split("</code>")[0].strip()
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "student"
    assert me["name"] == "Stu Dent"


def test_quiz_attempts_require_published_or_teacher(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Hidden", "instructions": "", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    join_class(client, code)
    assert client.get("/quizzes/1").status_code == 403
    assert client.get("/quizzes/1/tutor").status_code == 403


def test_material_without_text_not_ai_readable(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Picture only", "csrf": token},
        files={"file": ("pic.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}")
    assert "Nudge can read this" not in page.text
    material_id = __import__("re").search(r"materials/(\d+)", page.text).group(1)
    detail = client.get(f"/materials/{material_id}")
    assert "No readable text" in detail.text
