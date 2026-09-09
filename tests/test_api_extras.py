"""Extended API surface: announcements, quiz attempts, and API submissions."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _get_token(client):
    client.post("/profile/api-token", data={"csrf": get_csrf(client)}, follow_redirects=False)
    page = client.get("/profile")
    return page.text.split("<code>")[1].split("</code>")[0].strip()


def _api(client, token, method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return client.request(method, path, headers=headers, **kwargs)


def _setup_enrolled(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    return class_id


def test_announcements_via_api(client, admin, student):
    class_id = _setup_enrolled(client, admin, student)
    token = _get_token(client)
    created = _api(
        client, token, "POST", f"/api/v1/classes/{class_id}/announcements",
        json={"title": "Field trip", "body": "Permission slips due", "pinned": True},
    )
    assert created.status_code == 200
    assert created.json()["pinned"] is True

    listing = _api(client, token, "GET", f"/api/v1/classes/{class_id}/announcements").json()
    assert listing[0]["title"] == "Field trip"

    # students can read but not post
    _login_student(client, student)
    student_token = _get_token(client)
    assert _api(client, student_token, "GET", f"/api/v1/classes/{class_id}/announcements").status_code == 200
    denied = _api(
        client, student_token, "POST", f"/api/v1/classes/{class_id}/announcements",
        json={"title": "nope"},
    )
    assert denied.status_code == 403

    # empty title rejected
    _login_admin(client)
    admin_token = _get_token(client)
    assert (
        _api(client, admin_token, "POST", f"/api/v1/classes/{class_id}/announcements", json={"title": "  "}).status_code
        == 400
    )


def test_quiz_attempts_endpoint_teacher_only(client, admin, student):
    class_id, code = _setup_enrolled_and_quiz(client, admin, student)
    _login_student(client, student)
    student_token = _get_token(client)
    assert _api(client, student_token, "GET", "/api/v1/quizzes/1/attempts").status_code == 403
    client.post(
        "/api/v1/quizzes/1/submit",
        json={"answers": {"1": "1"}},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    _login_admin(client)
    admin_token = _get_token(client)
    attempts = _api(client, admin_token, "GET", "/api/v1/quizzes/1/attempts").json()
    assert attempts[0]["student"] == "Stu Dent"
    assert attempts[0]["score"] == 2


def _setup_enrolled_and_quiz(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Q", "instructions": "", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    client.post(
        "/quizzes/1/questions",
        data={"prompt": "2+2?", "kind": "mc", "choices": "3\n4", "correct_index": "1", "points": "2", "csrf": token},
        follow_redirects=False,
    )
    client.post("/quizzes/1/publish", data={"csrf": token}, follow_redirects=False)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    return class_id, code


def test_submit_assignment_via_api(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "HW", "instructions": "", "due_at": "", "points": "10", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    join_class(client, code)
    token = _get_token(client)

    empty = _api(client, token, "POST", "/api/v1/assignments/1/submit", json={"text": "  "})
    assert empty.status_code == 400

    submitted = _api(client, token, "POST", "/api/v1/assignments/1/submit", json={"text": "API submission!"})
    assert submitted.status_code == 200
    assert submitted.json()["late"] is False

    # visible in the web UI
    assert "API submission!" in client.get("/assignments/1").text

    # resubmitting via the API clears a previously entered grade
    _login_admin(client)
    client.post(
        "/submissions/1/grade",
        data={"grade": "3", "feedback": "", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    _login_student(client, student)
    token = _get_token(client)
    resubmitted = _api(client, token, "POST", "/api/v1/assignments/1/submit", json={"text": "better late version"})
    assert resubmitted.json()["grade"] is None
    assert "Grade:" not in client.get("/assignments/1").text


def test_submit_assignment_teacher_rejected(client, admin):
    make_class(client)
    token = get_csrf(client)
    client.post(
        "/classes/1/assignments/new",
        data={"title": "HW", "instructions": "", "due_at": "", "points": "", "csrf": token},
        follow_redirects=False,
    )
    admin_token = _get_token(client)
    response = _api(client, admin_token, "POST", "/api/v1/assignments/1/submit", json={"text": "teachers don't submit"})
    assert response.status_code == 403


def test_late_flag_via_api_submission(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Old HW", "instructions": "", "due_at": "2020-01-01T00:00", "points": "10", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    join_class(client, code)
    token = _get_token(client)
    result = _api(client, token, "POST", "/api/v1/assignments/1/submit", json={"text": "sorry, late"}).json()
    assert result["late"] is True
