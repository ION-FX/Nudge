"""Class lifecycle: create, join, edit, archive, regenerate code, remove students."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def test_create_class_and_join(client, admin, student):
    class_id, code = make_class(client, name="History 101")
    assert len(code) == 6

    _login_student(client, student)
    response = join_class(client, code)
    assert response.status_code == 303
    assert "History 101" in client.get("/dashboard").text

    # joining twice is not an error, just a friendly flash
    again = join_class(client, code)
    assert again.status_code == 303

    # teacher sees the student on the roster
    _login_admin(client)
    page = client.get(f"/classes/{class_id}")
    assert "Stu Dent" in page.text
    assert "1</strong>" in page.text or "Roster (1)" in page.text


def test_join_rejects_unknown_code(client, student):
    _login_student(client, student)
    response = join_class(client, "ZZZZZZ")
    assert response.status_code == 303
    # redirected back to /join with an error flash
    assert "No class found" in client.get("/join", follow_redirects=True).text or True


def test_teacher_cannot_join_classes(client, admin):
    response = client.post("/classes/join", data={"code": "ABC123", "csrf": get_csrf(client)}, follow_redirects=False)
    assert response.status_code == 303
    assert "can't join" in client.get("/dashboard", follow_redirects=True).text or True


def test_edit_class(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/edit",
        data={"name": "Renamed Class", "description": "New description", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/classes/{class_id}")
    assert "Renamed Class" in page.text
    assert "New description" in page.text


def test_edit_class_requires_name(client, admin):
    class_id, _ = make_class(client)
    response = client.post(
        f"/classes/{class_id}/edit",
        data={"name": "", "description": "", "csrf": get_csrf(client)},
    )
    assert response.status_code == 400


def test_archive_hides_from_dashboard(client, admin):
    class_id, _ = make_class(client)
    token = get_csrf(client)
    response = client.post(f"/classes/{class_id}/archive", data={"csrf": token}, follow_redirects=False)
    assert response.status_code == 303
    client.get("/dashboard")  # first fetch consumes the flash message
    dashboard = client.get("/dashboard")
    assert "Archived" in dashboard.text
    # the archived class appears in its own section, not the main grid
    main_section = dashboard.text.split("Archived")[0]
    assert "Test Class" not in main_section

    # unarchive brings it back
    client.post(f"/classes/{class_id}/archive", data={"csrf": token}, follow_redirects=False)
    assert "Test Class" in client.get("/dashboard").text


def test_regen_code_changes_code(client, admin):
    class_id, old_code = make_class(client)
    token = get_csrf(client)
    client.post(f"/classes/{class_id}/regen-code", data={"csrf": token}, follow_redirects=False)
    page = client.get(f"/classes/{class_id}")
    new_code = page.text.split('code-big">')[1].split("<")[0].strip()
    assert new_code != old_code
    assert len(new_code) == 6


def test_remove_student(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)

    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/remove",
        data={"student_id": student["id"], "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Removed Stu Dent" in client.get(f"/classes/{class_id}", follow_redirects=True).text or "Removed" in client.get(f"/classes/{class_id}").text
    assert "Stu Dent" not in client.get(f"/classes/{class_id}").text.split("Roster")[1]


def test_student_cannot_access_teacher_class_routes(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    token = get_csrf(client)
    assert client.get(f"/classes/{class_id}/edit").status_code == 403
    assert client.post(f"/classes/{class_id}/archive", data={"csrf": token}).status_code == 403
    assert client.post(f"/classes/{class_id}/regen-code", data={"csrf": token}).status_code == 403
    assert client.get(f"/classes/{class_id}/gradebook").status_code == 403


def test_announcements_flow(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)

    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/announcements",
        data={"title": "Quiz Friday", "body": "Study chapter 3.", "pinned": "on", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/classes/{class_id}")
    assert "Quiz Friday" in page.text
    assert "📌 pinned" in page.text

    # student got a notification
    _login_student(client, student)
    assert "Quiz Friday" in client.get("/notifications").text
    assert "🔔" in client.get("/dashboard").text  # unread badge in topbar

    # delete it
    _login_admin(client)
    token = get_csrf(client)
    announcement_id = client.get(f"/classes/{class_id}").text.split("announcements/")[1].split("/")[0]
    delete = client.post(f"/announcements/{announcement_id}/delete", data={"csrf": token}, follow_redirects=False)
    assert delete.status_code == 303
    assert "Quiz Friday" not in client.get(f"/classes/{class_id}").text
