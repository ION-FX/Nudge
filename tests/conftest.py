"""Shared fixtures: isolated temp database/uploads per test, TestClient, auth helpers."""
import os
import tempfile

# Isolate storage BEFORE any app import happens.
_TMP = tempfile.mkdtemp(prefix="nudge-tests-")
os.environ["NUDGE_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["NUDGE_UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["NUDGE_DATA_DIR"] = _TMP
os.environ["NUDGE_SKIP_MODEL_CHECK"] = "1"
os.environ["TEACHER_INVITE_CODE"] = "TESTCODE"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN_EMAIL = "admin@nudge.test"
ADMIN_PASSWORD = "admin-pass-1"
INVITE = "TSTCODE1"
STUDENT_EMAIL = "student@nudge.test"
STUDENT_PASSWORD = "student-pass-1"


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts from a clean database and empty rate-limit counters."""
    from app.ai import _rate_hits
    from app.db import Base, engine, init_db

    Base.metadata.drop_all(engine)
    init_db()
    _rate_hits.clear()
    yield
    _rate_hits.clear()


@pytest.fixture()
def client():
    from app import app as fastapp
    from app.db import init_db

    init_db()
    with TestClient(fastapp) as testclient:
        yield testclient


@pytest.fixture()
def admin(client):
    """The instance admin (teacher), created through /setup like a real user."""
    response = client.post(
        "/setup",
        data={
            "name": "Admin Teacher",
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "invite_code": INVITE,
            "api_key": "",
            "model": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "name": "Admin Teacher", "id": 1}


@pytest.fixture()
def student(client, admin):
    """A registered student."""
    response = client.post(
        "/register",
        data={
            "name": "Stu Dent",
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "role": "student",
            "teacher_code": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return {"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD, "name": "Stu Dent", "id": 2}


def login(client, email, password):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def login_as(client, email, password):
    """Switch sessions safely: log out whoever is active, then log in as the user."""
    page = client.get("/profile")
    marker = 'name="csrf" value="'
    if marker in page.text:  # someone is logged in
        client.post("/logout", data={"csrf": page.text.split(marker)[1].split('"')[0]}, follow_redirects=False)
    response = login(client, email, password)
    assert response.status_code == 303, f"login as {email} failed: {response.status_code}"


def logout(client):
    page = client.get("/profile")
    marker = 'name="csrf" value="'
    if marker not in page.text:
        return None  # nobody logged in
    return client.post("/logout", data={"csrf": page.text.split(marker)[1].split('"')[0]}, follow_redirects=False)


def get_csrf(client, path="/profile"):
    page = client.get(path)
    assert page.status_code == 200, f"cannot fetch csrf from {path}: {page.status_code}"
    marker = 'name="csrf" value="'
    assert marker in page.text, f"no csrf token on {path} — are you logged in?"
    return page.text.split(marker)[1].split('"')[0]


def make_class(client, name="Test Class", description=""):
    """The admin teacher creates a class; returns (class_id, join_code)."""
    login_as(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    token = get_csrf(client)
    response = client.post(
        "/classes/new",
        data={"name": name, "description": description, "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    class_id = response.headers["location"].rsplit("/", 1)[-1]
    page = client.get(f"/classes/{class_id}")
    join_code = page.text.split('code-big">')[1].split("<")[0].strip()
    return int(class_id), join_code


def join_class(client, code):
    login_as(client, STUDENT_EMAIL, STUDENT_PASSWORD)
    token = get_csrf(client)
    return client.post("/classes/join", data={"code": code, "csrf": token}, follow_redirects=False)
