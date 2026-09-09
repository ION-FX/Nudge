from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import security
from ..db import Assignment, ClassRoom, Enrollment, Material, Submission, User
from ..deps import ensure_class_member, get_db, page_user
from ..web import redirect, render

router = APIRouter()

_JOIN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_join_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(6))
        if not db.query(ClassRoom).filter(ClassRoom.join_code == code).first():
            return code


def _require_teacher(user) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can do that.")


@router.get("/classes/new")
def class_new_page(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    _require_teacher(user)
    return render(request, db, "class_new.html", error=None)


@router.post("/classes/new")
def class_new(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    name = name.strip()
    if not name or len(name) > 160:
        return render(request, db, "class_new.html", error="Please give the class a name.", status_code=400)
    klass = ClassRoom(
        name=name,
        description=description.strip()[:2000],
        join_code=_gen_join_code(db),
        teacher_id=user.id,
    )
    db.add(klass)
    db.commit()
    return redirect(f"/classes/{klass.id}", flash=f"Class '{name}' created! Share the join code with students.")


@router.post("/classes/join")
def class_join(
    request: Request,
    code: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    if user.role != "student":
        return redirect("/dashboard", flash="Teachers can't join classes — create one instead.", category="err")
    klass = db.query(ClassRoom).filter(ClassRoom.join_code == code.strip().upper()).first()
    if not klass:
        return redirect("/join", flash="No class found with that join code.", category="err")
    if db.query(Enrollment).filter_by(class_id=klass.id, student_id=user.id).first():
        return redirect(f"/classes/{klass.id}", flash=f"You're already in {klass.name}.")
    db.add(Enrollment(class_id=klass.id, student_id=user.id))
    db.commit()
    return redirect(f"/classes/{klass.id}", flash=f"Joined {klass.name}!")


@router.get("/join")
def join_page(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    if user.role != "student":
        return redirect("/dashboard")
    return render(request, db, "join.html")


@router.get("/classes/{cid}")
def class_detail(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    ensure_class_member(db, user, klass)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id

    materials = (
        db.query(Material).filter(Material.class_id == klass.id).order_by(Material.created_at.desc()).all()
    )
    assignments = (
        db.query(Assignment).filter(Assignment.class_id == klass.id).order_by(Assignment.created_at.desc()).all()
    )

    roster = []
    roster_count = 0
    if is_teacher:
        roster = (
            db.query(Enrollment, User)
            .join(User, Enrollment.student_id == User.id)
            .filter(Enrollment.class_id == klass.id)
            .order_by(Enrollment.created_at)
            .all()
        )
        roster_count = len(roster)

    assignment_rows = []
    if assignments:
        ids = [a.id for a in assignments]
        if is_teacher:
            counts = dict(
                db.query(Submission.assignment_id, func.count(Submission.id))
                .filter(Submission.assignment_id.in_(ids))
                .group_by(Submission.assignment_id)
                .all()
            )
            assignment_rows = [(a, counts.get(a.id, 0), None) for a in assignments]
        else:
            subs = {
                s.assignment_id: s
                for s in db.query(Submission)
                .filter(Submission.student_id == user.id, Submission.assignment_id.in_(ids))
                .all()
            }
            assignment_rows = [(a, 0, subs.get(a.id)) for a in assignments]

    return render(
        request,
        db,
        "class_detail.html",
        klass=klass,
        teacher=db.get(User, klass.teacher_id),
        is_teacher=is_teacher,
        materials=materials,
        assignment_rows=assignment_rows,
        roster=roster,
        roster_count=roster_count,
    )
