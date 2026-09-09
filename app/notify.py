"""In-app notification creation helpers (bell feed)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .db import Enrollment, Notification


def notify(db: Session, user_id: int, kind: str, message: str, link: str = "") -> None:
    db.add(Notification(user_id=user_id, kind=kind, message=message[:400], link=link[:500]))
    db.commit()


def notify_class_students(
    db: Session,
    class_id: int,
    kind: str,
    message: str,
    link: str = "",
    exclude_user_id: int | None = None,
) -> None:
    rows = db.query(Enrollment).filter(Enrollment.class_id == class_id).all()
    for row in rows:
        if exclude_user_id is not None and row.student_id == exclude_user_id:
            continue
        db.add(Notification(user_id=row.student_id, kind=kind, message=message[:400], link=link[:500]))
    db.commit()
