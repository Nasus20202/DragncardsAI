"""The browser CORS policy, pinned (DRA-31).

eval-service was the one service that already carried a strict allowlist, and its
shape is what the other three were brought into line with. Its policy was only
covered at the config level (``test_config.test_cors_origins_default_and_parse``),
so an edit hardcoding ``["*"]`` back into the app factory would have passed every
test. These wire-level assertions close that gap, so all four services now pin the
policy the same way.

They also pin the case the whole application depends on: a request carrying **no**
``Origin`` at all. The dashboard reaches this service through its own server-side
Node proxy, so that is the class every real caller falls into.
"""

from __future__ import annotations

import httpx
import pytest

from eval_service.config import Settings
from eval_service.runtime.app import create_app

FOREIGN_ORIGIN = "https://evil.example"
DASHBOARD_ORIGIN = "http://localhost:3001"


def _client() -> httpx.AsyncClient:
    """A client over the real app factory.

    No lifespan is entered and no worker is started: CORS runs as middleware ahead
    of routing, and the only routed endpoint used here is ``/health``, which
    touches no database.
    """
    app = create_app(settings=Settings(), start_worker=False)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    )


def test_default_allowlist_is_the_dashboard_and_never_a_wildcard():
    origins = Settings().cors_allow_origins
    assert DASHBOARD_ORIGIN in origins
    assert "http://127.0.0.1:3001" in origins
    assert "*" not in origins


async def test_foreign_origin_is_refused_a_destructive_preflight():
    async with _client() as c:
        resp = await c.request(
            "OPTIONS",
            "/evaluations/some-request",
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
            "/evaluations/some-request",
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


def test_allowlist_is_configurable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EVAL_CORS_ALLOW_ORIGINS", "http://a.test , http://b.test ,")
    assert Settings().cors_allow_origins == ["http://a.test", "http://b.test"]
