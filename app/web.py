from __future__ import annotations

import datetime as dt
import json

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import config, security
from .db import Notification
from .deps import auth_context

templates = Jinja2Templates(directory=str(config.BASE_DIR / "app" / "templates"))


def _filesize(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


templates.env.filters["filesize"] = _filesize
templates.env.filters["duefmt"] = lambda d: d.strftime("%b %d, %H:%M") if d else "—"
templates.env.filters["dtfmt"] = lambda d: d.strftime("%b %d, %Y %H:%M") if d else "—"
templates.env.filters["datefmt"] = lambda d: d.strftime("%b %Y") if d else "—"


def _parse_json(raw: str):
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


templates.env.filters["parse_json"] = _parse_json
templates.env.filters["tojson_correct"] = lambda raw: str(_parse_json(raw).get("value", False))


def redirect(url: str, flash: str | None = None, category: str = "ok") -> RedirectResponse:
    resp = RedirectResponse(url, status_code=303)
    if flash:
        security.set_flash(resp, flash, category)
    return resp


def render(request: Request, db: Session, name: str, status_code: int = 200, **ctx):
    user, sess = auth_context(request, db)
    flash = security.pop_flash(request)
    unread = 0
    if user:
        unread = (
            db.query(Notification)
            .filter(Notification.user_id == user.id, Notification.read.is_(False))
            .count()
        )
    context = {
        "user": user,
        "csrf": sess.csrf_token if sess else "",
        "flash": flash,
        "unread": unread,
        "now": dt.datetime.now(),
        **ctx,
    }
    resp = templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)
    if flash:
        resp.delete_cookie(security.FLASH_COOKIE, path="/")
    return resp
