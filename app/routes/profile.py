"""Profile: display name and password management."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import security
from ..deps import get_db, page_user
from ..web import redirect, render

router = APIRouter()


@router.get("/profile")
def profile_page(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    return render(request, db, "profile.html", user_obj=user, name_error=None, pw_error=None)


@router.post("/profile/name")
def profile_name(request: Request, name: str = Form(""), csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    name = name.strip()
    if not name or len(name) > 120:
        return redirect("/profile", flash="Please enter a valid name.", category="err")
    user.name = name
    db.commit()
    return redirect("/profile", flash="Name updated.")


@router.post("/profile/password")
def profile_password(
    request: Request,
    current: str = Form(""),
    new: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    if not security.verify_password(current, user.password_hash):
        return redirect("/profile", flash="Current password is incorrect.", category="err")
    if len(new) < 8:
        return redirect("/profile", flash="New password must be at least 8 characters.", category="err")
    user.password_hash = security.hash_password(new)
    db.commit()
    return redirect("/profile", flash="Password changed.")


@router.post("/profile/api-token")
def profile_api_token(request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    """Generate (or rotate) the personal API token for JSON API access."""
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    user.api_token = secrets.token_urlsafe(32)
    db.commit()
    return redirect("/profile", flash="API token generated — see below.")
