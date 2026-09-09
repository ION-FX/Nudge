"""Global search across the classes, materials, assignments and announcements you can see."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import Announcement, Assignment, ClassRoom, Enrollment, Material
from ..deps import get_db, page_user
from ..web import render

router = APIRouter()


def _member_class_ids(db: Session, user) -> list[int]:
    if user.role == "teacher":
        rows = db.query(ClassRoom).filter(ClassRoom.teacher_id == user.id).all()
        return [c.id for c in rows]
    rows = db.query(Enrollment).filter(Enrollment.student_id == user.id).all()
    return [e.class_id for e in rows]


@router.get("/search")
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    q = q.strip()
    results = None
    if q:
        like = f"%{q}%"
        class_ids = _member_class_ids(db, user)

        class_hits = (
            db.query(ClassRoom)
            .filter(ClassRoom.id.in_(class_ids or [0]))
            .filter(ClassRoom.name.like(like) | ClassRoom.description.like(like))
            .all()
        )
        material_hits = (
            db.query(Material)
            .filter(Material.class_id.in_(class_ids or [0]))
            .filter(Material.title.like(like) | Material.description.like(like) | Material.text_content.like(like))
            .order_by(Material.created_at.desc())
            .limit(25)
            .all()
        )
        assignment_hits = (
            db.query(Assignment)
            .filter(Assignment.class_id.in_(class_ids or [0]))
            .filter(Assignment.title.like(like) | Assignment.instructions.like(like))
            .order_by(Assignment.created_at.desc())
            .limit(25)
            .all()
        )
        announcement_hits = (
            db.query(Announcement)
            .filter(Announcement.class_id.in_(class_ids or [0]))
            .filter(Announcement.title.like(like) | Announcement.body.like(like))
            .order_by(Announcement.created_at.desc())
            .limit(25)
            .all()
        )
        classes_by_id = {c.id: c for c in db.query(ClassRoom).filter(ClassRoom.id.in_(class_ids or [0])).all()}
        results = {
            "classes": class_hits,
            "materials": [(m, classes_by_id.get(m.class_id)) for m in material_hits],
            "assignments": [(a, classes_by_id.get(a.class_id)) for a in assignment_hits],
            "announcements": [(n, classes_by_id.get(n.class_id)) for n in announcement_hits],
        }

    return render(request, db, "search.html", q=q, results=results)
