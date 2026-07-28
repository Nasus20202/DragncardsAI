"""HTTP-level tests for session identification by UUID or room slug.

Every endpoint that identifies a session accepts either the UUID `session_id` or
the human-readable DragnCards room slug — reads, mutations, and delete alike. An
identifier that resolves to neither is a 404; a slug shared by more than one live
session is a 409.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx

from game_service.api.app import create_app
from game_service.logic.session_manager import (
    AmbiguousSessionIdentifierError,
    SessionNotFoundError,
)

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

    async def resolve_session_id(identifier: str):
        if identifier == ROOM_SLUG:
            return SESSION_UUID
        try:
            return str(uuid.UUID(identifier))
        except ValueError:
            raise SessionNotFoundError(
                f"{identifier!r} is neither a session id nor a known room slug"
            ) from None

    async def lookup_session_by_slug(room_slug: str):
        if room_slug == ROOM_SLUG:
            return dict(_METADATA)
        raise SessionNotFoundError(f"Session for room slug {room_slug!r} not found")

    async def get_session(session_id: str):
        if await resolve_session_id(session_id) == SESSION_UUID:
            session = MagicMock()
            session.session_id = SESSION_UUID
            session.plugin_name = "marvel-champions"
            session.get_state = AsyncMock(return_value={"game": {"roundNumber": 1}})
            session.close_room = AsyncMock()
            return session
        raise SessionNotFoundError(f"Session {session_id!r} not found")

    async def delete_session(session_id: str):
        if await resolve_session_id(session_id) != SESSION_UUID:
            raise SessionNotFoundError(f"Session {session_id!r} not found")

    @asynccontextmanager
    async def session_operation_lock(session_id: str, **kwargs):
        del kwargs
        await resolve_session_id(session_id)
        yield

    manager.resolve_session_id = resolve_session_id
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


async def test_state_route_accepts_slug():
    async with _make_client() as client:
        response = await client.get(f"/games/{ROOM_SLUG}/state")
    assert response.status_code == 200


async def test_state_route_accepts_uuid():
    async with _make_client() as client:
        response = await client.get(f"/games/{SESSION_UUID}/state")
    assert response.status_code == 200


async def test_state_route_rejects_unknown_identifier():
    async with _make_client() as client:
        response = await client.get("/games/no-such-room/state")
    assert response.status_code == 404


async def test_delete_route_accepts_slug_and_reports_canonical_id():
    async with _make_client() as client:
        response = await client.delete(f"/games/{ROOM_SLUG}")
    assert response.status_code == 200
    assert response.json()["session_id"] == SESSION_UUID


async def test_delete_route_rejects_unknown_identifier():
    async with _make_client() as client:
        response = await client.delete("/games/no-such-room")
    assert response.status_code == 404


async def test_delete_route_is_idempotent_for_already_gone_uuid():
    # A valid-UUID session that the reaper (or a prior teardown) already removed
    # must return success, not 404 — the client teardown is best-effort.
    gone_uuid = "99999999-9999-9999-9999-999999999999"
    async with _make_client() as client:
        response = await client.delete(f"/games/{gone_uuid}")
    assert response.status_code == 200
    assert response.json()["session_id"] == gone_uuid


async def test_ambiguous_slug_returns_409():
    manager = _make_manager()

    async def resolve_session_id(identifier: str):
        raise AmbiguousSessionIdentifierError(
            f"Room slug {identifier!r} matches 2 sessions"
        )

    manager.resolve_session_id = resolve_session_id

    @asynccontextmanager
    async def session_operation_lock(session_id: str, **kwargs):
        del kwargs
        await resolve_session_id(session_id)
        yield

    manager.session_operation_lock = session_operation_lock

    async with _make_client(manager) as client:
        state_response = await client.get(f"/games/{ROOM_SLUG}/state")
        delete_response = await client.delete(f"/games/{ROOM_SLUG}")
    assert state_response.status_code == 409
    assert delete_response.status_code == 409
