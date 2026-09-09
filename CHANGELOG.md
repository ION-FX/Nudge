# Changelog

## 0.3.0 — scale-up release

### Added
- **Quizzes**: MC / true-false / short-answer builder, publishing flow,
  server-side auto-grading, one attempt per student, teacher attempts table.
- **Gradebook**: student × (assignments + quizzes) matrix, totals, CSV export;
  student-facing "My grades" page.
- **Notifications**: in-app bell with unread count; events for new
  assignments, materials, quizzes, announcements, grades, and quiz results;
  mark-one / mark-all read.
- **Announcements**: pinnable class posts with fan-out notifications.
- **JSON API v1** (`/api/v1`): bearer-token auth with per-user tokens managed
  from the profile page; classes, assignments, submissions, grading, quizzes
  (programmatic submission), notifications, announcements, quiz attempts.
- **AI practice questions**: one-click generation from an assignment using the
  configured model; answers hidden behind a disclosure toggle for students.
- **Calendar**: due dates across all classes on one page.
- **Class management**: edit class, archive/unarchive, regenerate join code,
  remove students, per-student detail page, class activity feed.
- **Profile**: display-name change, password change, API token generation.
- **Global search** across classes, materials (including extracted text),
  assignments, and announcements, scoped to memberships.
- **Deployment**: Dockerfile, docker-compose, systemd unit, Makefile,
  management CLI (`manage.py`).
- **Test suite**: 100+ pytest tests with full isolation (no network, throwaway
  database per test).

### Changed
- `/setup` gate now funnels *all* traffic to the wizard until an account
  exists; the page locks itself afterwards.
- Additive in-place migrations for existing databases (new columns via
  `PRAGMA table_info` inspection).
- Tutor streams retry upstream 429s with backoff before surfacing an error.
- Dark mode follows the OS preference.

## 0.2.0
- First-run `/setup` wizard with DB-backed settings overriding `.env`.
- Configurable bind host/port; Tailscale deployment docs.

## 0.1.0
- Initial release: classes, materials with text extraction, assignments,
  submissions, grading, and the Socratic AI co-pilot with SSE streaming.
