"""Notifications, gradebook CSV, student grades page and global search."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def test_notifications_generated_and_read(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Homework 1", "instructions": "Do it", "due_at": "", "points": "10", "csrf": token},
        follow_redirects=False,
    )

    _login_student(client, student)
    feed = client.get("/notifications")
    assert "Homework 1" in feed.text
    assert "bell-count" in client.get("/dashboard").text  # unread badge

    # mark everything read; the redirect target confirms with a flash
    read_all = client.post("/notifications/read-all", data={"csrf": get_csrf(client)})
    assert "All caught up" in read_all.text
    assert "bell-count" not in client.get("/dashboard").text


def test_grade_notification(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Essay", "instructions": "", "due_at": "", "points": "10", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    client.post(
        "/assignments/1/submit",
        data={"text": "my essay", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_admin(client)
    client.post(
        "/submissions/1/grade",
        data={"grade": "9", "feedback": "Lovely", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_student(client, student)
    assert "scored 9/10" in client.get("/notifications").text


def test_gradebook_matrix_and_access(client, admin, student):
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
        data={"text": "work", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_admin(client)
    client.post(
        "/submissions/1/grade",
        data={"grade": "8", "feedback": "", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    page = client.get(f"/classes/{class_id}/gradebook")
    assert "Stu Dent" in page.text
    assert "8" in page.text

    # students cannot open the teacher's gradebook
    _login_student(client, student)
    assert client.get(f"/classes/{class_id}/gradebook").status_code == 403
    assert client.get(f"/classes/{class_id}/gradebook.csv").status_code == 403


def test_my_grades_page(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "HW", "instructions": "", "due_at": "", "points": "5", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    join_class(client, code)
    client.post(
        "/assignments/1/submit",
        data={"text": "done", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_admin(client)
    client.post(
        "/submissions/1/grade",
        data={"grade": "5", "feedback": "Perfect", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_student(client, student)
    page = client.get("/mygrades")
    assert "Test Class" in page.text
    assert "5 / 5" in page.text
    assert "Perfect" in page.text


def test_search_finds_materials_and_assignments(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Photosynthesis reading", "pasted_text": "Chloroplasts capture light.", "csrf": token},
        follow_redirects=False,
    )
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Photosynthesis worksheet", "instructions": "", "due_at": "", "points": "", "csrf": token},
        follow_redirects=False,
    )

    _login_student(client, student)
    join_class(client, code)
    page = client.get("/search?q=photosynthesis")
    assert "Photosynthesis reading" in page.text
    assert "Photosynthesis worksheet" in page.text

    empty = client.get("/search?q=quantum-tunneling-xyz")
    assert "Nothing found" in empty.text


def test_search_excludes_other_classes(client, admin, student):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/materials/new",
        data={"title": "Secret syllabus", "pasted_text": "hidden", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)  # not enrolled anywhere
    page = client.get("/search?q=syllabus")
    assert "Secret syllabus" not in page.text


def test_search_requires_login(client):
    response = client.get("/search?q=test", follow_redirects=False)
    assert response.status_code == 303
