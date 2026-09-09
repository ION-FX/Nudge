"""Setup wizard + registration + login flows."""
from tests.conftest import INVITE, get_csrf, login, logout


def test_setup_creates_admin_and_locks(client):
    response = client.post(
        "/setup",
        data={
            "name": "Founder",
            "email": "founder@nudge.test",
            "password": "founder-pass",
            "invite_code": INVITE,
            "api_key": "",
            "model": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert client.get("/dashboard").status_code == 200
    # setup page is now locked
    locked = client.get("/setup", follow_redirects=False)
    assert locked.status_code == 303
    assert locked.headers["location"] == "/login"
    # posting to setup again can't create a second account
    again = client.post(
        "/setup",
        data={"name": "Sneak", "email": "sneak@nudge.test", "password": "password1", "invite_code": "X"},
        follow_redirects=False,
    )
    assert again.status_code == 303


def test_setup_validates_password(client):
    response = client.post(
        "/setup",
        data={"name": "A", "email": "a@t.io", "password": "short", "invite_code": "CODE1234", "api_key": "", "model": ""},
    )
    assert response.status_code == 400
    assert "at least 8" in response.text


def test_setup_rejects_bogus_api_key(client):
    response = client.post(
        "/setup",
        data={
            "name": "A",
            "email": "a@t.io",
            "password": "password1",
            "invite_code": "CODE1234",
            "api_key": "not-an-openrouter-key",
            "model": "",
        },
    )
    assert response.status_code == 400
    assert "sk-or-" in response.text


def test_register_student_no_code_needed(client, admin):
    response = client.post(
        "/register",
        data={"name": "Kid", "email": "kid@nudge.test", "password": "password1", "role": "student", "teacher_code": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_teacher_registration_requires_invite_code(client, admin):
    bad = client.post(
        "/register",
        data={"name": "Fake", "email": "fake@nudge.test", "password": "password1", "role": "teacher", "teacher_code": "WRONG"},
    )
    assert bad.status_code == 400
    assert "invite code" in bad.text

    good = client.post(
        "/register",
        data={"name": "Real", "email": "real@nudge.test", "password": "password1", "role": "teacher", "teacher_code": INVITE.lower()},
        follow_redirects=False,
    )
    assert good.status_code == 303  # case-insensitive match


def test_duplicate_email_rejected(client, admin):
    response = client.post(
        "/register",
        data={"name": "Dup", "email": "admin@nudge.test", "password": "password1", "role": "student", "teacher_code": ""},
    )
    assert response.status_code == 400
    assert "already registered" in response.text


def test_login_logout_flow(client, admin):
    assert login(client, "admin@nudge.test", "wrong-password").status_code == 400
    response = login(client, "admin@nudge.test", "admin-pass-1")
    assert response.status_code == 303
    assert client.get("/dashboard").status_code == 200
    assert logout(client).status_code == 303
    page = client.get("/dashboard", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/login"


def test_csrf_required_for_logout(client, admin):
    response = client.post("/logout", data={"csrf": "wrong"}, follow_redirects=False)
    assert response.status_code == 403


def test_profile_name_and_password(client, admin):
    token = get_csrf(client)
    assert client.post("/profile/name", data={"name": "Renamed", "csrf": token}, follow_redirects=False).status_code == 303
    assert "Renamed" in client.get("/profile").text

    wrong = client.post("/profile/password", data={"current": "nope", "new": "new-password-1", "csrf": token}, follow_redirects=False)
    assert wrong.headers["location"].endswith("/profile") and wrong.status_code == 303
    assert "incorrect" in client.get("/profile", follow_redirects=True).text

    ok = client.post("/profile/password", data={"current": "admin-pass-1", "new": "new-password-1", "csrf": token}, follow_redirects=False)
    assert ok.status_code == 303
    assert login(client, "admin@nudge.test", "new-password-1").status_code == 303
