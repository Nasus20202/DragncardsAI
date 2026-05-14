from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx

from game_service.api.app import create_app
from game_service.logic.session_manager import SessionNotFoundError
from game_service.logic.snapshots import GameStateSnapshot

SESSION_ID = "test-session-id"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def mock_session(**kwargs) -> MagicMock:
    session = MagicMock()
    session.session_id = SESSION_ID
    session.reset_game = AsyncMock(return_value={"game": {"stepId": 0}})
    session.set_seat = AsyncMock()
    session.set_spectator = AsyncMock()
    session.send_alert = AsyncMock()
    session.save_replay = AsyncMock()
    session.set_player_count = AsyncMock(return_value={"game": {"playerCount": 2}})
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
    session.get_state = AsyncMock(return_value={"game": {"roundNumber": 1}})
    for key, value in kwargs.items():
        setattr(session, key, value)
    return session


def mock_manager(session=None) -> MagicMock:
    manager = MagicMock()
    current_session = session or mock_session()

    async def get_session(sid):
        if sid == SESSION_ID:
            return current_session
        raise SessionNotFoundError(f"Session {sid!r} not found")

    manager.get_session = get_session
    manager.delete_session = AsyncMock()
    manager.list_sessions = MagicMock(return_value=[])

    @asynccontextmanager
    async def session_operation_lock(session_id: str, **kwargs):
        del session_id, kwargs
        yield

    manager.session_operation_lock = session_operation_lock
    return manager


def make_client(manager=None):
    app = create_app(session_manager=manager or mock_manager())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
