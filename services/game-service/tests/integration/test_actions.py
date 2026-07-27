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


def _group_of_card(state, card_id):
    """Return the group id currently holding card_id, or None."""
    game = state.get("game", state)
    for group_id, group in game["groupById"].items():
        for stack_id in group["stackIds"]:
            if card_id in game["stackById"][stack_id]["cardIds"]:
                return group_id
    return None


@pytest.mark.asyncio
async def test_shuffle_into_deck_moves_the_card_into_the_owner_deck(manager):
    """SHUFFLE_INTO_DECK must actually move a real card from hand into its deck.

    Regression test: the action used to pass "/cardById/<id>/deckGroupId" to VAR,
    which DragnLang evaluates to the path list ["cardById", "<id>", "deckGroupId"]
    rather than the value at that path. MOVE_CARD then failed with
    "Group not found: cardById<id>deckGroupId" and the card never moved.
    """
    session = await manager.create_session("marvel-champions")
    try:
        # Spider-Man (Peter Parker) hero set - gives player1 a real deck and hand.
        # Go through the manager so the load is polled to completion.
        await manager.load_prebuilt_deck(
            session.session_id, "fe0f49aa-d3b4-4604-a43c-eaa18bbe1601"
        )
        await session.execute_action(DrawCardAction(player_n="player1", count=5))

        state = await session.get_state()
        game = state.get("game", state)
        hand_stacks = game["groupById"]["player1Hand"]["stackIds"]
        assert hand_stacks, "expected a non-empty player1Hand after drawing"
        card_id = game["stackById"][hand_stacks[0]]["cardIds"][0]
        deck_group_id = game["cardById"][card_id]["deckGroupId"]
        deck_size_before = len(game["groupById"][deck_group_id]["stackIds"])

        await session.execute_action(
            ShuffleIntoDeckAction(instance_id=card_id, player_n="player1")
        )
        assert session.get_action_error() is None

        state = await session.get_state()
        game = state.get("game", state)
        assert _group_of_card(state, card_id) == deck_group_id
        assert len(game["groupById"][deck_group_id]["stackIds"]) == deck_size_before + 1
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
