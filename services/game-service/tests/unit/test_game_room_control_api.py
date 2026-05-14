"""Unit tests for game room control API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

from game_service.logic.session_manager import BadGameStateError, SessionLockedError

from ._game_room_state_api_test_helpers import (
    SESSION_ID,
    UNKNOWN_ID,
    make_client,
    mock_manager,
    mock_session,
)


async def test_reset_game_200():
    async with make_client() as client:
        response = await client.post(f"/games/{SESSION_ID}/reset", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == SESSION_ID
    assert "state" in body


async def test_reset_game_with_save_and_reload():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/reset",
            json={"save": True, "reload_plugin": True},
        )

    assert response.status_code == 200
    session.reset_game.assert_awaited_once_with(save=True, reload_plugin=True)


async def test_reset_game_not_found():
    async with make_client() as client:
        response = await client.post(f"/games/{UNKNOWN_ID}/reset", json={})

    assert response.status_code == 404


async def test_bad_game_state_on_reset_returns_409():
    session = mock_session(reset_game=AsyncMock(side_effect=BadGameStateError("corrupted")))
    async with make_client(mock_manager(session)) as client:
        response = await client.post(f"/games/{SESSION_ID}/reset", json={})

    assert response.status_code == 409


async def test_set_seat_204():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/seat",
            json={"player_index": 0, "user_id": 42},
        )

    assert response.status_code == 204
    session.set_seat.assert_awaited_once_with(player_index=0, user_id=42)


async def test_set_seat_not_found():
    async with make_client() as client:
        response = await client.post(
            f"/games/{UNKNOWN_ID}/seat",
            json={"player_index": 0, "user_id": 42},
        )

    assert response.status_code == 404


async def test_set_spectator_204():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/spectator",
            json={"user_id": 7, "spectating": True},
        )

    assert response.status_code == 204
    session.set_spectator.assert_awaited_once_with(user_id=7, spectating=True)


async def test_set_spectator_not_found():
    async with make_client() as client:
        response = await client.post(
            f"/games/{UNKNOWN_ID}/spectator",
            json={"user_id": 7, "spectating": False},
        )

    assert response.status_code == 404


async def test_send_alert_204():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/alert",
            json={"message": "watch out!"},
        )

    assert response.status_code == 204
    session.send_alert.assert_awaited_once_with("watch out!")


async def test_send_alert_not_found():
    async with make_client() as client:
        response = await client.post(f"/games/{UNKNOWN_ID}/alert", json={"message": "x"})

    assert response.status_code == 404


async def test_save_replay_204():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.post(f"/games/{SESSION_ID}/replay")

    assert response.status_code == 204
    session.save_replay.assert_awaited_once()


async def test_save_replay_not_found():
    async with make_client() as client:
        response = await client.post(f"/games/{UNKNOWN_ID}/replay")

    assert response.status_code == 404


async def test_set_player_count_200():
    session = mock_session(set_player_count=AsyncMock(return_value={"game": {"players": 3}}))
    async with make_client(mock_manager(session)) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/player-count",
            json={"num_players": 3, "layout_id": "standard3Player"},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == SESSION_ID
    assert response.json()["state"]["game"]["players"] == 3
    session.set_player_count.assert_awaited_once_with(
        num_players=3,
        layout_id="standard3Player",
    )


async def test_set_player_count_not_found():
    async with make_client() as client:
        response = await client.post(
            f"/games/{UNKNOWN_ID}/player-count",
            json={"num_players": 2, "layout_id": "standard2Player"},
        )

    assert response.status_code == 404


async def test_set_player_count_rejects_invalid_num_players():
    async with make_client() as client:
        response = await client.post(
            f"/games/{SESSION_ID}/player-count",
            json={"num_players": 0},
        )

    assert response.status_code == 422


async def test_session_locked_error_returns_423():
    session = mock_session()
    manager = mock_manager(session)

    class _Locked:
        async def __aenter__(self):
            raise SessionLockedError("busy")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def locked(session_id: str, **kwargs):
        del session_id, kwargs
        return _Locked()

    manager.session_operation_lock = locked
    async with make_client(manager) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/actions", json={"type": "next_step"}
        )

    assert response.status_code == 423
