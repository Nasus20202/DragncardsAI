"""
Integration tests for the FastAPI HTTP REST API.

Requires a running DragnCards instance with the Marvel Champions plugin installed.

Run with:
    pytest tests/integration/test_api.py -v

Note: Tests that call endpoints which invoke WebSocket operations (execute_action,
get_state) must use httpx.AsyncClient with the ASGI transport to avoid blocking
the asyncio event loop (which would prevent the WebSocket receiver task from running).
Tests that only need synchronous HTTP (health, list, 404 checks) use TestClient.
"""

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from game_service.api.app import create_app
from game_service.session.manager import SessionManager

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev_user@example.com")
DEV_USER_PASSWORD = os.environ.get("DEV_USER_PASSWORD", "password")

PLUGIN_REGISTRY = {
    "marvel-champions": {
        "id": int(os.environ.get("MC_PLUGIN_ID", "1")),
        "version": int(os.environ.get("MC_PLUGIN_VERSION", "3")),
        "name": "Marvel Champions",
    }
}


@pytest.fixture
def manager():
    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=DEV_USER_EMAIL,
        password=DEV_USER_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
    )


@pytest.fixture
def app(manager):
    return create_app(session_manager=manager)


@pytest.fixture
def sync_client(app):
    """Synchronous TestClient — use only for endpoints that don't touch WebSocket."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Health check  (sync safe — no WebSocket)
# ---------------------------------------------------------------------------


def test_health(sync_client):
    """GET /health returns 200 ok."""
    resp = sync_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /games  (sync safe — just reads in-memory list)
# ---------------------------------------------------------------------------


def test_list_games_empty(sync_client):
    """GET /games on a fresh manager returns an empty list."""
    resp = sync_client.get("/games")
    assert resp.status_code == 200
    assert resp.json() == {"sessions": []}


@pytest.mark.asyncio
async def test_list_games_with_session(app, manager):
    """GET /games lists the active session."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/games")
        assert resp.status_code == 200
        ids = [s["session_id"] for s in resp.json()["sessions"]]
        assert session.session_id in ids
    finally:
        await manager.delete_session(session.session_id)


# ---------------------------------------------------------------------------
# POST /games
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_game(app, manager):
    """POST /games creates a session and returns metadata."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/games", json={"plugin_name": "marvel-champions"})
    assert resp.status_code == 201
    body = resp.json()
    assert "session" in body
    session = body["session"]
    assert "session_id" in session
    assert session["plugin_name"] == "marvel-champions"
    assert "room_slug" in session
    assert "created_at" in session
    # Cleanup
    await manager.delete_session(session["session_id"])


@pytest.mark.asyncio
async def test_create_game_unknown_plugin(app):
    """POST /games with an unknown plugin returns 400."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/games", json={"plugin_name": "nonexistent-plugin"})
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /games/{id}/state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_game_state(app, manager):
    """GET /games/{id}/state returns the current game state."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/games/{session.session_id}/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["state"] is not None
        assert "game" in body["state"]
    finally:
        await manager.delete_session(session.session_id)


def test_get_game_state_not_found(sync_client):
    """GET /games/{id}/state with unknown ID returns 404."""
    resp = sync_client.get("/games/00000000-0000-0000-0000-000000000000/state")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /games/{id}/actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_action_next_step(app, manager):
    """POST /games/{id}/actions with next_step returns updated state."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/games/{session.session_id}/actions",
                json={"type": "next_step"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["state"] is not None
    finally:
        await manager.delete_session(session.session_id)


def test_execute_action_not_found(sync_client):
    """POST /games/{id}/actions with unknown session ID returns 404."""
    resp = sync_client.post(
        "/games/00000000-0000-0000-0000-000000000000/actions",
        json={"type": "next_step"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /games/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_game(app, manager):
    """DELETE /games/{id} deletes the session."""
    session = await manager.create_session("marvel-champions")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(f"/games/{session.session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["deleted"] is True

        # Session should be gone
        resp2 = await client.get(f"/games/{session.session_id}/state")
        assert resp2.status_code == 404


def test_delete_game_not_found(sync_client):
    """DELETE /games/{id} with unknown ID returns 404."""
    resp = sync_client.delete("/games/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
