"""First-run setup: create the admin teacher and core settings. Locks once any user exists."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import User
from ..deps import get_db
from ..security import attach_session_cookie, create_session, hash_password
from ..settings import resolve_invite_code, set_setting, users_exist
from ..web import redirect, render

router = APIRouter()

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
DEFAULT_MODEL = "google/gemma-4-31b-it:free"


def _suggest_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


@router.get("/setup")
def setup_page(request: Request, db: Session = Depends(get_db)):
    if users_exist(db):
        return redirect("/login")
    suggestion = resolve_invite_code(db) or _suggest_code()
    return render(request, db, "setup.html", error=None, form={}, invite_suggestion=suggestion)


@router.post("/setup")
def setup_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    invite_code: str = Form(""),
    api_key: str = Form(""),
    model: str = Form(""),
    db: Session = Depends(get_db),
):
    if users_exist(db):
        return redirect("/login")

    name = name.strip()
    email = email.strip().lower()
    invite_code = invite_code.strip().upper()
    api_key = api_key.strip()
    model = model.strip()
    form = {"name": name, "email": email, "invite_code": invite_code, "api_key": api_key, "model": model}

    error = None
    if not name or len(name) > 120:
        error = "Please enter your name."
    elif "@" not in email or len(email) > 255:
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif api_key and not api_key.startswith("sk-or-"):
        error = "That doesn't look like an OpenRouter key — it should start with 'sk-or-'."
    elif not invite_code:
        invite_code = _suggest_code()
    elif len(invite_code) < 4:
        error = "Invite code must be at least 4 characters."

    if error:
        return render(request, db, "setup.html", error=error, form=form, status_code=400,
                      invite_suggestion=invite_code or _suggest_code())

    user = User(name=name, email=email, role="teacher", password_hash=hash_password(password))
    db.add(user)
    db.flush()
    set_setting(db, "teacher_invite_code", invite_code)
    if api_key:
        set_setting(db, "openrouter_api_key", api_key)
    if model:
        set_setting(db, "model", model)

    sess = create_session(db, user.id)
    resp = redirect(
        "/dashboard",
        flash=f"Setup complete! Teacher invite code: {invite_code} — share it with co-teachers.",
    )
    attach_session_cookie(resp, sess.token)
    return resp
