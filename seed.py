"""Seed demo data: python seed.py (safe to run twice)."""

import datetime as dt
import uuid

from app import config
from app.db import Assignment, ClassRoom, Enrollment, Material, SessionLocal, User, init_db
from app.security import hash_password

LOOPS_GUIDE = """Loops in Python — Study Guide
=============================

A loop repeats work so you don't have to copy-paste code.

The `for` loop
--------------
Use a `for` loop when you know how many times (or over what collection) you want to repeat:

    for number in range(1, 6):
        print(number)

`range(1, 6)` produces 1, 2, 3, 4, 5 — the end value is NOT included.

The `while` loop
----------------
Use a `while` loop when you repeat until a condition changes:

    count = 3
    while count > 0:
        print(count)
        count = count - 1

Forgetting to update the variable in the condition causes an INFINITE LOOP.

Common patterns
---------------
- Accumulate a total: start a variable at 0, add inside the loop.
- Build a string: start with "", concatenate inside the loop.
- Count matches: start a counter at 0, add 1 when a condition is true.

The `%` (modulo) operator
-------------------------
`x % y` is the remainder after dividing x by y. `7 % 3` is 1.
A number `x` is a multiple of `y` exactly when `x % y == 0` — very handy in loops.
"""

FAQ_TEXT = """Class FAQ
---------
Q: Can Nudge do my assignment for me?
A: No — and that's on purpose. Nudge is your co-pilot: it asks guiding questions,
   gives hints, and explains concepts so YOU can solve the problem.

Q: What if my code has a bug?
A: Paste the error and what you expected vs. what happened. Nudge will help you
   find it yourself — debugging is where the real learning happens.

Q: Can I resubmit an assignment?
A: Yes, until the due date is... well, actually you can resubmit any time, but
   late work is flagged and resubmitting clears your grade for re-grading.
"""


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "teacher@nudge.test").first():
            print("Seed data already present — nothing to do.")
            return

        teacher = User(
            email="teacher@nudge.test", name="Ms. Rivera", role="teacher",
            password_hash=hash_password("nudge-teacher-1"),
        )
        alex = User(
            email="alex@nudge.test", name="Alex Chen", role="student",
            password_hash=hash_password("nudge-student-1"),
        )
        sam = User(
            email="sam@nudge.test", name="Sam Okafor", role="student",
            password_hash=hash_password("nudge-student-1"),
        )
        db.add_all([teacher, alex, sam])
        db.commit()

        klass = ClassRoom(
            name="Intro to Python",
            description="First-semester Python: variables, loops, and functions.",
            join_code="PY7DEMO",
            teacher_id=teacher.id,
        )
        db.add(klass)
        db.commit()

        stored = uuid.uuid4().hex + ".txt"
        (config.UPLOAD_DIR / stored).write_text(LOOPS_GUIDE)
        db.add_all(
            [
                Material(
                    class_id=klass.id,
                    title="Loops study guide",
                    description="Read before starting Loop Practice.",
                    original_name="loops-guide.txt",
                    stored_name=stored,
                    ext=".txt",
                    size_bytes=len(LOOPS_GUIDE.encode()),
                    text_content=LOOPS_GUIDE,
                ),
                Material(
                    class_id=klass.id,
                    title="Class FAQ",
                    description="",
                    original_name="",
                    stored_name="",
                    ext="",
                    size_bytes=len(FAQ_TEXT.encode()),
                    text_content=FAQ_TEXT,
                ),
            ]
        )
        db.add_all([Enrollment(class_id=klass.id, student_id=alex.id), Enrollment(class_id=klass.id, student_id=sam.id)])
        db.add(
            Assignment(
                class_id=klass.id,
                title="Loop Practice",
                instructions=(
                    "Write a Python program that prints the numbers from 1 to 30, one per line, but:\n"
                    "  1. For multiples of 3, print 'Fizz' instead of the number.\n"
                    "  2. For multiples of 5, print 'Buzz' instead of the number.\n"
                    "  3. For numbers that are multiples of BOTH 3 and 5, print 'FizzBuzz'.\n\n"
                    "Submit your code as text. Check it yourself first: does the output start correctly?\n"
                    "If you get stuck, ask Nudge for hints — don't ask it for the answer, it won't tell you!"
                ),
                due_at=dt.datetime.now() + dt.timedelta(days=7),
                points=10,
            )
        )
        db.commit()

        print("Seed data created! (This also locks the /setup page, since users now exist.)")
        print("  Teacher  teacher@nudge.test / nudge-teacher-1")
        print("  Student  alex@nudge.test   / nudge-student-1")
        print("  Student  sam@nudge.test    / nudge-student-1")
        print(f"  Class 'Intro to Python' join code: {klass.join_code}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
