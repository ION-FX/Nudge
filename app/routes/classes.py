from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import security
from ..db import Announcement, Assignment, ClassRoom, Enrollment, Material, Quiz, QuizAttempt, QuizQuestion, Submission, User
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
    if klass.archived:
        return redirect("/join", flash="That class is archived and no longer accepts students.", category="err")
    if db.query(Enrollment).filter_by(class_id=klass.id, student_id=user.id).first():
        return redirect(f"/classes/{klass.id}", flash=f"You're already in {klass.name}.")
    db.add(Enrollment(class_id=klass.id, student_id=user.id))
    db.commit()
    return redirect(f"/classes/{klass.id}", flash=f"Joined {klass.name}!")


@router.get("/join")
def join_page(request: Request, code: str = "", db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    if user.role != "student":
        return redirect("/dashboard")
    return render(request, db, "join.html", prefill=code.strip().upper()[:12])


def _require_class_teacher(db: Session, user, klass: ClassRoom) -> None:
    if user.role != "teacher" or klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can do that.")


@router.get("/classes/{cid}/edit")
def class_edit_page(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    return render(request, db, "class_edit.html", klass=klass, error=None)


@router.post("/classes/{cid}/edit")
def class_edit(
    cid: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    name = name.strip()
    if not name or len(name) > 160:
        return render(request, db, "class_edit.html", klass=klass, error="Please give the class a name.", status_code=400)
    klass.name = name
    klass.description = description.strip()[:2000]
    db.commit()
    return redirect(f"/classes/{klass.id}", flash="Class updated.")


@router.post("/classes/{cid}/archive")
def class_archive(cid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    klass.archived = not klass.archived
    db.commit()
    if klass.archived:
        return redirect("/dashboard", flash=f"'{klass.name}' moved to archived classes.")
    return redirect(f"/classes/{klass.id}", flash=f"'{klass.name}' is active again.")


@router.post("/classes/{cid}/regen-code")
def class_regen_code(cid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    klass.join_code = _gen_join_code(db)
    db.commit()
    return redirect(f"/classes/{klass.id}", flash=f"New join code: {klass.join_code}")


@router.post("/classes/{cid}/remove")
def class_remove_student(
    cid: int,
    request: Request,
    student_id: int = Form(0),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    enrollment = (
        db.query(Enrollment).filter_by(class_id=klass.id, student_id=student_id).first()
    )
    if not enrollment:
        return redirect(f"/classes/{klass.id}", flash="That student isn't in this class.", category="err")
    student = db.get(User, student_id)
    db.delete(enrollment)
    db.commit()
    return redirect(f"/classes/{klass.id}", flash=f"Removed {student.name} from the class.")


@router.get("/classes/{cid}/students/{sid}")
def student_detail(cid: int, sid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    student = db.get(User, sid)
    if not student or not db.query(Enrollment).filter_by(class_id=klass.id, student_id=sid).first():
        raise HTTPException(status_code=404, detail="Student not found in this class.")

    assignments = (
        db.query(Assignment).filter(Assignment.class_id == klass.id).order_by(Assignment.due_at, Assignment.id).all()
    )
    assignment_rows = []
    for a in assignments:
        sub = db.query(Submission).filter_by(assignment_id=a.id, student_id=sid).first()
        assignment_rows.append((a, sub))

    quizzes = (
        db.query(Quiz).filter(Quiz.class_id == klass.id, Quiz.published.is_(True)).order_by(Quiz.id).all()
    )
    quiz_rows = []
    for q in quizzes:
        attempt = db.query(QuizAttempt).filter_by(quiz_id=q.id, student_id=sid).first()
        total = sum(qq.points for qq in db.query(QuizQuestion).filter(QuizQuestion.quiz_id == q.id).all())
        quiz_rows.append((q, attempt, total))

    return render(
        request,
        db,
        "student_detail.html",
        klass=klass,
        student=student,
        assignment_rows=assignment_rows,
        quiz_rows=quiz_rows,
    )


@router.get("/classes/{cid}")
def class_detail(cid: int, request: Request, db: Session = Depends(get_db), tab: str = "stream"):
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

    announcements = (
        db.query(Announcement)
        .filter(Announcement.class_id == klass.id)
        .order_by(Announcement.pinned.desc(), Announcement.created_at.desc())
        .all()
    )

    quizzes = db.query(Quiz).filter(Quiz.class_id == klass.id).order_by(Quiz.id.desc()).all()

    events = []
    for a in assignments:
        events.append((a.created_at, "📝", f"Posted assignment: {a.title}", f"/assignments/{a.id}"))
    for m in materials:
        events.append((m.created_at, "📄", f"Uploaded material: {m.title}", f"/materials/{m.id}"))
    for q in quizzes:
        events.append((q.created_at, "🧪", f"Created quiz: {q.title}", f"/quizzes/{q.id}"))
    for n in announcements:
        events.append((n.created_at, "📢", f"Announcement: {n.title}", f"/classes/{klass.id}#announcements"))
    events.sort(key=lambda e: e[0], reverse=True)
    activity = events[:8]
    quiz_rows = []
    if quizzes:
        quiz_ids = [q.id for q in quizzes]
        if is_teacher:
            attempt_counts = dict(
                db.query(QuizAttempt.quiz_id, func.count(QuizAttempt.id))
                .filter(QuizAttempt.quiz_id.in_(quiz_ids))
                .group_by(QuizAttempt.quiz_id)
                .all()
            )
            quiz_rows = [(q, attempt_counts.get(q.id, 0), None) for q in quizzes]
        else:
            attempts = {
                a.quiz_id: a
                for a in db.query(QuizAttempt)
                .filter(QuizAttempt.student_id == user.id, QuizAttempt.quiz_id.in_(quiz_ids))
                .all()
            }
            quiz_rows = [(q, 0, attempts.get(q.id)) for q in quizzes]

    stream = []
    for n in announcements:
        stream.append({"when": n.created_at, "icon": "📢", "kind_label": "Announcement", "kind": "announcement",
                       "title": n.title, "body": n.body, "link": "", "pinned": n.pinned,
                       "meta": f"by {db.get(User, n.author_id).name}", "announcement_id": n.id})
    for a in assignments:
        meta_bits = []
        if a.due_at:
            meta_bits.append(f"due {a.due_at:%b %d}")
        if a.points is not None:
            meta_bits.append(f"{a.points} pts")
        stream.append({"when": a.created_at, "icon": "📝", "kind_label": "Assignment", "kind": "assignment",
                       "title": a.title, "body": a.instructions, "link": f"/assignments/{a.id}",
                       "pinned": False, "meta": " · ".join(meta_bits)})
    for q in quizzes:
        stream.append({"when": q.created_at, "icon": "🧪", "kind_label": "Quiz", "kind": "quiz",
                       "title": q.title, "body": q.instructions, "link": f"/quizzes/{q.id}",
                       "pinned": False, "meta": "published" if q.published else "draft"})
    for m in materials:
        stream.append({"when": m.created_at, "icon": "📄", "kind_label": "Material", "kind": "material",
                       "title": m.title, "body": m.description, "link": f"/materials/{m.id}",
                       "pinned": False, "meta": "AI-readable" if m.text_content else ""})
    stream.sort(key=lambda item: (not item["pinned"], -item["when"].timestamp()))

    if tab not in ("stream", "assignments", "quizzes", "materials", "people"):
        tab = "stream"

    return render(
        request,
        db,
        "class_detail.html",
        klass=klass,
        teacher=db.get(User, klass.teacher_id),
        is_teacher=is_teacher,
        tab=tab,
        stream=stream,
        materials=materials,
        assignment_rows=assignment_rows,
        quiz_rows=quiz_rows,
        announcements=announcements,
        activity=activity,
        roster=roster,
        roster_count=roster_count,
    )
