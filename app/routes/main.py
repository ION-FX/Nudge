from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import Assignment, ClassRoom, Enrollment, Material, Submission, User
from ..deps import get_db, page_user
from ..web import redirect, render

router = APIRouter()


@router.get("/")
def landing(request: Request, db: Session = Depends(get_db)):
    from ..deps import auth_context

    if auth_context(request, db)[0]:
        return redirect("/dashboard")
    return render(request, db, "landing.html")


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)

    if user.role == "teacher":
        classes = (
            db.query(ClassRoom)
            .filter(ClassRoom.teacher_id == user.id)
            .order_by(ClassRoom.created_at.desc())
            .all()
        )
        class_stats = []
        for c in classes:
            class_stats.append(
                (
                    c,
                    {
                        "students": db.query(Enrollment).filter_by(class_id=c.id).count(),
                        "materials": db.query(Material).filter_by(class_id=c.id).count(),
                        "assignments": db.query(Assignment).filter_by(class_id=c.id).count(),
                    },
                )
            )
        return render(request, db, "dashboard.html", class_stats=class_stats)

    enrollments = (
        db.query(Enrollment).filter(Enrollment.student_id == user.id).order_by(Enrollment.created_at).all()
    )
    classes = [db.get(ClassRoom, e.class_id) for e in enrollments]
    class_ids = [c.id for c in classes]

    upcoming = []
    if class_ids:
        cutoff = dt.datetime.now() - dt.timedelta(days=3)
        assignments = (
            db.query(Assignment)
            .filter(Assignment.class_id.in_(class_ids), Assignment.due_at.isnot(None))
            .filter(Assignment.due_at >= cutoff)
            .order_by(Assignment.due_at)
            .limit(10)
            .all()
        )
        subs = {
            s.assignment_id: s
            for s in db.query(Submission)
            .filter(Submission.student_id == user.id, Submission.assignment_id.in_([a.id for a in assignments]))
            .all()
        }
        upcoming = [(a, db.get(ClassRoom, a.class_id), subs.get(a.id)) for a in assignments]

    teacher_names = {c.id: db.get(User, c.teacher_id).name for c in classes}
    return render(request, db, "dashboard.html", classes=classes, upcoming=upcoming, teacher_names=teacher_names)
