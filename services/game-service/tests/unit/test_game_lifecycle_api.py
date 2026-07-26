"""HTTP-level tests for the slug lookup endpoint and UUID-only enforcement.

The room slug is low-entropy and guessable, so it is accepted ONLY by the
dedicated read-only `GET /games/by-slug/{room_slug}` lookup. State/mutation/
delete endpoints stay UUID-only: a slug supplied there must surface as a 404.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx

from game_service.api.app import create_app
from game_service.logic.session_manager import SessionNotFoundError

SESSION_UUID = "11111111-1111-1111-1111-111111111111"
ROOM_SLUG = "lively-fog-1234"

_METADATA = {
    "session_id": SESSION_UUID,
    "plugin_name": "marvel-champions",
    "plugin_id": 1,
    "room_slug": ROOM_SLUG,
    "created_at": "2026-06-24T00:00:00+00:00",
    "frontend_url": None,
}


def _make_manager() -> MagicMock:
    manager = MagicMock()

    async def lookup_session_by_slug(room_slug: str):
        if room_slug == ROOM_SLUG:
            return dict(_METADATA)
        raise SessionNotFoundError(f"Session for room slug {room_slug!r} not found")

    async def get_session(session_id: str):
        if session_id == SESSION_UUID:
            session = MagicMock()
            session.session_id = SESSION_UUID
            session.plugin_name = "marvel-champions"
            session.get_state = AsyncMock(return_value={"game": {"roundNumber": 1}})
            session.close_room = AsyncMock()
            return session
        raise SessionNotFoundError(f"Session {session_id!r} not found")

    async def delete_session(session_id: str):
        if session_id != SESSION_UUID:
            raise SessionNotFoundError(f"Session {session_id!r} not found")

    @asynccontextmanager
    async def session_operation_lock(session_id: str, **kwargs):
        del session_id, kwargs
        yield

    manager.lookup_session_by_slug = lookup_session_by_slug
    manager.get_session = get_session
    manager.delete_session = delete_session
    manager.session_operation_lock = session_operation_lock
    return manager


def _make_client(manager=None):
    app = create_app(session_manager=manager or _make_manager())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_lookup_by_slug_returns_session_id():
    async with _make_client() as client:
        response = await client.get(f"/games/by-slug/{ROOM_SLUG}")
    assert response.status_code == 200
    body = response.json()
    assert body["session"]["session_id"] == SESSION_UUID
    assert body["session"]["room_slug"] == ROOM_SLUG


async def test_lookup_by_unknown_slug_returns_404():
    async with _make_client() as client:
        response = await client.get("/games/by-slug/no-such-room")
    assert response.status_code == 404


async def test_state_route_rejects_slug_as_not_found():
    # A slug supplied to a UUID-only state route must NOT resolve.
    async with _make_client() as client:
        response = await client.get(f"/games/{ROOM_SLUG}/state")
    assert response.status_code == 404


async def test_state_route_accepts_uuid():
    async with _make_client() as client:
        response = await client.get(f"/games/{SESSION_UUID}/state")
    assert response.status_code == 200


async def test_delete_route_rejects_slug_as_not_found():
    # A slug supplied to the delete route must NOT authorize deletion.
    async with _make_client() as client:
        response = await client.delete(f"/games/{ROOM_SLUG}")
    assert response.status_code == 404


async def test_delete_route_is_idempotent_for_already_gone_uuid():
    # A valid-UUID session that the reaper (or a prior teardown) already removed
    # must return success, not 404 — the client teardown is best-effort.
    gone_uuid = "99999999-9999-9999-9999-999999999999"
    async with _make_client() as client:
        response = await client.delete(f"/games/{gone_uuid}")
    assert response.status_code == 200
    assert response.json()["session_id"] == gone_uuid
