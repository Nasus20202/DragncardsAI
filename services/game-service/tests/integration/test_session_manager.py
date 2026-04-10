"""
Integration tests for GameSession and SessionManager.

Requires a running DragnCards instance with the Marvel Champions plugin installed.

Run with:
    pytest tests/integration/test_session_manager.py -v
"""

import asyncio
import os

import pytest

from game_service.session.manager import SessionManager, SessionNotFoundError

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev_user@example.com")
DEV_USER_PASSWORD = os.environ.get("DEV_USER_PASSWORD", "password")

PLUGIN_REGISTRY = {
    "marvel-champions": {
        "id": int(os.environ.get("MC_PLUGIN_ID", "1")),
        "version": int(os.environ.get("MC_PLUGIN_VERSION", "1")),
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


@pytest.mark.asyncio
async def test_create_session_returns_session_id(manager):
    """Creating a session returns a valid session with an ID and metadata."""
    session = await manager.create_session("marvel-champions")
    try:
        assert session.session_id
        assert session.plugin_name == "marvel-champions"
        assert session.room_slug
        assert session.created_at is not None
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_get_state_after_create(manager):
    """After creating a session, game state is available."""
    session = await manager.create_session("marvel-champions")
    try:
        state = await session.get_state()
        assert state is not None
        # DragnCards state always has a "game" key
        assert "game" in state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_list_sessions(manager):
    """list_sessions returns metadata for all active sessions."""
    session = await manager.create_session("marvel-champions")
    try:
        sessions = manager.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert session.session_id in ids
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_delete_session_removes_from_pool(manager):
    """Deleting a session removes it from the pool."""
    session = await manager.create_session("marvel-champions")
    session_id = session.session_id
    await manager.delete_session(session_id)
    sessions = manager.list_sessions()
    assert not any(s["session_id"] == session_id for s in sessions)


@pytest.mark.asyncio
async def test_get_nonexistent_session_raises(manager):
    """Getting a non-existent session raises SessionNotFoundError."""
    with pytest.raises(SessionNotFoundError):
        await manager.get_session("00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_invalid_plugin_raises(manager):
    """Creating a session with an unknown plugin raises SessionError."""
    from game_service.session.manager import SessionError

    with pytest.raises(SessionError, match="not found"):
        await manager.create_session("nonexistent-plugin")
