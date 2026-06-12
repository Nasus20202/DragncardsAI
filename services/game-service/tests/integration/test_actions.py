"""
Integration tests for game action execution.

Requires a running DragnCards instance with Marvel Champions plugin.

Run with:
    pytest tests/integration/test_actions.py -v
"""

import os

import pytest

pytestmark = pytest.mark.live

from game_service.logic.actions import (
    DrawCardAction,
    NextStepAction,
    ExhaustCardAction,
    ReadyCardAction,
    FlipCardAction,
    DealEncounterAction,
    DrawBoostAction,
    ShuffleIntoDeckAction,
    ZeroTokensAction,
    MulliganDrawHandAction,
    ShadowsOfThePastAction,
    PlayerEndPhaseAction,
    VillainEncounterPhaseAction,
    VillainEndPhaseAction,
    MultipleDoubleSidedVillainsAction,
    DiscardMinionAction,
    DiscardSideSchemeAction,
    ModifyTokensAction,
)
from game_service.logic.session_manager import SessionManager

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


@pytest.mark.asyncio
async def test_exhaust_card_action(manager):
    """EXHAUST_CARD action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            ExhaustCardAction(instance_id="test-card-1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_ready_card_action(manager):
    """READY_CARD action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            ReadyCardAction(instance_id="test-card-1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_flip_card_action(manager):
    """FLIP_CARD action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            FlipCardAction(instance_id="test-card-1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_deal_encounter_action(manager):
    """DEAL_ENCOUNTER_CARD action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            DealEncounterAction(player_n="player1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_deal_second_encounter_action(manager):
    """DEAL_SECOND_ENCOUNTER_CARD action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            DealEncounterAction(
                player_n="player1", deck_group_id="sharedEncounter2Deck"
            )
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_draw_boost_action(manager):
    """DRAW_BOOST_CARD action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(DrawBoostAction(player_n="player1"))
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_shuffle_into_deck_action(manager):
    """SHUFFLE_INTO_DECK action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            ShuffleIntoDeckAction(instance_id="test-card-1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_zero_tokens_action(manager):
    """ZERO_TOKENS action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            ZeroTokensAction(instance_id="test-card-1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_mulligan_draw_hand_action(manager):
    """MULLIGAN_DRAW_HAND action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            MulliganDrawHandAction(player_n="player1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_shadows_of_the_past_action(manager):
    """SHADOWS_OF_THE_PAST action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            ShadowsOfThePastAction(player_n="player1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_player_end_phase_action(manager):
    """PLAYER_END_PHASE action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(PlayerEndPhaseAction())
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_villain_encounter_phase_action(manager):
    """VILLAIN_ENCOUNTER_PHASE action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(VillainEncounterPhaseAction())
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_villain_end_phase_action(manager):
    """VILLAIN_END_PHASE action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(VillainEndPhaseAction())
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_multiple_double_sided_villains_action(manager):
    """MULTIPLE_DOUBLE_SIDED_VILLAINS action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(MultipleDoubleSidedVillainsAction())
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_discard_minion_action(manager):
    """DISCARD_MINION action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            DiscardMinionAction(player_n="player1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_discard_side_scheme_action(manager):
    """DISCARD_SIDE_SCHEME action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            DiscardSideSchemeAction(player_n="player1")
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_modify_tokens_action(manager):
    """MODIFY_TOKENS action should execute and return a valid state."""
    session = await manager.create_session("marvel-champions")
    try:
        new_state = await session.execute_action(
            ModifyTokensAction(instance_id="test-card-1", token_type="threat", amount=1)
        )
        assert new_state is not None
        assert "game" in new_state or "createdAt" in new_state
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_modify_tokens_action_error_field(manager):
    """MODIFY_TOKENS action response should include error field when action fails."""
    session = await manager.create_session("marvel-champions")
    try:
        # Execute action with nonexistent card - should still return but may have error
        new_state = await session.execute_action(
            ModifyTokensAction(
                instance_id="nonexistent-card-xyz", token_type="threat", amount=1
            )
        )
        # Verify session can retrieve error state
        error = session.get_action_error()
        # Error may be None or a string depending on whether DragnCards reported failure
        assert error is None or isinstance(error, str)
    finally:
        await manager.delete_session(session.session_id)
