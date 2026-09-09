"""JSON API v1: token auth, class/assignment reads, grading, quiz submission."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _get_token(client):
    """Session-authenticated token generation via the profile page flow."""
    response = client.post("/profile/api-token", data={"csrf": get_csrf(client)}, follow_redirects=False)
    assert response.status_code == 303
    token = None
    for _name, value in client.cookies.items():
        pass
    # the token is rendered on the profile page
    page = client.get("/profile")
    marker = "<code>"
    token = page.text.split(marker)[1].split("</code>")[0].strip()
    assert token.startswith(("sk", "nudge")) or len(token) >= 32
    return token


def _api(client, token, method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return client.request(method, path, headers=headers, **kwargs)


def test_api_requires_token(client, admin):
    assert client.get("/api/v1/me", follow_redirects=False).status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer nope"}, follow_redirects=False).status_code == 401


def test_me_endpoint(client, admin):
    token = _get_token(client)
    data = _api(client, token, "GET", "/api/v1/me").json()
    assert data["email"] == "admin@nudge.test"
    assert data["role"] == "teacher"


def test_token_rotation_invalidates_old(client, admin):
    token = _get_token(client)
    assert _api(client, token, "GET", "/api/v1/me").status_code == 200
    new_token = _api(client, token, "POST", "/api/v1/me/token").json()["token"]
    assert new_token != token
    assert _api(client, token, "GET", "/api/v1/me").status_code == 401
    assert _api(client, new_token, "GET", "/api/v1/me").status_code == 200


def test_classes_and_class_detail(client, admin, student):
    class_id, code = make_class(client)
    token = _get_token(client)
    classes = _api(client, token, "GET", "/api/v1/classes").json()
    assert classes[0]["name"] == "Test Class"
    assert classes[0]["join_code"] == code  # teachers can see the code

    detail = _api(client, token, "GET", f"/api/v1/classes/{class_id}").json()
    assert detail["name"] == "Test Class"

    # students see the class too, but never the join code
    _login_student(client, student)
    join_class(client, code)
    student_token = _get_token(client)
    student_classes = _api(client, student_token, "GET", "/api/v1/classes").json()
    assert student_classes[0]["id"] == class_id
    assert student_classes[0]["join_code"] is None


def test_assignment_read_and_grading(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "HW", "instructions": "Do it", "due_at": "", "points": "10", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    join_class(client, code)
    student_token = _get_token(client)
    client.post(
        "/assignments/1/submit",
        data={"text": "my work", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    detail = _api(client, student_token, "GET", "/api/v1/assignments/1").json()
    assert detail["my_submission"]["text"] == "my work"
    assert "submissions" not in detail  # students never see the class-wide list

    # students cannot grade
    denied = _api(
        client, student_token, "POST", "/api/v1/submissions/1/grade",
        json={"grade": 10, "feedback": "self-graded!"},
    )
    assert denied.status_code == 403

    _login_admin(client)
    admin_token = _get_token(client)
    detail = _api(client, admin_token, "GET", "/api/v1/assignments/1").json()
    assert detail["submissions"][0]["text"] == "my work"
    graded = _api(
        client, admin_token, "POST", "/api/v1/submissions/1/grade",
        json={"grade": 9, "feedback": "Solid"},
    )
    assert graded.json()["grade"] == 9
    _login_student(client, student)
    assert client.get("/assignments/1").text.count("Grade: 9/10") == 1


def test_quiz_read_hides_answers_from_students(client, admin, student):
    class_id, code = make_class(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/quizzes/new",
        data={"title": "Q", "instructions": "", "due_at": "", "csrf": token},
        follow_redirects=False,
    )
    client.post(
        "/quizzes/1/questions",
        data={"prompt": "2+2?", "kind": "mc", "choices": "3\n4", "correct_index": "1", "points": "1", "csrf": token},
        follow_redirects=False,
    )
    client.post("/quizzes/1/publish", data={"csrf": token}, follow_redirects=False)

    _login_student(client, student)
    join_class(client, code)
    student_token = _get_token(client)
    payload = _api(client, student_token, "GET", "/api/v1/quizzes/1").json()
    assert payload["questions"][0]["prompt"] == "2+2?"
    assert payload["questions"][0]["choices"] == ["3", "4"]
    assert "correct" not in payload["questions"][0]

    _login_admin(client)
    admin_token = _get_token(client)
    payload = _api(client, admin_token, "GET", "/api/v1/quizzes/1").json()
    assert payload["questions"][0]["correct"] == {"index": 1}


def test_quiz_api_submission_autogrades(client, admin, student):
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
    student_token = _get_token(client)
    result = _api(
        client, student_token, "POST", "/api/v1/quizzes/1/submit",
        json={"answers": {"1": "1"}},
    ).json()
    assert result["score"] == 2
    assert result["results"][0]["correct"] is True

    # the one attempt is spent
    again = _api(
        client, student_token, "POST", "/api/v1/quizzes/1/submit",
        json={"answers": {"1": "1"}},
    )
    assert again.status_code == 409


def test_api_notifications(client, admin, student):
    class_id, code = make_class(client)
    _login_student(client, student)
    join_class(client, code)
    _login_admin(client)
    token = get_csrf(client)
    client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": "Read chapter 2", "instructions": "", "due_at": "", "points": "", "csrf": token},
        follow_redirects=False,
    )
    _login_student(client, student)
    student_token = _get_token(client)
    rows = _api(client, student_token, "GET", "/api/v1/notifications").json()
    assert any("Read chapter 2" in row["message"] for row in rows)


def test_api_membership_enforced(client, admin, student):
    class_id, _ = make_class(client)
    _login_student(client, student)
    token = _get_token(client)
    assert _api(client, token, "GET", "/api/v1/classes/1").status_code == 403
    # no assignment was created in this fresh database -> 404 (object hidden)
    assert _api(client, token, "GET", "/api/v1/assignments/1").status_code == 404
