from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import SessionLocal, init_db
from .deps import PageRedirect
from .routes import ALL_ROUTERS
from .settings import users_exist
from .web import templates

log = logging.getLogger("nudge")


def _verify_model() -> None:
    """Best-effort startup check that the configured OpenRouter model exists."""
    try:
        resp = httpx.get(f"{config.OPENROUTER_BASE_URL}/models", timeout=10)
        ids = {m["id"] for m in resp.json().get("data", [])}
        if config.MODEL in ids:
            log.info("OpenRouter model OK: %s", config.MODEL)
        else:
            log.warning("Model %r is not in the OpenRouter catalog — chat will fail. Fix MODEL in .env", config.MODEL)
    except Exception as exc:  # the app should still start when offline
        log.warning("Could not verify OpenRouter model: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _verify_model()
    yield


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="Nudge", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=config.BASE_DIR / "app" / "static"), name="static")
    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.middleware("http")
    async def _setup_gate(request: Request, call_next):
        """Until an account exists, funnel everything into first-run setup."""
        path = request.url.path
        if not (path.startswith("/static") or path.startswith("/setup")):
            db = SessionLocal()
            try:
                if not users_exist(db):
                    return RedirectResponse("/setup", status_code=303)
            finally:
                db.close()
        return await call_next(request)

    @app.exception_handler(PageRedirect)
    async def _page_redirect_handler(request: Request, exc: PageRedirect):
        return RedirectResponse(exc.url, status_code=303)

    @app.exception_handler(HTTPException)
    async def _http_error_handler(request: Request, exc: HTTPException):
        if 300 <= exc.status_code < 400:
            return RedirectResponse("/", status_code=exc.status_code)
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"status": exc.status_code, "detail": exc.detail, "user": None, "csrf": "", "flash": None},
            status_code=exc.status_code,
        )

    return app


app = create_app()
