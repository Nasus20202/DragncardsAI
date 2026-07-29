"""The browser CORS policy, pinned (DRA-31).

game-service shipped with ``allow_origins=["*"]`` and a comment conceding it was a
development shortcut. Compose publishes 4001 on the host, so any web page a
developer happened to visit while the stack was running could issue a cross-origin
``DELETE http://localhost:4001/games/{session_id}`` — or drive the mutating action
routes — and the browser would carry it out.

These tests fail if the wildcard comes back by either route: widening
``DEFAULT_CORS_ALLOW_ORIGINS``, or hardcoding ``["*"]`` in the app factory again.
The wire-level assertions cover the second case, which a config-only test would
miss.

They also pin the case the whole application depends on: a request carrying **no**
``Origin`` at all. Every real caller is in that class — the dashboard reaches this
service through its own server-side Node proxy, the orchestrator and history-service
are server-to-server, MCP clients are not browsers, and this service's own /docs
playground is same-origin, which CORS never applies to.
"""

from __future__ import annotations

import httpx
import pytest

from game_service.api.app import cors_allow_origins, create_app

FOREIGN_ORIGIN = "https://evil.example"
DASHBOARD_ORIGIN = "http://localhost:3001"


def _client() -> httpx.AsyncClient:
    """A client over the real app factory.

    CORS runs as middleware ahead of routing, and the only routed endpoint used
    here is ``/health``, which needs no session manager.
    """
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://t"
    )


def test_default_allowlist_is_the_dashboard_and_never_a_wildcard(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    origins = cors_allow_origins()
    assert DASHBOARD_ORIGIN in origins
    assert "http://127.0.0.1:3001" in origins
    assert "*" not in origins


def test_allowlist_is_configurable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a.test , http://b.test ,")
    assert cors_allow_origins() == ["http://a.test", "http://b.test"]


async def test_foreign_origin_is_refused_a_destructive_preflight():
    async with _client() as c:
        resp = await c.request(
            "OPTIONS",
            "/games/some-session",
            headers={
                "Origin": FOREIGN_ORIGIN,
                "Access-Control-Request-Method": "DELETE",
            },
        )

    # Starlette answers a disallowed preflight itself and, crucially, never grants
    # access-control-allow-origin — so the browser refuses to send the DELETE. It
    # does still echo access-control-allow-methods, which is inert on its own.
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


async def test_foreign_origin_cannot_read_a_cross_origin_response():
    async with _client() as c:
        resp = await c.get("/health", headers={"Origin": FOREIGN_ORIGIN})

    assert "access-control-allow-origin" not in resp.headers


async def test_dashboard_origin_is_still_granted_its_preflight():
    async with _client() as c:
        resp = await c.request(
            "OPTIONS",
            "/games/some-session",
            headers={
                "Origin": DASHBOARD_ORIGIN,
                "Access-Control-Request-Method": "DELETE",
            },
        )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == DASHBOARD_ORIGIN


async def test_a_request_with_no_origin_is_untouched():
    """The path every real caller uses, including the dashboard's own proxy."""
    async with _client() as c:
        resp = await c.get("/health")

    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
