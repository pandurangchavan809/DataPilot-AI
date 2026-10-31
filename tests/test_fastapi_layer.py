"""Behaviour of the FastAPI layer: error format, limits, CORS and SSE."""

import asyncio
import threading
import time

from fastapi.testclient import TestClient

from app import create_app
from app.api import chat as chat_api
from app.config import Settings

ORIGIN = {"Origin": "http://localhost:5173"}


def make_client(tmp_path, **overrides):
    settings = Settings(
        secret_key="test-secret-key-for-pytest-only-0123456789",
        demo_db_path=tmp_path / "demo.db",
        auth_db_path=tmp_path / "auth.db",
        **overrides,
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_errors_use_one_json_format(client):
    assert client.get("/api/nope").json()["error"]["code"] == "not_found"
    assert client.get("/api/auth/login").json()["error"]["code"] == "method_not_allowed"


def test_bad_body_is_400_and_never_echoes_the_password(client):
    resp = client.post("/api/auth/login", json={"email": "a@b.co", "password": 12345678})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"
    assert resp.json()["error"]["message"].startswith("password:")
    assert "12345678" not in resp.text


def test_invalid_json_is_400(client):
    resp = client.post("/api/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_oversized_body_is_rejected(client):
    resp = client.post(
        "/api/auth/login", content=b"x" * (1024 * 1024 + 1), headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 413


def test_rate_limit_returns_429_in_our_format(tmp_path):
    client = make_client(tmp_path, auth_rate_limit="2/minute")
    bad = {"email": "user", "password": "wrong"}
    assert [client.post("/api/auth/login", json=bad).status_code for _ in range(3)] == [401, 401, 429]
    assert client.post("/api/auth/login", json=bad).json()["error"]["code"] == "rate_limited"


def test_rate_limit_uses_the_proxy_ip_and_ignores_faked_addresses(tmp_path):
    client = make_client(tmp_path, auth_rate_limit="1/minute", proxy_fix_hops=1)
    bad = {"email": "user", "password": "wrong"}

    def attempt(forwarded):
        return client.post("/api/auth/login", json=bad, headers={"X-Forwarded-For": forwarded}).status_code

    assert attempt("1.1.1.1") == 401
    assert attempt("9.9.9.9, 1.1.1.1") == 429  # a faked left-hand address doesn't get a fresh limit
    assert attempt("2.2.2.2") == 401  # a different real client does


def test_cors_allows_the_frontend_and_the_auth_header(client):
    resp = client.options(
        "/api/config",
        headers={**ORIGIN, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN["Origin"]
    evil = client.options(
        "/api/config", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in evil.headers


def test_unexpected_errors_are_json_and_keep_cors_headers(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    def boom(*_):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(client.app.state.services.registry, "available_models", boom)
    resp = client.get("/api/health", headers=ORIGIN)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in resp.text
    assert resp.headers["access-control-allow-origin"] == ORIGIN["Origin"]


def test_app_error_status_is_kept(client):
    assert client.post("/api/auth/refresh", json={"refresh_token": "garbage"}).status_code == 401


def test_chat_streams_sse_with_the_right_headers(client, headers, monkeypatch):
    client.post("/api/connections", json={"type": "sqlite_demo"}, headers=headers)

    def fake_run(_ctx):
        yield "token", {"text": "hi"}
        yield "done", {"models": []}

    monkeypatch.setattr(chat_api.orchestrator, "run", fake_run)
    resp = client.post("/api/chat", json={"message": "hello"}, headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-accel-buffering"] == "no"
    assert resp.text.startswith(": stream-open")
    assert "event: token" in resp.text and "event: done" in resp.text


def test_stream_ends_instead_of_hanging_when_the_worker_breaks(monkeypatch):
    def broken_run(_ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_api.orchestrator, "run", broken_run)

    async def consume():
        return [chunk async for chunk in chat_api.stream_events(None)]

    assert asyncio.run(asyncio.wait_for(consume(), 5)) == [": stream-open\n\n"]


def test_events_arrive_live_and_the_run_stops_when_the_client_disconnects(monkeypatch):
    produced = []
    finished = threading.Event()

    def slow_run(_ctx):
        try:
            for i in range(50):
                time.sleep(0.05)
                produced.append(i)
                yield "token", {"text": str(i)}
        finally:
            finished.set()

    monkeypatch.setattr(chat_api.orchestrator, "run", slow_run)

    async def consume():
        stream = chat_api.stream_events(None)
        assert (await anext(stream)).startswith(": stream-open")
        started = time.perf_counter()
        first = await anext(stream)
        assert "event: token" in first
        assert time.perf_counter() - started < 1  # not waiting for all 50 events (2.5 s)
        await stream.aclose()  # the client disconnects

    asyncio.run(consume())
    assert finished.wait(2), "the agent run kept going after the disconnect"
    assert len(produced) < 50
