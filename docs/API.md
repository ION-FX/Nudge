# JSON API (v1)

All endpoints live under `/api/v1` and authenticate with a bearer token:

```
Authorization: Bearer <your-token>
```

Get a token from **Profile → API access → Generate token** (session login
required), or rotate an existing one with `POST /api/v1/me/token` using the
current token. Treat the token like a password: it grants full access to the
account. Rotate it from the profile page at any time.

## Endpoints

| Method | Path | Who | Description |
| --- | --- | --- | --- |
| GET | `/api/v1/me` | any | id, name, email, role |
| POST | `/api/v1/me/token` | any | rotate token (returns the new one) |
| GET | `/api/v1/classes` | any | classes you teach / are enrolled in, with counts |
| GET | `/api/v1/classes/{id}` | member | class detail incl. assignments, quizzes, materials |
| GET | `/api/v1/assignments/{id}` | member | assignment; teachers also get all submissions, students get their own |
| POST | `/api/v1/submissions/{id}/grade` | teacher | body `{"grade": 17, "feedback": "..."}` |
| GET | `/api/v1/quizzes/{id}` | member | questions; teachers additionally receive the answer key |
| POST | `/api/v1/quizzes/{id}/submit` | student | body `{"answers": {"<question_id>": "response"}}` → auto-graded |
| GET | `/api/v1/notifications` | any | latest 100 notifications |

## Example

```bash
TOKEN=...  # from the profile page

curl -s -H "Authorization: Bearer $TOKEN" https://<host>/api/v1/classes

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"grade": 18, "feedback": "Well argued"}' \
  https://<host>/api/v1/submissions/42/grade

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"answers": {"1": "2", "2": "true"}}' \
  https://<host>/api/v1/quizzes/7/submit
```

## Notes

- Answers to quiz questions are **never** returned for student tokens — only
  teachers can see the answer key, and only via the API for the same reasons
  the UI hides it.
- Errors use the standard HTTP codes: 401 (missing/invalid token), 403
  (wrong role or not a member), 404 (missing object), 409 (attempt already
  used).
