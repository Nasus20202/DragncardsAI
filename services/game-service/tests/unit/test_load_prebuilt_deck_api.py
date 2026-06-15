from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from game_service.logic.exceptions import SessionError, SessionNotFoundError

from .cards_test_support import install_stub_marvel_provider, make_client, mock_manager
from .game_room_state_test_support import SESSION_ID, UNKNOWN_ID, mock_session


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


async def test_load_prebuilt_deck_200():
    session = mock_session()
    manager = mock_manager(session)
    manager.load_prebuilt_deck = AsyncMock(return_value={"game": {}})
    async with make_client(manager) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/load-prebuilt-deck", params={"deck_id": "set-001"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == SESSION_ID
    assert body["success"] is True
    manager.load_prebuilt_deck.assert_awaited_once_with(SESSION_ID, "set-001")


async def test_load_prebuilt_deck_not_found():
    manager = mock_manager()
    manager.load_prebuilt_deck = AsyncMock(side_effect=SessionNotFoundError("missing"))
    async with make_client(manager) as client:
        response = await client.post(
            f"/games/{UNKNOWN_ID}/load-prebuilt-deck", params={"deck_id": "set-001"}
        )

    assert response.status_code == 404


async def test_load_prebuilt_deck_missing_deck_rejected():
    manager = mock_manager()
    manager.load_prebuilt_deck = AsyncMock(side_effect=SessionError("missing deck"))
    async with make_client(manager) as client:
        response = await client.post(
            f"/games/{SESSION_ID}/load-prebuilt-deck", params={"deck_id": "missing"}
        )

    assert response.status_code == 400
