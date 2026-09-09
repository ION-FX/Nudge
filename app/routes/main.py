from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import Assignment, ClassRoom, Enrollment, Material, Quiz, Submission, User
from ..deps import get_db, page_user
from ..web import redirect, render

router = APIRouter()


@router.get("/")
def landing(request: Request, db: Session = Depends(get_db)):
    from ..deps import auth_context

    if auth_context(request, db)[0]:
        return redirect("/dashboard")
    return render(request, db, "landing.html")


def _member_class_ids(db: Session, user) -> list[int]:
    if user.role == "teacher":
        rows = db.query(ClassRoom).filter(ClassRoom.teacher_id == user.id).all()
        return [c.id for c in rows]
    rows = db.query(Enrollment).filter(Enrollment.student_id == user.id).all()
    return [e.class_id for e in rows]


@router.get("/calendar")
def calendar_view(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    class_ids = _member_class_ids(db, user)
    cutoff = dt.datetime.now() - dt.timedelta(days=14)
    items = []
    if class_ids:
        classes = {c.id: c for c in db.query(ClassRoom).filter(ClassRoom.id.in_(class_ids)).all()}
        for a in (
            db.query(Assignment)
            .filter(Assignment.class_id.in_(class_ids), Assignment.due_at.isnot(None), Assignment.due_at >= cutoff)
            .all()
        ):
            items.append({"due": a.due_at, "kind": "📝 Assignment", "title": a.title,
                          "where": classes[a.class_id].name, "link": f"/assignments/{a.id}"})
        for q in (
            db.query(Quiz)
            .filter(Quiz.class_id.in_(class_ids), Quiz.published.is_(True), Quiz.due_at.isnot(None), Quiz.due_at >= cutoff)
            .all()
        ):
            items.append({"due": q.due_at, "kind": "🧪 Quiz", "title": q.title,
                          "where": classes[q.class_id].name, "link": f"/quizzes/{q.id}"})
    items.sort(key=lambda item: item["due"])
    return render(request, db, "calendar.html", items=items)


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)

    if user.role == "teacher":
        classes = (
            db.query(ClassRoom)
            .filter(ClassRoom.teacher_id == user.id, ClassRoom.archived.is_(False))
            .order_by(ClassRoom.created_at.desc())
            .all()
        )
        archived = (
            db.query(ClassRoom)
            .filter(ClassRoom.teacher_id == user.id, ClassRoom.archived.is_(True))
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
        return render(request, db, "dashboard.html", class_stats=class_stats, archived=archived)

    enrollments = (
        db.query(Enrollment).filter(Enrollment.student_id == user.id).order_by(Enrollment.created_at).all()
    )
    classes = []
    for e in enrollments:
        c = db.get(ClassRoom, e.class_id)
        if c and not c.archived:
            classes.append(c)
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
