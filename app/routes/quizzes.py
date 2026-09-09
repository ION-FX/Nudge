"""Quizzes: teacher-built, auto-graded on submit (multiple choice / true-false / short answer)."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import security
from ..db import (
    ClassRoom,
    Enrollment,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    User,
    now,
)
from ..deps import ensure_class_member, get_db, page_user, parse_due
from ..notify import notify_class_students, notify
from ..web import redirect, render

router = APIRouter()

QUESTION_KINDS = ("mc", "truefalse", "short")


def _require_class_teacher(db: Session, user, klass: ClassRoom) -> None:
    if user.role != "teacher" or klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can do that.")


def _get_quiz_or_404(db: Session, qid: int) -> Quiz:
    quiz = db.get(Quiz, qid)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    return quiz


def _quiz_questions(db: Session, quiz_id: int) -> list[QuizQuestion]:
    return (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position, QuizQuestion.id)
        .all()
    )


def quiz_total_points(questions: list[QuizQuestion]) -> int:
    return sum(q.points for q in questions)


def grade_response(question: QuizQuestion, response: str) -> bool:
    try:
        data = json.loads(question.correct)
    except json.JSONDecodeError:
        return False
    if question.kind == "mc":
        return response.strip().lstrip("+").isdigit() and int(response.strip().lstrip("+")) == data.get("index", -1)
    if question.kind == "truefalse":
        want = "true" if data.get("value") else "false"
        return response.strip().lower() == want
    accepted = [a.strip().lower() for a in data.get("answers", [])]
    return response.strip().lower() in accepted


# ---------- teacher: create / configure ----------


@router.get("/classes/{cid}/quizzes/new")
def quiz_new_page(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)
    return render(request, db, "quiz_new.html", klass=klass, error=None)


@router.post("/classes/{cid}/quizzes/new")
def quiz_new(
    cid: int,
    request: Request,
    title: str = Form(""),
    instructions: str = Form(""),
    due_at: str = Form(""),
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

    title = title.strip()
    if not title:
        return render(request, db, "quiz_new.html", klass=klass, error="Please give the quiz a title.", status_code=400)
    quiz = Quiz(
        class_id=klass.id,
        title=title[:200],
        instructions=instructions.strip()[:8000],
        due_at=parse_due(due_at),
    )
    db.add(quiz)
    db.commit()
    return redirect(f"/quizzes/{quiz.id}", flash="Quiz created — now add questions.")


@router.post("/quizzes/{qid}/edit")
def quiz_edit(
    qid: int,
    request: Request,
    title: str = Form(""),
    instructions: str = Form(""),
    due_at: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    _require_class_teacher(db, user, klass)
    title = title.strip()
    if not title:
        return redirect(f"/quizzes/{quiz.id}", flash="Quiz needs a title.", category="err")
    quiz.title = title[:200]
    quiz.instructions = instructions.strip()[:8000]
    quiz.due_at = parse_due(due_at)
    db.commit()
    return redirect(f"/quizzes/{quiz.id}", flash="Quiz details saved.")


@router.post("/quizzes/{qid}/publish")
def quiz_publish(qid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    _require_class_teacher(db, user, klass)
    quiz.published = not quiz.published
    db.commit()
    if quiz.published:
        questions = _quiz_questions(db, quiz.id)
        notify_class_students(
            db,
            klass.id,
            "quiz",
            f"New quiz in {klass.name}: {quiz.title} ({quiz_total_points(questions)} pts)",
            link=f"/quizzes/{quiz.id}",
        )
        return redirect(f"/quizzes/{quiz.id}", flash="Quiz published — students can take it now.")
    return redirect(f"/quizzes/{quiz.id}", flash="Quiz unpublished.")


@router.post("/quizzes/{qid}/delete")
def quiz_delete(qid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    _require_class_teacher(db, user, klass)
    for question in _quiz_questions(db, quiz.id):
        db.query(QuizAnswer).filter(QuizAnswer.question_id == question.id).delete()
        db.delete(question)
    db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).delete()
    db.delete(quiz)
    db.commit()
    return redirect(f"/classes/{klass.id}", flash="Quiz deleted.")


@router.post("/quizzes/{qid}/questions")
def question_add(
    qid: int,
    request: Request,
    prompt: str = Form(""),
    kind: str = Form("mc"),
    choices: str = Form(""),
    correct_index: str = Form(""),
    correct_tf: str = Form("true"),
    correct_short: str = Form(""),
    points: str = Form("1"),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    _require_class_teacher(db, user, klass)

    prompt = prompt.strip()
    kind = kind if kind in QUESTION_KINDS else "mc"
    try:
        pts = max(1, min(100, int(float(points))))
    except ValueError:
        pts = 1

    error = None
    choice_list: list[str] = []
    correct_json = "{}"

    if not prompt:
        error = "The question needs a prompt."
    elif kind == "mc":
        choice_list = [line.strip() for line in choices.splitlines() if line.strip()]
        if len(choice_list) < 2:
            error = "Multiple choice needs at least two options (one per line)."
        elif not correct_index.strip().isdigit() or not (0 <= int(correct_index) < len(choice_list)):
            error = "Pick which option is the correct answer."
        else:
            correct_json = json.dumps({"index": int(correct_index)})
    elif kind == "truefalse":
        correct_json = json.dumps({"value": correct_tf == "true"})
    else:
        answers = [line.strip() for line in correct_short.splitlines() if line.strip()]
        if not answers:
            error = "Short answer needs at least one accepted answer (one per line)."
        else:
            correct_json = json.dumps({"answers": answers})

    if error:
        return redirect(f"/quizzes/{quiz.id}", flash=error, category="err")

    position = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz.id)
        .count()
    )
    db.add(
        QuizQuestion(
            quiz_id=quiz.id,
            position=position,
            prompt=prompt[:4000],
            kind=kind,
            choices=json.dumps(choice_list),
            correct=correct_json,
            points=pts,
        )
    )
    db.commit()
    return redirect(f"/quizzes/{quiz.id}", flash="Question added.")


@router.post("/questions/{question_id}/delete")
def question_delete(question_id: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    question = db.get(QuizQuestion, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")
    quiz = _get_quiz_or_404(db, question.quiz_id)
    klass = db.get(ClassRoom, quiz.class_id)
    _require_class_teacher(db, user, klass)
    db.query(QuizAnswer).filter(QuizAnswer.question_id == question.id).delete()
    db.delete(question)
    db.commit()
    return redirect(f"/quizzes/{quiz.id}", flash="Question removed.")


# ---------- shared view: teacher builder / student take-or-result ----------


@router.get("/quizzes/{qid}")
def quiz_detail(qid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    ensure_class_member(db, user, klass)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id
    questions = _quiz_questions(db, quiz.id)

    if is_teacher:
        attempts = (
            db.query(QuizAttempt, User)
            .join(User, QuizAttempt.student_id == User.id)
            .filter(QuizAttempt.quiz_id == quiz.id)
            .order_by(QuizAttempt.score.desc())
            .all()
        )
        return render(
            request,
            db,
            "quiz_detail.html",
            quiz=quiz,
            klass=klass,
            questions=questions,
            total_points=quiz_total_points(questions),
            attempts=attempts,
            student_count=db.query(Enrollment).filter_by(class_id=klass.id).count(),
            is_teacher=True,
        )

    if not quiz.published:
        raise HTTPException(status_code=403, detail="This quiz isn't available yet.")
    attempt = (
        db.query(QuizAttempt)
        .filter_by(quiz_id=quiz.id, student_id=user.id)
        .first()
    )
    answers_by_qid: dict[int, QuizAnswer] = {}
    if attempt:
        for answer in db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt.id).all():
            answers_by_qid[answer.question_id] = answer
    return render(
        request,
        db,
        "quiz_take.html",
        quiz=quiz,
        klass=klass,
        questions=questions,
        total_points=quiz_total_points(questions),
        attempt=attempt,
        answers_by_qid=answers_by_qid,
        is_teacher=False,
    )


# ---------- student: submit ----------


@router.post("/quizzes/{qid}/take")
async def quiz_take(qid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students take quizzes.")
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    ensure_class_member(db, user, klass)
    if not quiz.published:
        raise HTTPException(status_code=403, detail="This quiz isn't available yet.")
    if db.query(QuizAttempt).filter_by(quiz_id=quiz.id, student_id=user.id).first():
        return redirect(f"/quizzes/{quiz.id}", flash="You've already taken this quiz.", category="err")

    form = await request.form()
    questions = _quiz_questions(db, quiz.id)

    attempt = QuizAttempt(quiz_id=quiz.id, student_id=user.id, score=0, submitted_at=now())
    db.add(attempt)
    db.flush()

    score = 0
    for question in questions:
        raw = form.get(f"q_{question.id}")
        response = "" if raw is None else str(raw).strip()
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
    attempt.score = score
    db.commit()

    teacher = db.get(User, klass.teacher_id)
    notify(
        db,
        teacher.id,
        "quiz",
        f"{user.name} scored {score}/{quiz_total_points(questions)} on '{quiz.title}'",
        link=f"/quizzes/{quiz.id}",
    )
    return redirect(f"/quizzes/{quiz.id}", flash=f"Submitted — you scored {score}/{quiz_total_points(questions)}!")


def _parse_import_row(row: list[str]) -> QuizQuestion | None:
    """Columns: prompt | kind | options (|-separated, mc only) | correct | points."""
    if len(row) < 4:
        return None
    prompt, kind, options, correct = (cell.strip() for cell in row[:4])
    points = 1
    if len(row) >= 5 and row[4].strip():
        try:
            points = max(1, min(100, int(float(row[4]))))
        except ValueError:
            return None
    if not prompt:
        return None
    kind = {"mc": "mc", "multiple": "mc", "tf": "truefalse", "truefalse": "truefalse", "short": "short"}.get(
        kind.lower(), None
    )
    if kind is None:
        return None
    if kind == "mc":
        choice_list = [opt.strip() for opt in options.split("|") if opt.strip()]
        if len(choice_list) < 2 or not correct.isdigit() or not (0 <= int(correct) < len(choice_list)):
            return None
        return QuizQuestion(prompt=prompt, kind="mc", choices=json.dumps(choice_list),
                            correct=json.dumps({"index": int(correct)}), points=points)
    if kind == "truefalse":
        if correct.lower() not in ("true", "false"):
            return None
        return QuizQuestion(prompt=prompt, kind="truefalse",
                            correct=json.dumps({"value": correct.lower() == "true"}), points=points)
    answers = [a.strip() for a in correct.split("||") if a.strip()]
    if not answers:
        return None
    return QuizQuestion(prompt=prompt, kind="short",
                        correct=json.dumps({"answers": answers}), points=points)


@router.post("/quizzes/{qid}/import")
def quiz_import(
    qid: int,
    request: Request,
    csv_text: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    """Bulk-add questions from pasted CSV rows."""
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    quiz = _get_quiz_or_404(db, qid)
    klass = db.get(ClassRoom, quiz.class_id)
    _require_class_teacher(db, user, klass)

    reader = csv.reader(io.StringIO(csv_text.strip()))
    position = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
    added, skipped = 0, 0
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        if row[0].strip().lower() == "prompt":  # header row
            continue
        question = _parse_import_row(row)
        if question is None:
            skipped += 1
            continue
        question.quiz_id = quiz.id
        question.position = position
        position += 1
        db.add(question)
        added += 1
    db.commit()
    if added == 0:
        return redirect(f"/quizzes/{quiz.id}", flash="No valid rows found — check the format.", category="err")
    message = f"Imported {added} question" + ("s" if added != 1 else "") + "."
    if skipped:
        message += f" Skipped {skipped} invalid row" + ("s" if skipped != 1 else "") + "."
    return redirect(f"/quizzes/{quiz.id}", flash=message)
