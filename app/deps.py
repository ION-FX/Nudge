from __future__ import annotations

import datetime as dt

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import security
from .db import ClassRoom, Enrollment, SessionLocal, User, UserSession


class PageRedirect(Exception):
    """Raised in page handlers when the request should be sent elsewhere (e.g. /login)."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(url)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def auth_context(request: Request, db: Session) -> tuple[User | None, UserSession | None]:
    sess = security.get_session(db, request.cookies.get(security.SESSION_COOKIE))
    if not sess:
        return None, None
    user = db.get(User, sess.user_id)
    if not user:
        return None, None
    return user, sess


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return auth_context(request, db)[0]


def page_user(request: Request, db: Session) -> tuple[User, UserSession]:
    user, sess = auth_context(request, db)
    if not user:
        raise PageRedirect("/login")
    return user, sess


def ensure_class_member(db: Session, user: User, klass: ClassRoom) -> None:
    if user.role == "teacher" and klass.teacher_id == user.id:
        return
    if user.role == "student" and (
        db.query(Enrollment).filter_by(class_id=klass.id, student_id=user.id).first()
    ):
        return
    raise HTTPException(status_code=403, detail="You're not a member of this class.")


def parse_due(raw: str | None) -> dt.datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw)
    except ValueError:
        return None


def parse_points(raw: str | None) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return None
