"""AI provider admin: teachers register endpoints/keys/models and pick the active one."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ai, security
from ..db import AiProvider
from ..deps import get_db, page_user
from ..web import redirect, render

router = APIRouter()

KINDS = ("openai_compat", "anthropic")


def _require_teacher(user) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can manage AI providers.")


def _get_provider_or_404(db: Session, provider_id: int) -> AiProvider:
    provider = db.get(AiProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    return provider


@router.get("/settings/ai")
def ai_settings_page(request: Request, db: Session = Depends(get_db)):
    user, _ = page_user(request, db)
    _require_teacher(user)
    providers = db.query(AiProvider).order_by(AiProvider.active.desc(), AiProvider.id).all()
    return render(request, db, "ai_settings.html", providers=providers, presets=ai.PROVIDER_PRESETS)


@router.post("/settings/ai/providers")
def provider_add(
    request: Request,
    name: str = Form(""),
    kind: str = Form("openai_compat"),
    base_url: str = Form(""),
    api_key: str = Form(""),
    model: str = Form(""),
    make_active: str = Form(""),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    name = name.strip()[:80]
    kind = kind if kind in KINDS else "openai_compat"
    base_url = base_url.strip().rstrip("/")
    model = model.strip()[:160]
    if not name:
        return redirect("/settings/ai", flash="Give the provider a name.", category="err")
    if not base_url.startswith(("http://", "https://")):
        return redirect("/settings/ai", flash="Base URL must start with http:// or https://", category="err")
    if not model:
        return redirect("/settings/ai", flash="Model is required.", category="err")
    if make_active:
        db.query(AiProvider).update({AiProvider.active: False})
    provider = AiProvider(
        name=name, kind=kind, base_url=base_url, api_key=api_key.strip(), model=model, active=bool(make_active)
    )
    db.add(provider)
    db.commit()
    state = " and activated" if make_active else ""
    return redirect("/settings/ai", flash=f"Provider '{name}' added{state}.")


@router.post("/settings/ai/providers/{provider_id}/activate")
def provider_activate(
    provider_id: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)
):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    provider = _get_provider_or_404(db, provider_id)
    db.query(AiProvider).update({AiProvider.active: False})
    provider.active = True
    db.commit()
    return redirect("/settings/ai", flash=f"'{provider.name}' is now the active provider.")


@router.post("/settings/ai/providers/{provider_id}/delete")
def provider_delete(provider_id: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    provider = _get_provider_or_404(db, provider_id)
    was_active = provider.active
    db.delete(provider)
    db.commit()
    if was_active:
        return redirect(
            "/settings/ai",
            flash=f"'{provider.name}' deleted — falling back to the .env OpenRouter config.",
        )
    return redirect("/settings/ai", flash=f"'{provider.name}' deleted.")


@router.post("/settings/ai/providers/{provider_id}/test")
async def provider_test(provider_id: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db)):
    user, sess = page_user(request, db)
    _require_teacher(user)
    if not security.csrf_ok(csrf, sess):
        raise HTTPException(status_code=403, detail="Bad CSRF token.")
    provider = _get_provider_or_404(db, provider_id)
    config = {
        "kind": provider.kind,
        "base_url": provider.base_url.strip().rstrip("/"),
        "api_key": provider.api_key.strip(),
        "model": provider.model,
    }
    ok, detail = await ai.test_provider(config)
    if ok:
        return redirect("/settings/ai", flash=f"✔ {provider.name}: {detail}")
    return redirect("/settings/ai", flash=f"✘ {provider.name}: {detail}", category="err")
