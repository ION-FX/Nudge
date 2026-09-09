# Nudge feature tour

## Classroom basics
- **Classes with join codes** — teachers create classes, students join with a 6-character code (or a prefilled `/join?code=…` link). Codes can be regenerated at any time; old codes stop working.
- **Materials** — upload `.pdf`, `.txt`, `.md`, `.csv`, `.json`, `.py`, or images, or paste text directly. Text is extracted (pypdf for PDFs) so the AI co-pilot can tutor from the actual reading. Materials can be edited, replaced, or deleted.
- **Assignments** — title, rich instructions, optional due date and points. Students submit text and/or a file; late submissions are flagged; resubmitting replaces the old submission and clears its grade for re-grading.
- **Grading** — teachers grade per submission with points and feedback; students see grades, feedback, and a personal grades page (`/mygrades`).
- **Quizzes** — multiple-choice, true/false, and short-answer questions with automatic grading on submit. One attempt per student; drafts stay hidden until published; per-question point values; teacher sees an attempts table sorted by score.
- **Announcements** — class-level posts, pinnable, with notification fan-out.
- **Gradebook** — a student × (assignments + quizzes) matrix per class, with totals and one-click CSV export. Teachers can drill into a single student's record from the roster.
- **Calendar** — every due date across all classes on one page.

## The AI co-pilot
- **Context-aware tutoring** — "Ask Nudge" on any class, material, assignment, or quiz. The tutor receives the assignment instructions, the extracted text of class materials, and the recent conversation.
- **Never reveals answers** — the system prompt (and the quiz-context builder) treats answer keys as confidential. For quizzes, only question *prompts* are shared with the model, never the stored answers.
- **SSE streaming** — replies stream token-by-token; history is persisted per conversation.
- **Conversation management** — `/tutor` lists every conversation with its context, message count, and a delete button; `?new=1` starts a fresh conversation with the same context.
- **Quick retry on 429s** — the free model's shared pool is congested often; the server silently retries with backoff before showing a friendly "try again" message.
- **AI practice questions** — teachers can generate practice questions from any assignment with one click. Questions are shown to students with the answer tucked behind a disclosure toggle.

## Staying informed
- **Notification center** — bell with unread count; new assignments, materials, quizzes, announcements, grades, and quiz results all land in the feed; mark one or all as read.
- **Recent activity** — the class page shows the latest posts, uploads, and quizzes at a glance.
- **Global search** — one box searches your classes, materials (including extracted text), assignments, and announcements — scoped to what you can see.

## Platform
- **First-run setup** — `/setup` wizard creates the admin teacher and locks itself.
- **Accounts** — scrypt-hashed passwords, server-side sessions, CSRF protection on every form, profile with display-name, password change, and personal API token.
- **JSON API (v1)** — token-authenticated endpoints for classes, assignments, submissions, grading, quizzes (including programmatic submission), and notifications. See `docs/API.md`.
- **Management CLI** — `python manage.py` can create teachers, set the invite code, print stats, and export gradebooks.
- **Deployment** — Dockerfile + docker-compose + systemd unit; SQLite database with additive in-place migrations; uploads stored outside the web root with UUID names.
- **Dark mode** — follows the OS preference automatically.
