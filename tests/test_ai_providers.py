import re

"""Multi-provider AI: dashboard CRUD, activation, resolution order, anthropic shapes."""
import json

from app import ai, config
from app.db import AiProvider, SessionLocal
from tests.conftest import get_csrf, login, logout


def _login_admin(client):
    logout(client)
    login(client, "admin@nudge.test", "admin-pass-1")


def _add_provider(client, name="My Ollama", kind="openai_compat",
                  base_url="http://localhost:11434/v1", model="llama3.1",
                  api_key="", make_active="on"):
    return client.post(
        "/settings/ai/providers",
        data={"name": name, "kind": kind, "base_url": base_url, "api_key": api_key,
              "model": model, "make_active": make_active, "csrf": get_csrf(client)},
        follow_redirects=False,
    )


def test_provider_page_is_teacher_only(client, admin, student):
    _login_admin(client)
    assert client.get("/settings/ai").status_code == 200
    logout(client)
    login(client, student["email"], student["password"])
    assert client.get("/settings/ai").status_code == 403  # students can't manage AI
    logout(client)
    response = client.get("/settings/ai", follow_redirects=False)
    assert response.status_code == 303  # anonymous -> login
    assert response.headers["location"] == "/login"


def test_add_activate_and_resolve(client, admin):
    _login_admin(client)
    assert _add_provider(client).status_code == 303
    db = SessionLocal()
    provider = ai.resolve_provider(db)
    assert provider["name"] == "My Ollama"
    assert provider["kind"] == "openai_compat"
    assert provider["base_url"] == "http://localhost:11434/v1"
    db.close()

    # local Ollama without a key is considered ready
    assert ai._provider_ready(provider) is True


def test_activate_switches_active_provider(client, admin):
    _login_admin(client)
    _add_provider(client, name="First", model="m1")
    _add_provider(client, name="Second", model="m2", make_active="on")
    db = SessionLocal()
    assert ai.resolve_provider(db)["model"] == "m2"
    db.close()
    page = client.get("/settings/ai")
    provider_id = re.search(r"providers/(\d+)/activate", page.text).group(1)
    client.post(f"/settings/ai/providers/{provider_id}/activate", data={"csrf": get_csrf(client)}, follow_redirects=False)
    db = SessionLocal()
    assert ai.resolve_provider(db)["model"] == "m1"
    db.close()


def test_delete_active_falls_back_to_env(client, admin):
    _login_admin(client)
    _add_provider(client, name="Temp", model="m", make_active="on")
    page = client.get("/settings/ai")
    provider_id = re.search(r"providers/(\d+)/delete", page.text).group(1)
    client.post(f"/settings/ai/providers/{provider_id}/delete", data={"csrf": get_csrf(client)}, follow_redirects=False)
    db = SessionLocal()
    resolved = ai.resolve_provider(db)
    assert resolved["name"] == "OpenRouter (default)"
    assert resolved["api_key"] == config.OPENROUTER_API_KEY  # .env fallback survives
    db.close()


def test_add_rejects_bad_url_and_missing_model(client, admin):
    bad_url = _add_provider(client, name="X", base_url="openrouter.ai/api/v1", make_active="")
    assert bad_url.status_code == 303
    assert "http://" in client.get("/settings/ai", follow_redirects=True).text
    missing_model = client.post(
        "/settings/ai/providers",
        data={"name": "Y", "kind": "openai_compat", "base_url": "https://x/v1", "api_key": "",
              "model": "", "make_active": "", "csrf": get_csrf(client)},
        follow_redirects=False,
    )
    assert missing_model.status_code == 303


def test_anthropic_system_split_and_body_shape():
    messages = [
        {"role": "system", "content": "You are Nudge."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "question"},
    ]
    system, rest = ai._split_system(messages)
    assert system == "You are Nudge."
    assert [m["role"] for m in rest] == ["user", "assistant", "user"]

    provider = {"kind": "anthropic", "base_url": "https://api.anthropic.com", "api_key": "k", "model": "claude"}
    body = ai._build_body(provider, messages, stream=True, max_tokens=700)
    assert body["system"] == "You are Nudge."
    assert body["stream"] is True
    assert body["max_tokens"] == 700
    assert "temperature" not in body
    assert ai._endpoint(provider) == "https://api.anthropic.com/v1/messages"
    headers = ai._headers(provider)
    assert headers["x-api-key"] == "k"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in headers


def test_openai_compat_headers_and_endpoint():
    provider = {"kind": "openai_compat", "base_url": "https://openrouter.ai/api/v1", "api_key": "sk", "model": "m"}
    assert ai._endpoint(provider) == "https://openrouter.ai/api/v1/chat/completions"
    headers = ai._headers(provider)
    assert headers["Authorization"] == "Bearer sk"


def test_anthropic_deltas_parse_content_blocks(monkeypatch):
    """Feed a scripted Anthropic SSE stream through the generator."""
    lines = [
        'data: {"type": "content_block_start"}',
        'data: {"type": "content_block_delta", "delta": {"text": "Hel"}}',
        'data: {"type": "content_block_delta", "delta": {"text": "lo"}}',
        'data: {"type": "message_stop"}',
    ]

    class FakeSSE:
        status_code = 200

        async def aiter_lines(self_inner):
            for line in lines:
                yield line

        async def aread(self_inner):
            return b""

    class FakeResponse(FakeSSE):
        async def __aenter__(self_inner):
            return self_inner

        async def __aexit__(self_inner, *exc):
            return False

    class FakeClient:
        def __init__(self_inner, *a, **k):
            pass

        async def __aenter__(self_inner):
            return self_inner

        async def __aexit__(self_inner, *exc):
            return False

        def stream(self_inner, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(ai.httpx, "AsyncClient", FakeClient)

    async def consume():
        out = []
        async for delta in ai._anthropic_deltas(
            {"kind": "anthropic", "base_url": "https://api.anthropic.com", "api_key": "k", "model": "m"},
            {},
        ):
            out.append(delta)
        return out

    assert "".join(__import__("asyncio").run(consume())) == "Hello"


def test_resolve_provider_without_db_uses_env(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "envkey")
    monkeypatch.setattr(config, "MODEL", "env/model")
    resolved = ai.resolve_provider(None)
    assert resolved["api_key"] == "envkey"
    assert resolved["model"] == "env/model"
    assert resolved["kind"] == "openai_compat"


def test_provider_test_helper_reports_provider_errors(client, admin, monkeypatch):
    db = SessionLocal()
    _login_admin(client)
    _add_provider(client, name="Broken", base_url="https://broken.example/v1", model="m", api_key="bad")
    provider = db.query(AiProvider).filter(AiProvider.name == "Broken").first()
    config_dict = {
        "kind": provider.kind,
        "base_url": provider.base_url,
        "api_key": provider.api_key,
        "model": provider.model,
    }

    class ErrResponse:
        status_code = 401
        text = json.dumps({"error": {"message": "invalid api key"}})

        def json(self):
            return {}

    class ErrClient:
        def __init__(self_inner, *a, **k):
            pass

        async def __aenter__(self_inner):
            return self_inner

        async def __aexit__(self_inner, *exc):
            return False

        async def post(self_inner, *a, **k):
            return ErrResponse()

    monkeypatch.setattr(ai.httpx, "AsyncClient", ErrClient)

    import asyncio

    ok, detail = asyncio.run(ai.test_provider(config_dict))
    assert ok is False
    assert "API key" in detail or "key" in detail.lower()
    db.close()
