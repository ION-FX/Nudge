"""Management CLI: python manage.py <command> [options]

Commands:
  create-teacher --email E --name N --password P
  set-invite --code CODE
  stats
  export-grades --class-id ID --out PATH
"""
from __future__ import annotations

import argparse
import csv
import sys

from app.db import SessionLocal, User, init_db
from app.security import hash_password


def create_teacher(args) -> None:
    db = SessionLocal()
    if db.query(User).filter(User.email == args.email.lower()).first():
        sys.exit(f"error: {args.email} is already registered")
    user = User(
        email=args.email.strip().lower(),
        name=args.name,
        role="teacher",
        password_hash=hash_password(args.password),
    )
    db.add(user)
    db.commit()
    print(f"teacher created: {user.email} (id {user.id})")


def set_invite(args) -> None:
    from app.settings import set_setting

    db = SessionLocal()
    set_setting(db, "teacher_invite_code", args.code.strip().upper())
    print(f"teacher invite code set to {args.code.strip().upper()}")


def stats(args) -> None:
    from app.db import Assignment, ClassRoom, Enrollment, Material, Quiz, Submission, User

    db = SessionLocal()
    print("users:        ", db.query(User).count())
    print("  teachers:   ", db.query(User).filter_by(role="teacher").count())
    print("  students:   ", db.query(User).filter_by(role="student").count())
    print("classes:      ", db.query(ClassRoom).count())
    print("enrollments:  ", db.query(Enrollment).count())
    print("materials:    ", db.query(Material).count())
    print("assignments:  ", db.query(Assignment).count())
    print("submissions:  ", db.query(Submission).count())
    print("quizzes:      ", db.query(Quiz).count())
    db.close()


def export_grades(args) -> None:
    from app.db import ClassRoom
    from app.routes.gradebook import _build_matrix

    db = SessionLocal()
    klass = db.get(ClassRoom, args.class_id)
    if klass is None:
        sys.exit(f"error: class {args.class_id} not found")
    students, assignments, quizzes, subs, attempts, quiz_totals = _build_matrix(db, klass)
    with open(args.out, "w", newline="") as handle:
        writer = csv.writer(handle)
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
    print(f"gradebook for '{klass.name}' written to {args.out}")


def main() -> None:
    init_db()
    parser = argparse.ArgumentParser(prog="manage.py", description="Nudge management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p_teacher = sub.add_parser("create-teacher", help="create a teacher account")
    p_teacher.add_argument("--email", required=True)
    p_teacher.add_argument("--name", required=True)
    p_teacher.add_argument("--password", required=True)
    p_teacher.set_defaults(func=create_teacher)

    p_invite = sub.add_parser("set-invite", help="set the teacher invite code")
    p_invite.add_argument("--code", required=True)
    p_invite.set_defaults(func=set_invite)

    sub.add_parser("stats", help="print row counts").set_defaults(func=stats)

    p_export = sub.add_parser("export-grades", help="export a class gradebook as CSV")
    p_export.add_argument("--class-id", type=int, required=True)
    p_export.add_argument("--out", required=True)
    p_export.set_defaults(func=export_grades)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
