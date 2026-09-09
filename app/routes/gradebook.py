"""Gradebook: teacher matrix across assignments & quizzes, CSV export, student view."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db import Assignment, ClassRoom, Enrollment, Quiz, QuizAttempt, QuizQuestion, Submission, User
from ..deps import get_db, page_user
from ..web import render

router = APIRouter()


def _member_class_or_404(db: Session, cid: int) -> ClassRoom:
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    return klass


def _build_matrix(db: Session, klass: ClassRoom):
    students = (
        db.query(User)
        .join(Enrollment, Enrollment.student_id == User.id)
        .filter(Enrollment.class_id == klass.id)
        .order_by(User.name)
        .all()
    )
    assignments = (
        db.query(Assignment)
        .filter(Assignment.class_id == klass.id)
        .order_by(Assignment.due_at, Assignment.id)
        .all()
    )
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.class_id == klass.id, Quiz.published.is_(True))
        .order_by(Quiz.id)
        .all()
    )
    subs = {
        (s.assignment_id, s.student_id): s
        for s in db.query(Submission).filter(Submission.assignment_id.in_([a.id for a in assignments] or [0])).all()
    }
    attempts = {
        (a.quiz_id, a.student_id): a
        for a in db.query(QuizAttempt).filter(QuizAttempt.quiz_id.in_([q.id for q in quizzes] or [0])).all()
    }
    quiz_totals = {
        q.id: sum(qq.points for qq in db.query(QuizQuestion).filter(QuizQuestion.quiz_id == q.id).all())
        for q in quizzes
    }
    return students, assignments, quizzes, subs, attempts, quiz_totals


@router.get("/classes/{cid}/gradebook")
def gradebook(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = _member_class_or_404(db, cid)
    if user.role != "teacher" or klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can open the gradebook.")

    students, assignments, quizzes, subs, attempts, quiz_totals = _build_matrix(db, klass)

    rows = []
    for student in students:
        cells = []
        total = 0
        possible = 0
        for a in assignments:
            sub = subs.get((a.id, student.id))
            earned = sub.grade if sub and sub.grade is not None else None
            if earned is not None and a.points:
                total += earned
                possible += a.points
            cells.append({"kind": "assignment", "item": a, "value": earned, "sub": sub})
        for q in quizzes:
            att = attempts.get((q.id, student.id))
            if att is not None:
                total += att.score
                possible += quiz_totals.get(q.id, 0)
            cells.append({"kind": "quiz", "item": q, "value": att.score if att else None, "total": quiz_totals.get(q.id, 0)})
        rows.append({"student": student, "cells": cells, "total": total, "possible": possible})

    return render(
        request,
        db,
        "gradebook.html",
        klass=klass,
        rows=rows,
        assignments=assignments,
        quizzes=quizzes,
    )


@router.get("/classes/{cid}/gradebook.csv")
def gradebook_csv(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = _member_class_or_404(db, cid)
    if user.role != "teacher" or klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can export grades.")

    students, assignments, quizzes, subs, attempts, _quiz_totals = _build_matrix(db, klass)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = ["student", "email"]
    for a in assignments:
        header.append(f"{a.title} (/{a.points or '?'})")
    for q in quizzes:
        header.append(f"Quiz: {q.title}")
    writer.writerow(header)

    for student in students:
        row = [student.name, student.email]
        for a in assignments:
            sub = subs.get((a.id, student.id))
            row.append(sub.grade if sub and sub.grade is not None else "")
        for q in quizzes:
            att = attempts.get((q.id, student.id))
            row.append(att.score if att else "")
        writer.writerow(row)

    filename = f"{klass.name.replace(' ', '_').lower()}_gradebook.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/mygrades")
def my_grades(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students have a personal grades page.")

    enrollments = db.query(Enrollment).filter(Enrollment.student_id == user.id).all()
    sections = []
    for enrollment in enrollments:
        klass = db.get(ClassRoom, enrollment.class_id)
        if not klass or klass.archived:
            continue
        assignments = (
            db.query(Assignment)
            .filter(Assignment.class_id == klass.id)
            .order_by(Assignment.due_at, Assignment.id)
            .all()
        )
        assignment_rows = []
        for a in assignments:
            sub = db.query(Submission).filter_by(assignment_id=a.id, student_id=user.id).first()
            assignment_rows.append((a, sub))
        quizzes = (
            db.query(Quiz)
            .filter(Quiz.class_id == klass.id, Quiz.published.is_(True))
            .order_by(Quiz.id)
            .all()
        )
        quiz_rows = []
        for q in quizzes:
            attempt = db.query(QuizAttempt).filter_by(quiz_id=q.id, student_id=user.id).first()
            quiz_rows.append((q, attempt))
        sections.append((klass, assignment_rows, quiz_rows))

    return render(request, db, "my_grades.html", sections=sections)
