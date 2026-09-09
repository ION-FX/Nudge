from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import config, security
from ..db import Assignment, ClassRoom, Enrollment, Submission, User, now
from ..deps import ensure_class_member, get_db, page_user, parse_due, parse_points
from ..extract import UPLOAD_EXTENSIONS, ext_of
from ..web import redirect, render

router = APIRouter()


def _require_teacher(user) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can do that.")


def _get_assignment_or_404(db: Session, aid: int) -> Assignment:
    assignment = db.get(Assignment, aid)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return assignment


@router.get("/classes/{cid}/assignments/new")
def assignment_new_page(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    _require_teacher(user)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    ensure_class_member(db, user, klass)
    return render(request, db, "assignment_new.html", klass=klass, error=None)


@router.post("/classes/{cid}/assignments/new")
def assignment_new(
    cid: int,
    request: Request,
    title: str = Form(""),
    instructions: str = Form(""),
    due_at: str = Form(""),
    points: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    ensure_class_member(db, user, klass)

    title = title.strip()
    due = parse_due(due_at)
    pts = parse_points(points)
    if not title:
        return render(
            request, db, "assignment_new.html", klass=klass, error="Please give the assignment a title.", status_code=400
        )
    assignment = Assignment(
        class_id=klass.id,
        title=title[:200],
        instructions=instructions.strip()[:20000],
        due_at=due,
        points=pts,
    )
    db.add(assignment)
    db.commit()
    return redirect(f"/assignments/{assignment.id}", flash=f"Assignment '{title}' posted.")


@router.get("/assignments/{aid}")
def assignment_detail(aid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    assignment = _get_assignment_or_404(db, aid)
    klass = db.get(ClassRoom, assignment.class_id)
    ensure_class_member(db, user, klass)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id

    submissions = []
    student_count = 0
    my_sub = None
    if is_teacher:
        student_count = db.query(Enrollment).filter_by(class_id=klass.id).count()
        submissions = (
            db.query(Submission, User)
            .join(User, Submission.student_id == User.id)
            .filter(Submission.assignment_id == assignment.id)
            .order_by(Submission.submitted_at)
            .all()
        )
    else:
        my_sub = (
            db.query(Submission)
            .filter_by(assignment_id=assignment.id, student_id=user.id)
            .first()
        )

    return render(
        request,
        db,
        "assignment_detail.html",
        assignment=assignment,
        klass=klass,
        is_teacher=is_teacher,
        submissions=submissions,
        student_count=student_count,
        my_sub=my_sub,
        now=now(),
    )


@router.post("/assignments/{aid}/submit")
async def assignment_submit(
    aid: int,
    request: Request,
    text: str = Form(""),
    file: UploadFile | None = File(None),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit.")
    assignment = _get_assignment_or_404(db, aid)
    klass = db.get(ClassRoom, assignment.class_id)
    ensure_class_member(db, user, klass)

    text = text.strip()
    data = b""
    original_name = ""
    ext = ""
    error = None

    if file is not None and file.filename:
        ext = ext_of(file.filename)
        if ext not in UPLOAD_EXTENSIONS:
            error = f"File type '{ext or '?'}' isn't allowed. Allowed: {', '.join(sorted(UPLOAD_EXTENSIONS))}"
        else:
            data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
            if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
                error = f"File is too large (max {config.MAX_UPLOAD_MB} MB)."
            else:
                original_name = file.filename
                text = text[:20000]
    elif text:
        text = text[:20000]
    else:
        error = "Write some text or attach a file to submit."

    if error:
        return redirect(f"/assignments/{aid}", flash=error, category="err")

    stored_name = ""
    if original_name:
        stored_name = uuid.uuid4().hex + ext
        (config.UPLOAD_DIR / stored_name).write_bytes(data)

    late = bool(assignment.due_at and now() > assignment.due_at)
    sub = db.query(Submission).filter_by(assignment_id=assignment.id, student_id=user.id).first()
    if sub:
        sub.text = text
        sub.stored_name = stored_name
        sub.original_name = original_name
        sub.late = late
        sub.grade = None
        sub.feedback = ""
        sub.graded_at = None
        sub.submitted_at = now()
    else:
        sub = Submission(
            assignment_id=assignment.id,
            student_id=user.id,
            text=text,
            stored_name=stored_name,
            original_name=original_name,
            late=late,
        )
        db.add(sub)
    db.commit()
    return redirect(
        f"/assignments/{aid}",
        flash="Submission saved — marked as late." if late else "Submission saved!",
    )


@router.post("/submissions/{sid}/grade")
def submission_grade(
    sid: int,
    request: Request,
    grade: str = Form(""),
    feedback: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    sub = db.get(Submission, sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    assignment = _get_assignment_or_404(db, sub.assignment_id)
    klass = db.get(ClassRoom, assignment.class_id)
    if klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can grade.")
    sub.grade = parse_points(grade)
    sub.feedback = feedback.strip()[:5000]
    sub.graded_at = now() if sub.grade is not None else None
    db.commit()
    if sub.grade is None:
        return redirect(f"/assignments/{assignment.id}", flash="Grade cleared.")
    return redirect(f"/assignments/{assignment.id}", flash=f"Graded: {sub.grade}" + (f"/{assignment.points}" if assignment.points else ""))


@router.get("/submissions/{sid}/file")
def submission_file(sid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    sub = db.get(Submission, sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    assignment = _get_assignment_or_404(db, sub.assignment_id)
    klass = db.get(ClassRoom, assignment.class_id)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id
    if not is_teacher and sub.student_id != user.id:
        raise HTTPException(status_code=403, detail="Not your submission.")
    if not sub.stored_name:
        raise HTTPException(status_code=404, detail="This submission has no attached file.")
    path = config.UPLOAD_DIR / sub.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File is missing on disk.")
    return FileResponse(path, filename=sub.original_name or path.name)
