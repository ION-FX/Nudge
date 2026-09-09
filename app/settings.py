"""DB-backed settings that override .env defaults — set via the first-run /setup page."""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import config
from .db import Setting, User


def users_exist(db: Session) -> bool:
    return db.query(User).count() > 0


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def resolve_api_key(db: Session) -> str:
    return get_setting(db, "openrouter_api_key").strip() or config.OPENROUTER_API_KEY


def resolve_model(db: Session) -> str:
    return get_setting(db, "model").strip() or config.MODEL


def resolve_invite_code(db: Session) -> str:
    return get_setting(db, "teacher_invite_code").strip() or config.TEACHER_INVITE_CODE
