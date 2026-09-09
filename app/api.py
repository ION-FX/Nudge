"""JSON API (v1) — token-authenticated read/write access for integrations.

Auth: `Authorization: Bearer <api_token>` (token managed from the profile page).
Unlike the cookie-based pages, token requests are not cookie-bound, so no CSRF applies.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import (
    Assignment,
    ClassRoom,
    Enrollment,
    Material,
    Notification,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    Submission,
    User,
    now,
)
from .deps import get_db

router = APIRouter(prefix="/api/v1")


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def current_api_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    user = db.query(User).filter(User.api_token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return user


def _require_teacher(user: User) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required.")


def _member_class_ids(db: Session, user: User) -> list[int]:
    if user.role == "teacher":
        rows = db.query(ClassRoom).filter(ClassRoom.teacher_id == user.id).all()
        return [c.id for c in rows]
    rows = db.query(Enrollment).filter(Enrollment.student_id == user.id).all()
    return [e.class_id for e in rows]


def _member_class_or_404(db: Session, user: User, cid: int) -> ClassRoom:
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    if cid not in _member_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Not a member of this class.")
    return klass


# ---------- account ----------


@router.get("/me")
def me(user: User = Depends(current_api_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


@router.post("/me/token")
def rotate_token(request: Request, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    """Rotate the token used for THIS request; old token stops working immediately."""
    new_token = secrets.token_urlsafe(32)
    user.api_token = new_token
    db.commit()
    return {"token": new_token}


# ---------- classes ----------


@router.get("/classes")
def list_classes(user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    classes = (
        db.query(ClassRoom).filter(ClassRoom.id.in_(_member_class_ids(db, user) or [0])).order_by(ClassRoom.name).all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "archived": c.archived,
            "teacher": db.get(User, c.teacher_id).name,
            "join_code": c.join_code if user.role == "teacher" and c.teacher_id == user.id else None,
            "students": db.query(Enrollment).filter_by(class_id=c.id).count(),
            "assignments": db.query(Assignment).filter_by(class_id=c.id).count(),
            "materials": db.query(Material).filter_by(class_id=c.id).count(),
        }
        for c in classes
    ]


@router.get("/classes/{cid}")
def class_detail(cid: int, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    klass = _member_class_or_404(db, user, cid)
    assignments = db.query(Assignment).filter(Assignment.class_id == klass.id).all()
    quizzes = db.query(Quiz).filter(Quiz.class_id == klass.id, Quiz.published.is_(True)).all()
    materials = db.query(Material).filter(Material.class_id == klass.id).all()
    return {
        "id": klass.id,
        "name": klass.name,
        "description": klass.description,
        "join_code": klass.join_code if user.role == "teacher" and klass.teacher_id == user.id else None,
        "assignments": [{"id": a.id, "title": a.title, "due_at": a.due_at.isoformat() if a.due_at else None, "points": a.points} for a in assignments],
        "quizzes": [{"id": q.id, "title": q.title, "due_at": q.due_at.isoformat() if q.due_at else None} for q in quizzes],
        "materials": [{"id": m.id, "title": m.title, "readable": bool(m.text_content)} for m in materials],
    }


# ---------- assignments & submissions ----------


@router.get("/assignments/{aid}")
def assignment_detail(aid: int, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    assignment = db.get(Assignment, aid)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    klass = _member_class_or_404(db, user, assignment.class_id)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id
    payload = {
        "id": assignment.id,
        "class_id": klass.id,
        "title": assignment.title,
        "instructions": assignment.instructions,
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "points": assignment.points,
    }
    if is_teacher:
        payload["submissions"] = [
            {
                "id": s.id,
                "student": db.get(User, s.student_id).name,
                "text": s.text,
                "file": s.original_name or None,
                "late": s.late,
                "grade": s.grade,
                "feedback": s.feedback,
                "submitted_at": s.submitted_at.isoformat(),
            }
            for s in db.query(Submission).filter(Submission.assignment_id == assignment.id).all()
        ]
    else:
        sub = db.query(Submission).filter_by(assignment_id=assignment.id, student_id=user.id).first()
        payload["my_submission"] = (
            {
                "text": sub.text,
                "file": sub.original_name or None,
                "late": sub.late,
                "grade": sub.grade,
                "feedback": sub.feedback,
                "submitted_at": sub.submitted_at.isoformat(),
            }
            if sub
            else None
        )
    return payload


class GradePayload(BaseModel):
    grade: int | None = None
    feedback: str = ""


@router.post("/submissions/{sid}/grade")
def grade_submission(
    sid: int,
    payload: GradePayload,
    user: User = Depends(current_api_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    sub = db.get(Submission, sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    assignment = db.get(Assignment, sub.assignment_id)
    klass = db.get(ClassRoom, assignment.class_id)
    if klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Not your class.")
    sub.grade = payload.grade
    sub.feedback = payload.feedback[:5000]
    db.commit()
    return {"id": sub.id, "grade": sub.grade, "feedback": sub.feedback}


# ---------- quizzes ----------


@router.get("/quizzes/{qid}")
def quiz_detail(qid: int, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    quiz = db.get(Quiz, qid)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    klass = _member_class_or_404(db, user, quiz.class_id)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id
    if not quiz.published and not is_teacher:
        raise HTTPException(status_code=403, detail="Quiz not available.")
    questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.position).all()
    payload = {
        "id": quiz.id,
        "title": quiz.title,
        "instructions": quiz.instructions,
        "published": quiz.published,
        "questions": [],
    }
    for q in questions:
        item = {"id": q.id, "prompt": q.prompt, "kind": q.kind, "points": q.points}
        if q.kind == "mc":
            item["choices"] = json_choices(q.choices)
        if is_teacher:
            item["correct"] = json_choices(q.correct)
        payload["questions"].append(item)
    return payload


def json_choices(raw: str):
    import json

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


class QuizSubmitPayload(BaseModel):
    answers: dict[str, str]


@router.post("/quizzes/{qid}/submit")
def quiz_submit(
    qid: int,
    payload: QuizSubmitPayload,
    user: User = Depends(current_api_user),
    db: Session = Depends(get_db),
):
    from .routes.quizzes import grade_response

    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students take quizzes.")
    quiz = db.get(Quiz, qid)
    if not quiz or not quiz.published:
        raise HTTPException(status_code=404, detail="Quiz not available.")
    if not db.query(Enrollment).filter_by(class_id=quiz.class_id, student_id=user.id).first():
        raise HTTPException(status_code=403, detail="Not a member of this class.")
    if db.query(QuizAttempt).filter_by(quiz_id=quiz.id, student_id=user.id).first():
        raise HTTPException(status_code=409, detail="Attempt already used.")

    questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).all()
    attempt = QuizAttempt(quiz_id=quiz.id, student_id=user.id, score=0, submitted_at=now())
    db.add(attempt)
    db.flush()
    score = 0
    results = []
    for question in questions:
        response = (payload.answers.get(str(question.id)) or "").strip()
        is_correct = grade_response(question, response)
        earned = question.points if is_correct else 0
        score += earned
        db.add(
            QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                response=response[:2000],
                correct=is_correct,
                points=earned,
            )
        )
        results.append({"question_id": question.id, "correct": is_correct, "points": earned})
    attempt.score = score
    db.commit()
    return {"score": score, "results": results}


# ---------- notifications ----------


@router.get("/notifications")
def api_notifications(user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": n.id,
            "kind": n.kind,
            "message": n.message,
            "link": n.link,
            "read": n.read,
            "created_at": n.created_at.isoformat(),
        }
        for n in rows
    ]


# ---------- extended surface: announcements, quiz attempts, submissions ----------


@router.get("/classes/{cid}/announcements")
def api_announcements(cid: int, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    from .db import Announcement

    klass = _member_class_or_404(db, user, cid)
    rows = (
        db.query(Announcement)
        .filter(Announcement.class_id == klass.id)
        .order_by(Announcement.pinned.desc(), Announcement.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "title": a.title,
            "body": a.body,
            "pinned": a.pinned,
            "author": db.get(User, a.author_id).name,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]


class AnnouncementPayload(BaseModel):
    title: str
    body: str = ""
    pinned: bool = False


@router.post("/classes/{cid}/announcements")
def api_announcement_create(
    cid: int,
    payload: AnnouncementPayload,
    user: User = Depends(current_api_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    if klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Not your class.")
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required.")
    from .db import Announcement
    from .notify import notify_class_students

    announcement = Announcement(
        class_id=klass.id,
        author_id=user.id,
        title=payload.title.strip()[:200],
        body=payload.body.strip()[:8000],
        pinned=payload.pinned,
    )
    db.add(announcement)
    db.commit()
    notify_class_students(
        db,
        klass.id,
        "announcement",
        f"New announcement in {klass.name}: {announcement.title}",
        link=f"/classes/{klass.id}",
    )
    return {"id": announcement.id, "title": announcement.title, "pinned": announcement.pinned}


@router.get("/quizzes/{qid}/attempts")
def api_quiz_attempts(qid: int, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    _require_teacher(user)
    quiz = db.get(Quiz, qid)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    klass = db.get(ClassRoom, quiz.class_id)
    if klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Not your class.")
    attempts = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).all()
    return [
        {
            "id": attempt.id,
            "student": db.get(User, attempt.student_id).name,
            "score": attempt.score,
            "submitted_at": attempt.submitted_at.isoformat(),
        }
        for attempt in attempts
    ]


class SubmitPayload(BaseModel):
    text: str
    file_name: str | None = None


@router.post("/assignments/{aid}/submit")
def api_assignment_submit(
    aid: int,
    payload: SubmitPayload,
    user: User = Depends(current_api_user),
    db: Session = Depends(get_db),
):
    """Students submit text via the API; late submissions are flagged like the web flow."""
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students submit assignments.")
    assignment = db.get(Assignment, aid)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if not db.query(Enrollment).filter_by(class_id=assignment.class_id, student_id=user.id).first():
        raise HTTPException(status_code=403, detail="Not a member of this class.")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Submission text is required.")

    sub = db.query(Submission).filter_by(assignment_id=assignment.id, student_id=user.id).first()
    late = bool(assignment.due_at and now() > assignment.due_at)
    if sub:
        sub.text = text[:20000]
        sub.late = late
        sub.grade = None
        sub.feedback = ""
        sub.graded_at = None
        sub.submitted_at = now()
    else:
        sub = Submission(assignment_id=assignment.id, student_id=user.id, text=text[:20000], late=late)
        db.add(sub)
    db.commit()
    return {
        "id": sub.id,
        "late": sub.late,
        "submitted_at": sub.submitted_at.isoformat(),
        "grade": sub.grade,
    }


# ---------- materials & search ----------


@router.get("/materials/{mid}")
def api_material_detail(mid: int, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    material = db.get(Material, mid)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")
    _member_class_or_404(db, user, material.class_id)
    klass = db.get(ClassRoom, material.class_id)
    return {
        "id": material.id,
        "class_id": klass.id,
        "class_name": klass.name,
        "title": material.title,
        "description": material.description,
        "file": material.original_name or None,
        "size_bytes": material.size_bytes,
        "ai_readable": bool(material.text_content),
    }


@router.get("/search")
def api_search(q: str, user: User = Depends(current_api_user), db: Session = Depends(get_db)):
    from .routes.search import _member_class_ids

    q = q.strip()
    if not q:
        return {"query": "", "results": {"classes": [], "materials": [], "assignments": []}}
    like = f"%{q}%"
    class_ids = _member_class_ids(db, user) or [0]
    classes = (
        db.query(ClassRoom)
        .filter(ClassRoom.id.in_(class_ids))
        .filter(ClassRoom.name.like(like) | ClassRoom.description.like(like))
        .all()
    )
    materials = (
        db.query(Material)
        .filter(Material.class_id.in_(class_ids))
        .filter(Material.title.like(like) | Material.text_content.like(like))
        .limit(25)
        .all()
    )
    assignments = (
        db.query(Assignment)
        .filter(Assignment.class_id.in_(class_ids))
        .filter(Assignment.title.like(like) | Assignment.instructions.like(like))
        .limit(25)
        .all()
    )
    return {
        "query": q,
        "results": {
            "classes": [{"id": c.id, "name": c.name} for c in classes],
            "materials": [{"id": m.id, "title": m.title, "class_id": m.class_id} for m in materials],
            "assignments": [{"id": a.id, "title": a.title, "class_id": a.class_id} for a in assignments],
        },
    }
