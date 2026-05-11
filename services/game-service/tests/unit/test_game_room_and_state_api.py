"""Unit tests for split game room and state HTTP routes.

Uses httpx.AsyncClient with ASGITransport plus a mocked SessionManager/GameSession,
so no real DragnCards backend is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from game_service.api.app import create_app
from game_service.logic.session_manager import (
    BadGameStateError,
    SessionNotFoundError,
    StateUnavailableError,
)
from game_service.logic.snapshots import GameStateSnapshot

SESSION_ID = "test-session-id"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(**kwargs) -> MagicMock:
    session = MagicMock()
    session.session_id = SESSION_ID
    session.reset_game = AsyncMock(return_value={"game": {"stepId": 0}})
    session.set_seat = AsyncMock()
    session.set_spectator = AsyncMock()
    session.send_alert = AsyncMock()
    session.save_replay = AsyncMock()
    session.export_state = AsyncMock(
        return_value=GameStateSnapshot(
            schema_version=1,
            plugin_name="marvel-champions",
            game={"roundNumber": 0},
        )
    )
    session.load_state = AsyncMock(return_value={"game": {"roundNumber": 2}})
    session.get_alerts = MagicMock(return_value=[{"level": "info", "text": "hello"}])
    session.get_gui_updates = MagicMock(
        return_value={"player1": {"player_n": "player1", "prompt": "choose"}}
    )
    session.get_state = AsyncMock(return_value={"game": {}})
    for k, v in kwargs.items():
        setattr(session, k, v)
    return session


def _mock_manager(session=None) -> MagicMock:
    manager = MagicMock()
    _session = session or _mock_session()

    async def get_session(sid):
        if sid == SESSION_ID:
            return _session
        raise SessionNotFoundError(f"Session {sid!r} not found")

    manager.get_session = get_session
    manager.delete_session = AsyncMock()
    manager.list_sessions = MagicMock(return_value=[])
    return manager


def _make_client(manager=None):
    app = create_app(session_manager=manager or _mock_manager())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


# ---------------------------------------------------------------------------
# 4.11 — POST /games/{id}/reset
# ---------------------------------------------------------------------------


async def test_reset_game_200():
    async with _make_client() as client:
        resp = await client.post(f"/games/{SESSION_ID}/reset", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == SESSION_ID
    assert "state" in body


async def test_reset_game_with_save_and_reload():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.post(
            f"/games/{SESSION_ID}/reset",
            json={"save": True, "reload_plugin": True},
        )
    assert resp.status_code == 200
    session.reset_game.assert_awaited_once_with(save=True, reload_plugin=True)


async def test_reset_game_not_found():
    async with _make_client() as client:
        resp = await client.post(f"/games/{UNKNOWN_ID}/reset", json={})
    assert resp.status_code == 404


async def test_export_snapshot_200():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.get(f"/games/{SESSION_ID}/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["plugin_name"] == "marvel-champions"
    assert body["game"]["roundNumber"] == 0


async def test_load_snapshot_200():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "marvel-champions",
                "game": {"roundNumber": 2},
            },
        )
    assert resp.status_code == 200
    session.load_state.assert_awaited_once()
    assert resp.json()["state"]["game"]["roundNumber"] == 2


async def test_load_snapshot_validation_error_returns_400():
    from game_service.logic.session_manager import SnapshotValidationError

    session = _mock_session()
    session.load_state = AsyncMock(
        side_effect=SnapshotValidationError("plugin mismatch")
    )
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "other-game",
                "game": {},
            },
        )
    assert resp.status_code == 400
    assert "plugin mismatch" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4.12 — POST /games/{id}/seat  and  POST /games/{id}/spectator
# ---------------------------------------------------------------------------


async def test_set_seat_204():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.post(
            f"/games/{SESSION_ID}/seat",
            json={"player_index": 0, "user_id": 42},
        )
    assert resp.status_code == 204
    session.set_seat.assert_awaited_once_with(player_index=0, user_id=42)


async def test_set_seat_not_found():
    async with _make_client() as client:
        resp = await client.post(
            f"/games/{UNKNOWN_ID}/seat",
            json={"player_index": 0, "user_id": 42},
        )
    assert resp.status_code == 404


async def test_set_spectator_204():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.post(
            f"/games/{SESSION_ID}/spectator",
            json={"user_id": 7, "spectating": True},
        )
    assert resp.status_code == 204
    session.set_spectator.assert_awaited_once_with(user_id=7, spectating=True)


async def test_set_spectator_not_found():
    async with _make_client() as client:
        resp = await client.post(
            f"/games/{UNKNOWN_ID}/spectator",
            json={"user_id": 7, "spectating": False},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4.13 — POST /games/{id}/alert  and  POST /games/{id}/replay
# ---------------------------------------------------------------------------


async def test_send_alert_204():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.post(
            f"/games/{SESSION_ID}/alert",
            json={"message": "watch out!"},
        )
    assert resp.status_code == 204
    session.send_alert.assert_awaited_once_with("watch out!")


async def test_send_alert_not_found():
    async with _make_client() as client:
        resp = await client.post(f"/games/{UNKNOWN_ID}/alert", json={"message": "x"})
    assert resp.status_code == 404


async def test_save_replay_204():
    session = _mock_session()
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.post(f"/games/{SESSION_ID}/replay")
    assert resp.status_code == 204
    session.save_replay.assert_awaited_once()


async def test_save_replay_not_found():
    async with _make_client() as client:
        resp = await client.post(f"/games/{UNKNOWN_ID}/replay")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4.14 — GET /games/{id}/alerts  and  GET /games/{id}/gui-update
# ---------------------------------------------------------------------------


async def test_get_alerts_200():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == SESSION_ID
    assert isinstance(body["alerts"], list)
    assert body["alerts"][0]["text"] == "hello"


async def test_get_alerts_empty_list():
    session = _mock_session()
    session.get_alerts = MagicMock(return_value=[])
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.get(f"/games/{SESSION_ID}/alerts")
    assert resp.status_code == 200
    assert resp.json()["alerts"] == []


async def test_get_alerts_not_found():
    async with _make_client() as client:
        resp = await client.get(f"/games/{UNKNOWN_ID}/alerts")
    assert resp.status_code == 404


async def test_get_gui_update_200():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/gui-update")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == SESSION_ID
    assert "player1" in body["updates"]
    assert body["updates"]["player1"]["prompt"] == "choose"


async def test_get_gui_update_empty():
    session = _mock_session()
    session.get_gui_updates = MagicMock(return_value={})
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.get(f"/games/{SESSION_ID}/gui-update")
    assert resp.status_code == 200
    assert resp.json()["updates"] == {}


async def test_get_gui_update_not_found():
    async with _make_client() as client:
        resp = await client.get(f"/games/{UNKNOWN_ID}/gui-update")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4.15 — BadGameStateError → 409  and  StateUnavailableError → 503
# ---------------------------------------------------------------------------


async def test_bad_game_state_error_returns_409():
    session = _mock_session()
    session.get_state = AsyncMock(
        side_effect=BadGameStateError("game state is corrupted")
    )
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.get(f"/games/{SESSION_ID}/state")
    assert resp.status_code == 409
    assert "corrupted" in resp.json()["detail"]


async def test_state_unavailable_error_returns_503():
    session = _mock_session()
    session.get_state = AsyncMock(
        side_effect=StateUnavailableError("state temporarily unavailable")
    )
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.get(f"/games/{SESSION_ID}/state")
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"]


async def test_bad_game_state_on_reset_returns_409():
    session = _mock_session()
    session.reset_game = AsyncMock(side_effect=BadGameStateError("corrupted"))
    async with _make_client(_mock_manager(session)) as client:
        resp = await client.post(f"/games/{SESSION_ID}/reset", json={})
    assert resp.status_code == 409
