from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import security
from ..db import User
from ..deps import auth_context, get_db
from ..settings import resolve_invite_code
from ..web import redirect, render

router = APIRouter()


def _logged_in(request: Request, db: Session):
    return auth_context(request, db)[0]


@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    if _logged_in(request, db):
        return redirect("/dashboard")
    return render(request, db, "register.html", error=None, form={})


@router.post("/register")
def register_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    role: str = Form("student"),
    teacher_code: str = Form(""),
    db: Session = Depends(get_db),
):
    name = name.strip()
    email = email.strip().lower()
    role = role if role in ("student", "teacher") else "student"
    form = {"name": name, "email": email, "role": role, "teacher_code": teacher_code}

    error = None
    if not name or len(name) > 120:
        error = "Please enter your name."
    elif "@" not in email or len(email) > 255:
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif role == "teacher" and (
        not resolve_invite_code(db) or teacher_code.strip().upper() != resolve_invite_code(db).upper()
    ):
        error = "That teacher invite code isn't valid. Students can register without a code."
    elif db.query(User).filter(User.email == email).first():
        error = "That email is already registered."

    if error:
        return render(request, db, "register.html", error=error, form=form, status_code=400)

    user = User(name=name, email=email, role=role, password_hash=security.hash_password(password))
    db.add(user)
    db.commit()
    sess = security.create_session(db, user.id)
    resp = redirect("/dashboard", flash=f"Welcome to Nudge, {name}!")
    security.attach_session_cookie(resp, sess.token)
    return resp


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if _logged_in(request, db):
        return redirect("/dashboard")
    return render(request, db, "login.html", error=None, email="")


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not security.verify_password(password, user.password_hash):
        return render(
            request, db, "login.html", error="Wrong email or password.", email=email, status_code=400
        )
    sess = security.create_session(db, user.id)
    resp = redirect("/dashboard", flash=f"Welcome back, {user.name}!")
    security.attach_session_cookie(resp, sess.token)
    return resp


@router.post("/logout")
def logout(
    request: Request,
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = auth_context(request, db)
    if user and not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    security.destroy_session(db, request.cookies.get(security.SESSION_COOKIE))
    resp = redirect("/", flash="Logged out. See you soon!")
    security.clear_session_cookie(resp)
    return resp
