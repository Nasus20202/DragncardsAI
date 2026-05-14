"""Unit tests for game room observation endpoints (alerts/gui updates)."""

from __future__ import annotations

from unittest.mock import MagicMock

from ._game_room_state_api_test_helpers import (
    SESSION_ID,
    UNKNOWN_ID,
    make_client,
    mock_manager,
    mock_session,
)


async def test_get_alerts_200():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == SESSION_ID
    assert isinstance(body["alerts"], list)
    assert body["alerts"][0]["text"] == "hello"


async def test_get_alerts_empty_list():
    session = mock_session(get_alerts=MagicMock(return_value=[]))
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/alerts")

    assert response.status_code == 200
    assert response.json()["alerts"] == []


async def test_get_alerts_not_found():
    async with make_client() as client:
        response = await client.get(f"/games/{UNKNOWN_ID}/alerts")

    assert response.status_code == 404


async def test_get_gui_update_200():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/gui-update")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == SESSION_ID
    assert "player1" in body["updates"]
    assert body["updates"]["player1"]["prompt"] == "choose"


async def test_get_gui_update_empty():
    session = mock_session(get_gui_updates=MagicMock(return_value={}))
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/gui-update")

    assert response.status_code == 200
    assert response.json()["updates"] == {}


async def test_get_gui_update_not_found():
    async with make_client() as client:
        response = await client.get(f"/games/{UNKNOWN_ID}/gui-update")

    assert response.status_code == 404
