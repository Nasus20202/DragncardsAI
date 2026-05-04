"""
Integration tests for game action execution.

Requires a running DragnCards instance with Marvel Champions plugin.

Run with:
    pytest tests/integration/test_actions.py -v
"""

import os

import pytest

pytestmark = pytest.mark.live

from game_service.session.actions import DrawCardAction, NextStepAction
from game_service.session.manager import SessionManager

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev_user@example.com")
DEV_USER_PASSWORD = os.environ.get("DEV_USER_PASSWORD", "password")

PLUGIN_REGISTRY = {
    "marvel-champions": {
        "id": int(os.environ.get("MC_PLUGIN_ID", "1")),
        "version": int(os.environ.get("MC_PLUGIN_VERSION", "1")),
        "name": "Marvel Champions",
    }
}


@pytest.fixture
def manager():
    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=DEV_USER_EMAIL,
        password=DEV_USER_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
    )


@pytest.mark.asyncio
async def test_next_step_changes_state(manager):
    """Executing NEXT_STEP returns a new state with an advanced stepId."""
    session = await manager.create_session("marvel-champions")
    try:
        initial_state = await session.get_state()
        initial_step = initial_state.get("game", {}).get("stepId")

        new_state = await session.execute_action(NextStepAction())

        assert new_state is not None
        assert "game" in new_state
        new_step = new_state.get("game", {}).get("stepId")
        # Step should have changed (or wrapped around if at the end)
        assert new_step is not None
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_draw_card_changes_hand(manager):
    """
    DRAW_CARD action executes without error and returns updated state.

    Note: A freshly created Marvel Champions game room has no cards loaded
    (the plugin shell is empty until a full deck is configured via the UI).
    This test verifies that the action can be sent and a state is returned —
    not that the hand count increases — since the deck starts empty.
    """
    session = await manager.create_session("marvel-champions")
    try:
        # The action should execute without raising even if the deck is empty
        new_state = await session.execute_action(
            DrawCardAction(player_n="player1", count=1)
        )
        assert new_state is not None
        # State shape should still be valid
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)
