from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import ai, security
from ..db import AiChat, AiMessage, Assignment, ClassRoom, Material, SessionLocal, User
from ..deps import auth_context, ensure_class_member, get_db, page_user
from ..settings import resolve_api_key, resolve_model
from ..web import render

router = APIRouter()

MAX_MESSAGE_CHARS = 4000
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _find_chat(db: Session, user_id: int, klass_id: int, assignment, material) -> AiChat | None:
    q = db.query(AiChat).filter(AiChat.user_id == user_id, AiChat.class_id == klass_id)
    q = q.filter(AiChat.assignment_id == assignment.id if assignment else AiChat.assignment_id.is_(None))
    q = q.filter(AiChat.material_id == material.id if material else AiChat.material_id.is_(None))
    return q.order_by(AiChat.id.desc()).first()


def _get_or_create_chat(db: Session, user: User, klass: ClassRoom, assignment=None, material=None) -> AiChat:
    chat = _find_chat(db, user.id, klass.id, assignment, material)
    if not chat:
        chat = AiChat(
            user_id=user.id,
            class_id=klass.id,
            assignment_id=assignment.id if assignment else None,
            material_id=material.id if material else None,
        )
        db.add(chat)
        db.commit()
    return chat


def _history(db: Session, chat_id: int, limit: int = 50) -> list[AiMessage]:
    return (
        db.query(AiMessage)
        .filter(AiMessage.chat_id == chat_id)
        .order_by(AiMessage.id.desc())
        .limit(limit)
        .all()[::-1]
    )


@router.get("/classes/{cid}/tutor")
def class_tutor(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    ensure_class_member(db, user, klass)
    chat = _get_or_create_chat(db, user, klass)
    return render(
        request, db, "chat.html", chat=chat, messages=_history(db, chat.id),
        context_label=f"Class — {klass.name}", back_url=f"/classes/{klass.id}",
    )


@router.get("/assignments/{aid}/tutor")
def assignment_tutor(aid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    assignment = db.get(Assignment, aid)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    klass = db.get(ClassRoom, assignment.class_id)
    ensure_class_member(db, user, klass)
    chat = _get_or_create_chat(db, user, klass, assignment=assignment)
    return render(
        request, db, "chat.html", chat=chat, messages=_history(db, chat.id),
        context_label=f"Assignment — {assignment.title}", back_url=f"/assignments/{assignment.id}",
    )


@router.get("/materials/{mid}/tutor")
def material_tutor(mid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    material = db.get(Material, mid)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")
    klass = db.get(ClassRoom, material.class_id)
    ensure_class_member(db, user, klass)
    chat = _get_or_create_chat(db, user, klass, material=material)
    return render(
        request, db, "chat.html", chat=chat, messages=_history(db, chat.id),
        context_label=f"Material — {material.title}", back_url=f"/materials/{material.id}",
    )


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _sse_error_response(message: str) -> StreamingResponse:
    async def gen():
        yield _sse({"type": "error", "text": message})
        yield _sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _persist(chat_id: int, user_text: str, reply: str) -> None:
    db = SessionLocal()
    try:
        db.add(AiMessage(chat_id=chat_id, role="user", content=user_text))
        db.add(AiMessage(chat_id=chat_id, role="assistant", content=reply))
        db.commit()
    finally:
        db.close()


@router.post("/api/chats/{chat_id}/messages")
async def post_message(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user, sess = auth_context(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Log in first.")
    if not security.csrf_ok(request.headers.get("X-CSRF-Token"), sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    chat = db.get(AiChat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat not found.")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body.")
    text = (body.get("content") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty message.")
    text = text[:MAX_MESSAGE_CHARS]

    if not ai.rate_allowed(user.id):
        return _sse_error_response(
            "You've hit the tutoring rate limit for this hour — take a short break and try again."
        )

    messages = ai.build_messages(db, chat, text)
    api_key = resolve_api_key(db)
    model = resolve_model(db)

    async def gen():
        parts: list[str] = []
        failed = False
        try:
            async for delta in ai.stream_completion(messages, api_key=api_key, model=model):
                parts.append(delta)
                yield _sse({"type": "delta", "text": delta})
        except ai.TutorError as exc:
            failed = True
            yield _sse({"type": "error", "text": str(exc)})
        except Exception:
            failed = True
            yield _sse({"type": "error", "text": "Something went wrong on our side. Please try again."})
        if not failed and parts:
            ai.rate_record(user.id)
            _persist(chat.id, text, "".join(parts))
        yield _sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)
