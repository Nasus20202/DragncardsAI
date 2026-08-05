from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from game_service.logic.exceptions import SessionError
from game_service.logic.session_manager import SessionManager, SessionNotFoundError

from .cards_test_support import install_stub_marvel_provider
from .game_room_state_test_support import SESSION_ID, mock_session


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


def _make_manager(session=None):
    manager = SessionManager(
        dragncards_http_url="http://test",
        dragncards_ws_url="ws://test/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={
            "marvel-champions": {"id": 1, "version": 1, "name": "Marvel Champions"}
        },
    )
    current_session = session or mock_session()
    manager.get_session = AsyncMock(return_value=current_session)

    @asynccontextmanager
    async def session_operation_lock(session_id: str, **kwargs):
        del session_id, kwargs
        yield

    manager.session_operation_lock = session_operation_lock
    return manager


@pytest.mark.asyncio
async def test_session_manager_load_prebuilt_deck_calls_session():
    session = mock_session()
    manager = _make_manager(session)
    result = await manager.load_prebuilt_deck(SESSION_ID, "set-001")
    session.load_prebuilt_deck.assert_awaited_once_with(
        "Spider-Verse (Hero)", player_n="player1"
    )
    assert result is None or result == session.load_prebuilt_deck.return_value


@pytest.mark.asyncio
async def test_session_manager_load_prebuilt_deck_passes_the_seat_through():
    session = mock_session()
    manager = _make_manager(session)
    await manager.load_prebuilt_deck(SESSION_ID, "set-001", player_n="player3")
    session.load_prebuilt_deck.assert_awaited_once_with(
        "Spider-Verse (Hero)", player_n="player3"
    )


@pytest.mark.asyncio
async def test_session_manager_load_prebuilt_deck_rejects_a_non_seat():
    manager = _make_manager()
    with pytest.raises(ValueError):
        await manager.load_prebuilt_deck(SESSION_ID, "set-001", player_n="shared")


@pytest.mark.asyncio
async def test_session_manager_load_prebuilt_deck_missing_session():
    manager = _make_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("missing"))
    with pytest.raises(SessionNotFoundError):
        await manager.load_prebuilt_deck("missing", "set-001")


@pytest.mark.asyncio
async def test_session_manager_load_prebuilt_deck_missing_deck():
    session = mock_session()
    manager = _make_manager(session)
    with pytest.raises(SessionError):
        await manager.load_prebuilt_deck(SESSION_ID, "missing")
