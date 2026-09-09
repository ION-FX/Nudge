# ✦ Nudge

A classroom platform where teachers create classes, upload materials, and post
assignments — with a twist: **Nudge**, an AI co-pilot that helps students when
they get stuck but **never reveals answers**. It asks guiding questions, gives
hints, and explains concepts so students genuinely learn.

## Why no npm?

The entire frontend is server-rendered [Jinja2](https://jinja.palletsprojects.com/) templates with
vanilla JavaScript and a single hand-written stylesheet — **no npm/npx/node, no
build step, no CDN assets**. Everything is self-hosted Python.

## Stack

| Layer      | Choice                                                              |
| ---------- | ------------------------------------------------------------------- |
| Backend    | Python 3.12 + FastAPI + Uvicorn                                      |
| Database   | SQLite (via SQLAlchemy) — file-based, zero config                    |
| Frontend   | Jinja2 templates + vanilla JS + custom CSS (no build tooling)        |
| AI         | OpenRouter (`google/gemma-4-31b-it:free` by default) via `httpx`     |
| Auth       | scrypt password hashing, DB-backed sessions, CSRF tokens             |
| Files      | Local `uploads/` with UUID names, extension whitelist, size cap      |

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# configure secrets
cp .env.example .env
# then edit .env: add your OpenRouter API key + a teacher invite code
```

`.env` keys:

| Key                  | Meaning                                                        |
| -------------------- | -------------------------------------------------------------- |
| `OPENROUTER_API_KEY` | Fallback AI key — can instead be set on the `/setup` page      |
| `MODEL`              | OpenRouter model id (default `google/gemma-4-31b-it:free`)     |
| `TEACHER_INVITE_CODE`| Fallback teacher gate — can instead be set on the `/setup` page|
| `MAX_UPLOAD_MB`      | Upload size cap (default 10)                                   |
| `HOST` / `PORT`      | Bind address/port (default `0.0.0.0:8000`)                     |

Run it:

```bash
.venv/bin/python run.py          # binds 0.0.0.0:8000 — reachable on LAN + Tailscale
```

### First-run setup

Open the site in a browser. If no account exists yet, every page redirects to
**`/setup`**, where you:

1. create the **admin teacher** account,
2. pick the **teacher invite code** future teachers must enter,
3. optionally paste your **OpenRouter API key** and **model** (stored in the
   local `data/nudge.db` — gitignored; anything left blank falls back to `.env`).

The setup page locks itself as soon as any user exists. `python seed.py`
creates demo users, so it also counts as setup — delete `data/nudge.db` to
start over.

### Accessing from other devices (Tailscale)

By default the server binds `0.0.0.0`, so once the machine is on a Tailscale
network, any device on the same tailnet can open:

```
http://<machine's tailnet IP>:8000     # e.g. http://100.72.72.72:8000 — run `tailscale ip -4`
```

For a proper HTTPS URL with MagicDNS, use Tailscale Serve instead (needs one
sudo setup, then the server can go back to 127.0.0.1):

```bash
sudo tailscale set --operator=$USER   # one-time, lets tailscale serve run without sudo
tailscale serve --bg 8000             # serves https://<machine>.<tailnet>.ts.net
```

If the site is unreachable from other devices, check the host firewall:
`sudo ufw allow in on tailscale0 to any port 8000` (or allow 8000 generally).


Demo logins (only if you ran `seed.py`):

- Teacher: `teacher@nudge.test` / `nudge-teacher-1`
- Student: `alex@nudge.test` / `nudge-student-1`

## What it does

**Teachers** — create classes (each gets a join code), upload materials
(`.pdf`, `.txt`, `.md`, `.csv`, `.json`, `.py`, images) or paste text, post
assignments with instructions/due date/points, view submissions, and grade with
feedback.

**Students** — join with a code, browse materials, submit answers (text and/or
file) with late-flagging and resubmission, and see grades + feedback.

**Nudge, the co-pilot** — a context-aware chat available for any class,
material, or assignment. It reads the class materials (text extracted from
uploads) and the assignment instructions, then tutors Socratically. The system
prompt and context pipeline enforce the one rule that makes Nudge *Nudge*:
guide, hint, explain — never give away the answer, even if the uploaded
materials contain answer keys. Streams token-by-token over SSE; per-user rate
limits protect the free model's shared pool.

## GitHub safety

- `.env` (your real API key) is **gitignored** — verify with `git check-ignore .env`
- Only `.env.example` with placeholders is committed
- `uploads/` and `data/` (user files + database) are gitignored too
- The key used during development was shared in chat; **rotate it** at
  https://openrouter.ai/keys before going live

## Project structure

```
nudge/
├── app/
│   ├── ai.py            # system prompt, context builder, OpenRouter SSE client
│   ├── config.py        # env settings
│   ├── db.py            # SQLAlchemy models
│   ├── security.py      # scrypt, sessions, CSRF, flash messages
│   ├── extract.py       # txt/md/csv/json/py + PDF text extraction
│   ├── deps.py, web.py  # auth helpers, render/redirect
│   ├── routes/          # auth, main, classes, materials, assignments, tutor
│   ├── templates/       # Jinja2
│   └── static/          # style.css, chat.js (vanilla)
├── uploads/             # stored files (gitignored)
├── data/nudge.db        # SQLite (gitignored)
├── run.py, seed.py
└── .env                 # secrets (gitignored)
```
