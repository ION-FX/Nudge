# Roadmap

Ideas are ranked by (teacher value) × (student value) ÷ (complexity). Nothing
here is committed — propose changes in an issue.

## Near term

- **Email invitations** — replace the shared teacher invite code with
  per-person invites; password reset via email.
- **Tutor: teacher-visible usage stats** — how many questions per assignment,
  so teachers can see what a class is stuck on *before* grading it.
- **Assignment categories & filters** — homework / lab / reading, filterable in
  the gradebook.
- **Quiz retake policy** — teacher-configurable (single attempt today).
- **Bulk grade export per student** — a one-page report suitable for printing.

## Medium term

- **Material versioning** — keep the previous text/file when a teacher
  replaces an upload, with a restore button.
- **Rich assignment instructions** — a tiny markdown editor with preview
  (still no npm: a small vendored renderer or a restricted tag set).
- **Per-student accommodations** — extra attempts, extended deadlines.
- **Audit log** — who changed which grade, visible to teachers.
- **Postgres support** — swap the SQLite engine via config for bigger
  deployments; the ORM layer is already database-agnostic.

## Explicitly out of scope

- **Answer-key auto-grading of essays by AI** — grading judgment stays human.
- **Live proctoring** — creepy, and the tutor's guardrails already make
  cheating via Nudge pointless.
- **npm/CDN frontends** — see CONTRIBUTING.md; this is a hard constraint.
