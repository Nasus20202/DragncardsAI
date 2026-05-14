"""Unit tests for /games/{id}/state and snapshot API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

from game_service.logic.session_manager import BadGameStateError, StateUnavailableError

from ._game_room_state_api_test_helpers import (
    SESSION_ID,
    UNKNOWN_ID,
    make_client,
    mock_manager,
    mock_session,
)


async def test_get_game_state_200():
    session = mock_session(get_state=AsyncMock(return_value={"game": {"roundNumber": 4}}))
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")

    assert response.status_code == 200
    assert response.json()["state"]["game"]["roundNumber"] == 4


async def test_get_game_state_not_found():
    async with make_client() as client:
        response = await client.get(f"/games/{UNKNOWN_ID}/state")

    assert response.status_code == 404


async def test_bad_game_state_error_returns_409():
    session = mock_session(
        get_state=AsyncMock(side_effect=BadGameStateError("game state is corrupted"))
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")

    assert response.status_code == 409
    assert "corrupted" in response.json()["detail"]


async def test_state_unavailable_error_returns_503():
    session = mock_session(
        get_state=AsyncMock(
            side_effect=StateUnavailableError("state temporarily unavailable")
        )
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


async def test_export_snapshot_200():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["plugin_name"] == "marvel-champions"
    assert body["game"]["roundNumber"] == 0


async def test_export_snapshot_not_found():
    async with make_client() as client:
        response = await client.get(f"/games/{UNKNOWN_ID}/snapshot")

    assert response.status_code == 404


async def test_load_snapshot_200():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "marvel-champions",
                "game": {"roundNumber": 2},
            },
        )

    assert response.status_code == 200
    session.load_state.assert_awaited_once()
    assert response.json()["state"]["game"]["roundNumber"] == 2


async def test_load_snapshot_not_found():
    async with make_client() as client:
        response = await client.put(
            f"/games/{UNKNOWN_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "marvel-champions",
                "game": {},
            },
        )

    assert response.status_code == 404


async def test_load_snapshot_validation_error_returns_400():
    from game_service.logic.session_manager import SnapshotValidationError

    session = mock_session(
        load_state=AsyncMock(side_effect=SnapshotValidationError("plugin mismatch"))
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "other-game",
                "game": {},
            },
        )

    assert response.status_code == 400
    assert "plugin mismatch" in response.json()["detail"]


async def test_load_snapshot_requires_game_payload():
    async with make_client() as client:
        response = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "marvel-champions",
            },
        )

    assert response.status_code == 422
