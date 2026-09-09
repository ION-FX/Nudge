from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets

from fastapi import Response
from sqlalchemy.orm import Session

from .db import UserSession, now

SESSION_COOKIE = "nudge_session"
FLASH_COOKIE = "nudge_flash"
SESSION_DAYS = 30
_SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT_PARAMS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT_PARAMS)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session(db: Session, user_id: int) -> UserSession:
    sess = UserSession(
        token=secrets.token_urlsafe(32),
        user_id=user_id,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=now() + dt.timedelta(days=SESSION_DAYS),
    )
    db.add(sess)
    db.commit()
    return sess


def get_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    sess = db.get(UserSession, token)
    if sess and sess.expires_at > now():
        return sess
    return None


def destroy_session(db: Session, token: str | None) -> None:
    if token and (sess := db.get(UserSession, token)):
        db.delete(sess)
        db.commit()


def attach_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/"
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def csrf_ok(supplied: str | None, sess: UserSession | None) -> bool:
    return bool(sess and supplied and hmac.compare_digest(supplied, sess.csrf_token))


def set_flash(response: Response, message: str, category: str = "ok") -> None:
    payload = base64.urlsafe_b64encode(json.dumps({"m": message, "c": category}).encode()).decode()
    response.set_cookie(FLASH_COOKIE, payload, max_age=120, httponly=True, samesite="lax", path="/")


def pop_flash(request) -> dict | None:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(raw.encode()))
        return {"message": str(data.get("m", "")), "category": str(data.get("c", "ok"))}
    except Exception:
        return None
