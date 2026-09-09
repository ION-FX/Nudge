"""Unit tests for the security primitives: scrypt hashing, sessions, CSRF, flash."""
import datetime as dt

from app import security
from app.db import SessionLocal, User, now


def _make_user(db):
    user = User(email="sec@test.com", name="Sec", role="student", password_hash=security.hash_password("hunter22"))
    db.add(user)
    db.commit()
    return user


def test_password_roundtrip():
    stored = security.hash_password("s3cret password!")
    assert stored != "s3cret password!"
    assert "$" in stored  # salt$digest
    assert security.verify_password("s3cret password!", stored)


def test_password_rejects_wrong():
    stored = security.hash_password("correct horse")
    assert not security.verify_password("wrong horse", stored)
    assert not security.verify_password("", stored)
    assert not security.verify_password("correct horse ", stored)


def test_password_salts_are_unique():
    assert security.hash_password("same") != security.hash_password("same")


def test_password_malformed_stored_value():
    assert not security.verify_password("x", "not-a-hash")
    assert not security.verify_password("x", "zz$$")


def test_session_roundtrip():
    db = SessionLocal()
    user = _make_user(db)
    sess = security.create_session(db, user.id)
    assert len(sess.token) >= 32
    fetched = security.get_session(db, sess.token)
    assert fetched is not None and fetched.user_id == user.id
    security.destroy_session(db, sess.token)
    assert security.get_session(db, sess.token) is None
    db.close()


def test_session_expiry_rejected():
    db = SessionLocal()
    user = _make_user(db)
    sess = security.create_session(db, user.id)
    sess.expires_at = now() - dt.timedelta(minutes=1)
    db.commit()
    assert security.get_session(db, sess.token) is None
    db.close()


def test_session_missing_token():
    db = SessionLocal()
    assert security.get_session(db, None) is None
    assert security.get_session(db, "nope") is None
    db.close()


def test_csrf_ok():
    assert security.csrf_ok("tok", None) is False
    sess = type("S", (), {"csrf_token": "tok"})()
    assert security.csrf_ok("tok", sess) is True
    assert security.csrf_ok("bad", sess) is False
    assert security.csrf_ok(None, sess) is False


def test_flash_roundtrip():
    from fastapi import Response

    response = Response()
    security.set_flash(response, "Well done!", category="ok")
    raw = response.headers.get("set-cookie")
    assert raw and "nudge_flash" in raw

    request = type("R", (), {"cookies": {"nudge_flash": raw.split(";")[0].split("=", 1)[1]}})()
    flash = security.pop_flash(request)
    assert flash == {"message": "Well done!", "category": "ok"}


def test_flash_garbage_cookie_is_ignored():
    request = type("R", (), {"cookies": {"nudge_flash": "!!!not-base64!!!"}})()
    assert security.pop_flash(request) is None


def test_setup_gate_redirects_anonymous(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}
