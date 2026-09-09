"""Tests for DB-backed settings and their .env fallbacks."""
from app import config
from app.db import SessionLocal
from app.settings import (
    get_setting,
    resolve_api_key,
    resolve_invite_code,
    resolve_model,
    set_setting,
    users_exist,
)


def test_get_set_setting_roundtrip():
    db = SessionLocal()
    assert get_setting(db, "nope") == ""
    set_setting(db, "nope", "value1")
    assert get_setting(db, "nope") == "value1"
    set_setting(db, "nope", "value2")  # update path
    assert get_setting(db, "nope") == "value2"
    db.close()


def test_resolve_falls_back_to_env(monkeypatch):
    db = SessionLocal()
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "env-key")
    monkeypatch.setattr(config, "MODEL", "env-model")
    monkeypatch.setattr(config, "TEACHER_INVITE_CODE", "ENVCODE")
    assert resolve_api_key(db) == "env-key"
    assert resolve_model(db) == "env-model"
    assert resolve_invite_code(db) == "ENVCODE"
    db.close()


def test_resolve_prefers_db_over_env(monkeypatch):
    db = SessionLocal()
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "env-key")
    monkeypatch.setattr(config, "MODEL", "env-model")
    set_setting(db, "openrouter_api_key", " db-key ")
    set_setting(db, "model", " db-model ")
    assert resolve_api_key(db) == "db-key"
    assert resolve_model(db) == "db-model"
    db.close()


def test_users_exist_reflects_database(client):
    db = SessionLocal()
    assert users_exist(db) is False
    db.close()
    client.post(
        "/setup",
        data={"name": "A", "email": "a@t.io", "password": "password1", "invite_code": "XYZW", "api_key": "", "model": ""},
    )
    db = SessionLocal()
    assert users_exist(db) is True
    db.close()
