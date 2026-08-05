"""
Integration tests for GameSession and SessionManager.

Requires a running DragnCards instance with the Marvel Champions plugin installed.

Run with:
    pytest tests/integration/test_session_manager.py -v
"""

import asyncio
import hashlib
import json
import os
from collections import Counter
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.live

from game_service.logic.session_manager import SessionManager, SessionNotFoundError

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
        sessions = await manager.list_sessions()
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
    sessions = await manager.list_sessions()
    assert not any(s["session_id"] == session_id for s in sessions)


@pytest.mark.asyncio
async def test_get_nonexistent_session_raises(manager):
    """Getting a non-existent session raises SessionNotFoundError."""
    with pytest.raises(SessionNotFoundError):
        await manager.get_session("00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_invalid_plugin_raises(manager):
    """Creating a session with an unknown plugin raises SessionError."""
    from game_service.logic.session_manager import SessionError

    with pytest.raises(SessionError, match="not found"):
        await manager.create_session("nonexistent-plugin")


@pytest.mark.asyncio
async def test_credential_cache_serves_two_rooms_with_one_authentication(manager):
    """DRA-36: a cached credential is reused against the real DragnCards backend.

    Counted at the wire by wrapping httpx, because the point of the cache is the
    round trips it removes, not an internal flag.
    """
    import httpx

    from game_service.coordination.session_store import _RespConnection
    from game_service.dragncards.auth_cache import DragnCardsAuthCache

    valkey_url = os.environ.get("VALKEY_URL", "redis://localhost:6380/0")
    parsed = urlparse(valkey_url)
    cache = DragnCardsAuthCache(
        DRAGNCARDS_HTTP_URL,
        DEV_USER_EMAIL,
        DEV_USER_PASSWORD,
        valkey=_RespConnection(parsed.hostname or "localhost", parsed.port or 6379),
        ttl_seconds=900,
    )
    await cache.invalidate()
    manager._auth_cache = cache

    counts: Counter[str] = Counter()
    original_send = httpx.AsyncClient.send

    async def counting_send(self, request, **kwargs):
        counts[request.url.path] += 1
        return await original_send(self, request, **kwargs)

    httpx.AsyncClient.send = counting_send
    created: list[str] = []
    try:
        for _ in range(2):
            session = await manager.create_session("marvel-champions", ephemeral=True)
            created.append(session.session_id)
    finally:
        httpx.AsyncClient.send = original_send
        for session_id in created:
            try:
                await manager.delete_session(session_id)
            except Exception:
                pass
        await cache.invalidate()

    assert counts["/api/v1/games"] == 2, "both rooms must actually be created"
    assert counts["/api/v1/session"] == 1, "the second room must not re-authenticate"
    assert counts["/api/v1/profile"] == 1, "the user id must be cached with the token"


@pytest.mark.asyncio
async def test_a_valkey_outage_still_creates_a_room(manager):
    """DRA-36: the cache degrades to a live authentication, it never fails.

    Pointed at a port with nothing listening, which is the outage the shared RESP
    client actually produces (a refused connection per command).
    """
    from game_service.coordination.session_store import _RespConnection
    from game_service.dragncards.auth_cache import DragnCardsAuthCache

    manager._auth_cache = DragnCardsAuthCache(
        DRAGNCARDS_HTTP_URL,
        DEV_USER_EMAIL,
        DEV_USER_PASSWORD,
        valkey=_RespConnection("127.0.0.1", 6399),
        ttl_seconds=900,
    )

    session = await manager.create_session("marvel-champions", ephemeral=True)
    try:
        assert session.room_slug
        state = await session.get_state()
        assert isinstance(state, dict) and "game" in state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_reloading_a_room_leaves_no_trace_of_its_previous_state(manager):
    """DRA-36: the guarantee ephemeral-room reuse rests on.

    DragnCards implements the `set_game` action as a whole-document replacement
    (`GameUI.resolve_action_type/4` returns `options["game"]`), so a room that has
    held another state must end up byte-for-byte identical to a fresh one. Asserted
    against the real backend, because it is upstream behaviour this repository does
    not control: if a future DragnCards merged instead of replaced, reuse would
    silently start showing stale boards and only this test would notice.
    """
    reused = await manager.create_session("marvel-champions", ephemeral=True)
    fresh = await manager.create_session("marvel-champions", ephemeral=True)
    try:
        # Two genuinely different board states to move between.
        first = await reused.export_state()
        await reused.set_player_count(2)
        second = await reused.export_state()
        assert _digest(first.game) != _digest(
            second.game
        ), "the two states must differ, or this test proves nothing"

        # The reused room walks second -> first; the fresh room goes straight to it.
        await reused.load_state(first)
        await fresh.load_state(first)

        reused_after = await reused.export_state()
        fresh_after = await fresh.export_state()
        assert _digest(reused_after.game) == _digest(fresh_after.game)
    finally:
        for session in (reused, fresh):
            try:
                await manager.delete_session(session.session_id)
            except Exception:
                pass


def _digest(document: dict) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
