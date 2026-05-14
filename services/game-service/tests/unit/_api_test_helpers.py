from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from game_service.api.app import create_app
from game_service.logic.session_manager import SessionNotFoundError

SESSION_ID = "test-session-id"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def mock_session(plugin_name: str = "marvel-champions") -> MagicMock:
    session = MagicMock()
    session.session_id = SESSION_ID
    session.plugin_name = plugin_name
    return session


def mock_manager(session: MagicMock | None = None) -> MagicMock:
    manager = MagicMock()
    selected_session = session or mock_session()

    async def get_session(sid: str):
        if sid == SESSION_ID:
            return selected_session
        raise SessionNotFoundError(f"Session {sid!r} not found")

    manager.get_session = get_session
    manager.list_sessions = MagicMock(return_value=[])
    return manager


def make_client(manager: MagicMock | None = None) -> httpx.AsyncClient:
    app = create_app(session_manager=manager or mock_manager())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
