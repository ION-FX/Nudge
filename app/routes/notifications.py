"""Notification center: bell feed with mark-as-read."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import security
from ..db import Notification
from ..deps import get_db, page_user
from ..web import redirect, render

router = APIRouter()


@router.get("/notifications")
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    items = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
        .all()
    )
    return render(request, db, "notifications.html", items=items)


@router.post("/notifications/read")
def notification_read(request: Request, nid: int = Form(0), csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    row = db.get(Notification, nid)
    if row and row.user_id == user.id:
        row.read = True
        db.commit()
    return redirect("/notifications")


@router.post("/notifications/read-all")
def notifications_read_all(request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read.is_(False)).update(
        {"read": True}
    )
    db.commit()
    return redirect("/notifications", flash="All caught up!")
