"""Assignment lifecycle: create, submit, late flag, resubmission, grading, edit/delete."""
from tests.conftest import get_csrf, join_class, login, logout, make_class


def _login_student(client, student):
    logout(client)
    login(client, student["email"], student["password"])


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _create_assignment(client, class_id, title="Task", due="", points="10", instructions="Do the thing."):
    token = get_csrf(client)
    response = client.post(
        f"/classes/{class_id}/assignments/new",
        data={"title": title, "instructions": instructions, "due_at": due, "points": points, "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[-1])


def test_create_and_view_assignment(client, admin, student):
    class_id, code = make_class(client)
    assignment_id = _create_assignment(client, class_id, title="Essay", points="20")
    _login_student(client, student)
    join_class(client, code)
    page = client.get(f"/assignments/{assignment_id}")
    assert "Essay" in page.text
    assert "20 points" in page.text
    assert "Submit your work" in page.text


def test_submit_and_grade_loop(client, admin, student):
    class_id, code = make_class(client)
    assignment_id = _create_assignment(client, class_id)

    _login_student(client, student)
    join_class(client, code)
    token = get_csrf(client)
    response = client.post(
        f"/assignments/{assignment_id}/submit",
        data={"text": "My answer is 42.", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Submitted" in client.get(f"/assignments/{assignment_id}").text

    # teacher grades it
    _login_admin(client)
    token = get_csrf(client)
    page = client.get(f"/assignments/{assignment_id}")
    submission_id = page.text.split("submissions/")[1].split("/")[0]
    response = client.post(
        f"/submissions/{submission_id}/grade",
        data={"grade": "17", "feedback": "Nice reasoning.", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    # student sees grade + feedback + notification
    _login_student(client, student)
    page = client.get(f"/assignments/{assignment_id}")
    assert "Grade: 17/10" in page.text  # assignment defaulted to 10 points
    assert "Nice reasoning." in page.text
    assert "scored 17/10" in client.get("/notifications").text  # grade notification


def test_late_flag_and_resubmission_clears_grade(client, admin, student):
    class_id, code = make_class(client)
    assignment_id = _create_assignment(client, class_id, due="2020-01-01T00:00")

    _login_student(client, student)
    join_class(client, code)
    token = get_csrf(client)
    client.post(f"/assignments/{assignment_id}/submit", data={"text": "late work", "csrf": token}, follow_redirects=False)
    assert "late" in client.get(f"/assignments/{assignment_id}").text

    _login_admin(client)
    token = get_csrf(client)
    page = client.get(f"/assignments/{assignment_id}")
    submission_id = page.text.split("submissions/")[1].split("/")[0]
    client.post(f"/submissions/{submission_id}/grade", data={"grade": "5", "feedback": "", "csrf": token}, follow_redirects=False)

    _login_student(client, student)
    client.post(
        f"/assignments/{assignment_id}/submit",
        data={"text": "resubmitted!", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    page = client.get(f"/assignments/{assignment_id}")
    assert "resubmitted!" in page.text
    assert "Grade:" not in page.text  # resubmission cleared the grade


def test_empty_submission_rejected(client, admin, student):
    class_id, code = make_class(client)
    assignment_id = _create_assignment(client, class_id)
    _login_student(client, student)
    join_class(client, code)
    response = client.post(
        f"/assignments/{assignment_id}/submit",
        data={"text": "", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Write some text" in client.get(f"/assignments/{assignment_id}", follow_redirects=True).text


def test_edit_and_delete_assignment(client, admin, student):
    class_id, code = make_class(client)
    assignment_id = _create_assignment(client, class_id, title="Old title")

    token = get_csrf(client)
    response = client.post(
        f"/assignments/{assignment_id}/edit",
        data={"title": "New title", "instructions": "Updated", "due_at": "", "points": "5", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "New title" in client.get(f"/assignments/{assignment_id}").text

    _login_student(client, student)
    join_class(client, code)
    client.post(f"/assignments/{assignment_id}/submit", data={"text": "work", "csrf": get_csrf(client)}, follow_redirects=False)

    _login_admin(client)
    delete = client.post(f"/assignments/{assignment_id}/delete", data={"csrf": get_csrf(client)}, follow_redirects=False)
    assert delete.status_code == 303
    assert client.get(f"/assignments/{assignment_id}").status_code == 404


def test_outsider_cannot_see_assignment(client, admin):
    class_id, _ = make_class(client)
    assignment_id = _create_assignment(client, class_id)
    logout(client)  # the admin session is a member; a true outsider is not
    assert client.get(f"/assignments/{assignment_id}", follow_redirects=False).status_code == 303
