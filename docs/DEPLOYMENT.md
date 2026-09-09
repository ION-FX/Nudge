# Deploying Nudge

## Bare metal / VM

```bash
git clone https://github.com/ION-FX/Nudge.git
cd Nudge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # add your OpenRouter key + a teacher invite code
.venv/bin/python run.py   # binds 0.0.0.0:8000
```

Open `http://<host>:8000` — the first visit redirects to `/setup`, where you
create the admin teacher account. Everything else (invite code, API key) can
also be configured there and lives in `data/nudge.db`.

### systemd

`deploy/nudge.service` is a ready-made unit:

```bash
sudo cp deploy/nudge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nudge
```

## Docker

```bash
cp .env.example .env      # fill in the key
docker compose up -d --build
```

The compose file persists `data/` (database) and `uploads/` in named volumes.

## Tailscale

The server binds `0.0.0.0`, so any device on the tailnet can reach
`http://<tailnet-ip>:8000`. For a proper HTTPS name:

```bash
sudo tailscale set --operator=$USER   # one-time
tailscale serve --bg 8000             # https://<machine>.<tailnet>.ts.net
```

## Backups

Everything that matters lives in two paths:

- `data/nudge.db` — the SQLite database (stop the service or use
  `sqlite3 data/nudge.db ".backup backup.db"` for a consistent copy)
- `uploads/` — submitted files and materials

## Management CLI

```bash
.venv/bin/python manage.py stats
.venv/bin/python manage.py create-teacher --email t@school.edu --name "Ms. R" --password '...'
.venv/bin/python manage.py set-invite --code SCHOOL24
.venv/bin/python manage.py export-grades --class-id 1 --out grades.csv
```
