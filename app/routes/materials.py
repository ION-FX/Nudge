from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import config, security
from ..db import ClassRoom, Material
from ..deps import ensure_class_member, get_db, page_user
from ..extract import UPLOAD_EXTENSIONS, ext_of, extract_text
from ..notify import notify_class_students
from ..web import redirect, render

router = APIRouter()


def _get_class_or_404(db: Session, cid: int) -> ClassRoom:
    klass = db.get(ClassRoom, cid)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found.")
    return klass


def _get_material_or_404(db: Session, mid: int) -> Material:
    material = db.get(Material, mid)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")
    return material


def _require_teacher(user) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can do that.")


def _require_owner(db: Session, user, klass: ClassRoom) -> None:
    if user.role != "teacher" or klass.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the class teacher can do that.")


@router.get("/classes/{cid}/materials/new")
def material_new_page(cid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    _require_teacher(user)
    klass = _get_class_or_404(db, cid)
    ensure_class_member(db, user, klass)
    return render(request, db, "material_new.html", klass=klass, max_mb=config.MAX_UPLOAD_MB, error=None)


@router.post("/classes/{cid}/materials/new")
async def material_new(
    cid: int,
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    pasted_text: str = Form(""),
    file: UploadFile | None = File(None),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    klass = _get_class_or_404(db, cid)
    ensure_class_member(db, user, klass)

    title = title.strip()
    pasted_text = pasted_text.strip()
    error = None
    data = b""
    original_name = ""
    ext = ""
    text_content = ""

    if not title:
        error = "Please give the material a title."
    elif file is not None and file.filename:
        ext = ext_of(file.filename)
        if ext not in UPLOAD_EXTENSIONS:
            error = f"File type '{ext or '?'}' isn't allowed. Allowed: {', '.join(sorted(UPLOAD_EXTENSIONS))}"
        else:
            data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
            if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
                error = f"File is too large (max {config.MAX_UPLOAD_MB} MB)."
            else:
                original_name = file.filename
    elif not pasted_text:
        error = "Upload a file or paste some text."

    if not error:
        if original_name:
            stored_name = uuid.uuid4().hex + ext
            (config.UPLOAD_DIR / stored_name).write_bytes(data)
            text_content = extract_text(original_name, data)
        else:
            stored_name = ""
            text_content = pasted_text[:20000]

        material = Material(
            class_id=klass.id,
            title=title[:200],
            description=description.strip()[:2000],
            original_name=original_name,
            stored_name=stored_name,
            ext=ext,
            size_bytes=len(data) if data else len(pasted_text.encode()),
            text_content=text_content,
        )
        db.add(material)
        db.commit()
        notify_class_students(
            db,
            klass.id,
            "material",
            f"New material in {klass.name}: {title}",
            link=f"/materials/{material.id}",
        )
        return redirect(f"/classes/{klass.id}", flash=f"Material '{title}' uploaded.")

    return render(
        request, db, "material_new.html", klass=klass, max_mb=config.MAX_UPLOAD_MB, error=error, status_code=400
    )


@router.get("/materials/{mid}/edit")
def material_edit_page(mid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    material = _get_material_or_404(db, mid)
    klass = _get_class_or_404(db, material.class_id)
    _require_owner(db, user, klass)
    return render(request, db, "material_edit.html", material=material, klass=klass, error=None)


@router.post("/materials/{mid}/edit")
async def material_edit(
    mid: int,
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    pasted_text: str = Form(""),
    file: UploadFile | None = File(None),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    material = _get_material_or_404(db, mid)
    klass = _get_class_or_404(db, material.class_id)
    _require_owner(db, user, klass)

    title = title.strip()
    if not title:
        return render(request, db, "material_edit.html", material=material, klass=klass,
                      error="Please give the material a title.", status_code=400)

    material.title = title[:200]
    material.description = description.strip()[:2000]

    replaced = False
    if file is not None and file.filename:
        ext = ext_of(file.filename)
        if ext not in UPLOAD_EXTENSIONS:
            return render(request, db, "material_edit.html", material=material, klass=klass,
                          error=f"File type '{ext or '?'}' isn't allowed.", status_code=400)
        data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
            return render(request, db, "material_edit.html", material=material, klass=klass,
                          error=f"File is too large (max {config.MAX_UPLOAD_MB} MB).", status_code=400)
        if material.stored_name:
            old = config.UPLOAD_DIR / material.stored_name
            if old.exists():
                old.unlink()
        stored_name = uuid.uuid4().hex + ext
        (config.UPLOAD_DIR / stored_name).write_bytes(data)
        material.original_name = file.filename
        material.stored_name = stored_name
        material.ext = ext
        material.size_bytes = len(data)
        material.text_content = extract_text(file.filename, data)
        replaced = True
    elif not material.stored_name:
        text = pasted_text.strip()
        if text:
            material.text_content = text[:20000]
            material.size_bytes = len(text.encode())
            replaced = True

    db.commit()
    note = " with a new file" if replaced else ""
    return redirect(f"/materials/{material.id}", flash=f"Material updated{note}.")


@router.get("/materials/{mid}")
def material_detail(mid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    material = _get_material_or_404(db, mid)
    klass = _get_class_or_404(db, material.class_id)
    ensure_class_member(db, user, klass)
    is_teacher = user.role == "teacher" and klass.teacher_id == user.id
    return render(
        request,
        db,
        "material_detail.html",
        material=material,
        klass=klass,
        is_teacher=is_teacher,
        preview=material.text_content[:1600],
    )


@router.get("/materials/{mid}/file")
def material_file(mid: int, request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    material = _get_material_or_404(db, mid)
    klass = _get_class_or_404(db, material.class_id)
    ensure_class_member(db, user, klass)
    if not material.stored_name:
        raise HTTPException(status_code=404, detail="This material has no attached file.")
    path = config.UPLOAD_DIR / material.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File is missing on disk.")
    return FileResponse(path, filename=material.original_name or path.name)


@router.post("/materials/{mid}/delete")
def material_delete(mid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    material = _get_material_or_404(db, mid)
    klass = _get_class_or_404(db, material.class_id)
    _require_owner(db, user, klass)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    if material.stored_name:
        path = config.UPLOAD_DIR / material.stored_name
        if path.exists():
            path.unlink()
    db.delete(material)
    db.commit()
    return redirect(f"/classes/{klass.id}", flash=f"Material '{material.title}' deleted.")
