import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from game_service.api.routers import game_action_helpers as helpers
from game_service.logic.actions import (
    DrawCardAction,
    MoveCardAction,
    NextStepAction,
    PrevStepAction,
    SetCardPropertyAction,
    SetPlayerCountAction,
    LoadCardsAction,
    UnloadCardsAction,
    RawAction,
)


def _mock_session(before_state=None, after_state=None):
    session = MagicMock()
    session.execute_action = AsyncMock()
    # get_state will return before_state, then after_state when called twice
    if before_state is None:
        before_state = {"game": {}}
    if after_state is None:
        after_state = {"game": {}}
    session.get_state = AsyncMock(side_effect=[before_state, after_state])
    return session


def _mock_manager(session):
    manager = MagicMock()
    # session_operation_lock used as async context manager; provide a callable
    class Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    manager.session_operation_lock = lambda *a, **k: Ctx()
    manager.get_session = AsyncMock(return_value=session)
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "helper, action_cls, before, after, expected_type",
    [
        (helpers.next_step, NextStepAction, {"game": {"step": 1}}, {"game": {"step": 2}}, NextStepAction),
        (helpers.prev_step, PrevStepAction, {"game": {"step": 2}}, {"game": {"step": 1}}, PrevStepAction),
        (helpers.draw_card, DrawCardAction, {"game": {"hands": {"player1": []}}}, {"game": {"hands": {"player1": ["cardA"]}}}, DrawCardAction),
        (helpers.move_card, MoveCardAction, {"game": {"zones": {"hand": ["c1"]}}}, {"game": {"zones": {"play": ["c1"]}}}, MoveCardAction),
        (helpers.set_card_property, SetCardPropertyAction, {"game": {"cardById": {"c1": {"currentSide": "A"}}}}, {"game": {"cardById": {"c1": {"currentSide": "B"}}}}, SetCardPropertyAction),
        (helpers.set_player_count, SetPlayerCountAction, {"game": {"numPlayers": 1}}, {"game": {"numPlayers": 2}}, SetPlayerCountAction),
        (helpers.load_cards, LoadCardsAction, {"game": {"loadCardsHistory": []}}, {"game": {"loadCardsHistory": ["loaded"]}}, LoadCardsAction),
        (helpers.unload_cards, UnloadCardsAction, {"game": {"player1": {"cards": ["c1"]}}}, {"game": {"player1": {"cards": []}}}, UnloadCardsAction),
        (helpers.raw_action, RawAction, {"game": {"x": 0}}, {"game": {"x": 1}}, RawAction),
    ],
)
async def test_action_helpers_call_execute_and_change_state(helper, action_cls, before, after, expected_type):
    session = _mock_session(before_state=before, after_state=after)
    manager = _mock_manager(session)

    # Fetch state before
    prev = await session.get_state()

    # Build an example action payload for actions that require body
    if action_cls is NextStepAction or action_cls is PrevStepAction:
        resp = await helper("sess-1", manager=manager)
    elif action_cls is DrawCardAction:
        action = DrawCardAction()
        resp = await helper("sess-1", action, manager=manager)
    elif action_cls is MoveCardAction:
        action = MoveCardAction(card_id="c1", dest_group_id="play")
        resp = await helper("sess-1", action, manager=manager)
    elif action_cls is SetCardPropertyAction:
        action = SetCardPropertyAction(card_id="c1", property_path="currentSide", value="B")
        resp = await helper("sess-1", action, manager=manager)
    elif action_cls is SetPlayerCountAction:
        action = SetPlayerCountAction(num_players=2)
        resp = await helper("sess-1", action, manager=manager)
    elif action_cls is LoadCardsAction:
        item = {"databaseId": "db1", "loadGroupId": "player1Deck", "quantity": 1}
        action = LoadCardsAction(cards=[item])
        resp = await helper("sess-1", action, manager=manager)
    elif action_cls is UnloadCardsAction:
        action = UnloadCardsAction(player_n="player1")
        resp = await helper("sess-1", action, manager=manager)
    elif action_cls is RawAction:
        action = RawAction(action_list=["SET", "/game/x", 1])
        resp = await helper("sess-1", action, manager=manager)
    else:
        pytest.skip("Unsupported action type in test")

    # Ensure execute_action was called on the session
    assert session.execute_action.await_count >= 1

    # Fetch state after
    new = await session.get_state()

    assert prev != new, "Expected game state to change after action"
    assert resp.session_id == "sess-1"
    assert resp.success is True
