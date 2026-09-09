"""Class announcements: teacher posts, students read; pinned first."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import security
from ..db import Announcement, ClassRoom
from ..deps import get_db, page_user
from ..notify import notify_class_students
from ..web import redirect

router = APIRouter()


def _get_announcement_or_404(db: Session, aid: int) -> Announcement:
    announcement = db.get(Announcement, aid)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found.")
    return announcement


def _require_class_teacher(db: Session, user, klass: ClassRoom) -> None:
    if user.role != "teacher" or klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can do that.")


@router.post("/classes/{cid}/announcements")
def announcement_create(
    cid: int,
    request: Request,
    title: str = Form(""),
    body: str = Form(""),
    pinned: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    _require_class_teacher(db, user, klass)

    title = title.strip()
    if not title:
        return redirect(f"/classes/{klass.id}", flash="Announcement needs a title.", category="err")

    announcement = Announcement(
        class_id=klass.id,
        author_id=user.id,
        title=title[:200],
        body=body.strip()[:8000],
        pinned=pinned == "on",
    )
    db.add(announcement)
    db.commit()
    notify_class_students(
        db,
        klass.id,
        "announcement",
        f"New announcement in {klass.name}: {announcement.title}",
        link=f"/classes/{klass.id}#announcements",
    )
    return redirect(f"/classes/{klass.id}", flash="Announcement posted.")


@router.post("/announcements/{aid}/delete")
def announcement_delete(aid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    announcement = _get_announcement_or_404(db, aid)
    klass = db.get(ClassRoom, announcement.class_id)
    _require_class_teacher(db, user, klass)
    db.delete(announcement)
    db.commit()
    return redirect(f"/classes/{klass.id}", flash="Announcement deleted.")


@router.post("/announcements/{aid}/pin")
def announcement_pin(aid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    announcement = _get_announcement_or_404(db, aid)
    klass = db.get(ClassRoom, announcement.class_id)
    _require_class_teacher(db, user, klass)
    announcement.pinned = not announcement.pinned
    db.commit()
    state = "pinned" if announcement.pinned else "unpinned"
    return redirect(f"/classes/{klass.id}", flash=f"Announcement {state}.")
