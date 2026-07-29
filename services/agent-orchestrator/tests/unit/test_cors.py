"""The browser CORS policy, pinned (DRA-31).

agent-orchestrator shipped with ``allow_origins=["*"]`` and no comment explaining
it. Compose publishes 4002 on the host, so any web page a developer happened to
visit while the stack was running could issue a cross-origin
``DELETE http://localhost:4002/sessions/{id}`` — destroying an agent session — or
``POST .../prompts``, spending the owner's model budget.

These tests fail if the wildcard comes back by either route: widening the
configured default in ``config.py``, or hardcoding ``["*"]`` in the app factory
again. The wire-level assertions cover the second case, which a config-only test
would miss.

They also pin the case the whole application depends on: a request carrying **no**
``Origin`` at all. Every real caller is in that class — the dashboard reaches this
service through its own server-side Node proxy, including the SSE job streams
(``EventSource`` against relative ``/api/proxy/orchestrator/...`` URLs), and
history-service is a server-to-server caller.
"""

from __future__ import annotations

import httpx
import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.app import create_app

FOREIGN_ORIGIN = "https://evil.example"
DASHBOARD_ORIGIN = "http://localhost:3001"

# Routes reachable cross-origin under the old wildcard that destroy state or spend
# the owner's money.
DESTRUCTIVE_PREFLIGHTS = [
    ("/sessions/some-session", "DELETE"),  # delete_session
    ("/sessions/some-session/prompts", "POST"),  # submit_prompt
]


def _client() -> httpx.AsyncClient:
    """A client over the real app factory.

    No lifespan is entered: CORS runs as middleware ahead of routing, and the only
    routed endpoint used here is ``/health``, which touches no database.
    """
    app = create_app(settings=Settings())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    )


def test_default_allowlist_is_the_dashboard_and_never_a_wildcard():
    origins = Settings().cors_allow_origins
    assert DASHBOARD_ORIGIN in origins
    assert "http://127.0.0.1:3001" in origins
    assert "*" not in origins


def test_allowlist_is_configurable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a.test , http://b.test ,")
    assert Settings().cors_allow_origins == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize(("path", "method"), DESTRUCTIVE_PREFLIGHTS)
async def test_foreign_origin_is_refused_a_destructive_preflight(
    path: str, method: str
):
    async with _client() as c:
        resp = await c.request(
            "OPTIONS",
            path,
            headers={
                "Origin": FOREIGN_ORIGIN,
                "Access-Control-Request-Method": method,
            },
        )

    # Starlette answers a disallowed preflight itself and, crucially, never grants
    # access-control-allow-origin — so the browser refuses to send the real request.
    # It does still echo access-control-allow-methods, which is inert on its own.
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
            "/sessions/some-session",
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
