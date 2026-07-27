"""Explicit, per-action HTTP endpoints that wrap the generic execute_action path.

These handlers are intentionally written out (no dynamic generation) so MCP
tooling generated from the OpenAPI schema exposes one tool per action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import ExecuteActionResponse
from game_service.logic.actions import (
    NextStepAction,
    PrevStepAction,
    DrawCardAction,
    MoveCardAction,
    SetCardPropertyAction,
    SetPlayerCountAction,
    LoadCardsAction,
    UnloadCardsAction,
    RawAction,
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

router = APIRouter(tags=["game-action-helpers"])


@router.post(
    "/games/{session_id}/actions/next_step",
    response_model=ExecuteActionResponse,
    summary="Advance to the next step in the round sequence (after player turns, before villain phase, etc.)",
    operation_id="next_step",
)
async def next_step(
    session_id: SessionIdentifier, manager: SessionManager = Depends(get_manager)
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(NextStepAction())
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/prev_step",
    response_model=ExecuteActionResponse,
    summary="Go back to the previous step (use to undo mistakes or redo encounter resolution)",
    operation_id="prev_step",
)
async def prev_step(
    session_id: SessionIdentifier, manager: SessionManager = Depends(get_manager)
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(PrevStepAction())
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/draw_card",
    response_model=ExecuteActionResponse,
    summary="Draw exact number of cards from player deck (use when a card effect says 'draw X cards', NOT for drawing up to hand limit)",
    operation_id="draw_card",
)
async def draw_card(
    session_id: SessionIdentifier,
    action: DrawCardAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/move_card",
    response_model=ExecuteActionResponse,
    summary="Move a card to a different zone/group (use to play cards, thwart schemes, or relocate cards)",
    operation_id="move_card",
)
async def move_card(
    session_id: SessionIdentifier,
    action: MoveCardAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/set_card_property",
    response_model=ExecuteActionResponse,
    summary="Set arbitrary card property (WARNING: use flip_card for hero/alter-ego changes, exhaust_card for exhaustion, ready_card for readying - this is a low-level action)",
    operation_id="set_card_property",
)
async def set_card_property(
    session_id: SessionIdentifier,
    action: SetCardPropertyAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/set_player_count",
    response_model=ExecuteActionResponse,
    summary="Set number of active players and optionally the table layout (use during game setup)",
    operation_id="set_player_count_action",
)
async def set_player_count(
    session_id: SessionIdentifier,
    action: SetPlayerCountAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/load_cards",
    response_model=ExecuteActionResponse,
    summary="Load specific cards into game zones by database ID (use during setup or to add specific cards mid-game)",
    operation_id="load_cards",
)
async def load_cards(
    session_id: SessionIdentifier,
    action: LoadCardsAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/unload_cards",
    response_model=ExecuteActionResponse,
    summary="Remove all cards for a player or all shared encounter cards (use for cleanup or reset)",
    operation_id="unload_cards",
)
async def unload_cards(
    session_id: SessionIdentifier,
    action: UnloadCardsAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/raw",
    response_model=ExecuteActionResponse,
    summary="DEBUG ONLY: Execute raw DragnLang action list",
    operation_id="raw_action",
)
async def raw_action(
    session_id: SessionIdentifier,
    action: RawAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/exhaust_card",
    response_model=ExecuteActionResponse,
    summary="Exhaust (turn sideways) a card to use its abilities, attack, thwart, or use basic powers",
    operation_id="exhaust_card",
)
async def exhaust_card(
    session_id: SessionIdentifier,
    action: ExhaustCardAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/ready_card",
    response_model=ExecuteActionResponse,
    summary="Ready (remove sideways) an exhausted card (use during refresh step or manually readied cards)",
    operation_id="ready_card",
)
async def ready_card(
    session_id: SessionIdentifier,
    action: ReadyCardAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/flip_card",
    response_model=ExecuteActionResponse,
    summary="Flip card to next side (A→B→C→A) - use for hero/alter-ego form changes or to cycle card sides",
    operation_id="flip_card",
)
async def flip_card(
    session_id: SessionIdentifier,
    action: FlipCardAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/deal_encounter",
    response_model=ExecuteActionResponse,
    summary="Deal an encounter card facedown to a player (use during villain phase Step 3)",
    operation_id="deal_encounter",
)
async def deal_encounter(
    session_id: SessionIdentifier,
    action: DealEncounterAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/draw_boost",
    response_model=ExecuteActionResponse,
    summary="Draw a facedown boost card for villain activation (use during villain phase Step 2 when villain attacks or schemes)",
    operation_id="draw_boost",
)
async def draw_boost(
    session_id: SessionIdentifier,
    action: DrawBoostAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/shuffle_into_deck",
    response_model=ExecuteActionResponse,
    summary="Return a card to its owner's deck and shuffle (use after playing events or cleanup effects)",
    operation_id="shuffle_into_deck",
)
async def shuffle_into_deck(
    session_id: SessionIdentifier,
    action: ShuffleIntoDeckAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/zero_tokens",
    response_model=ExecuteActionResponse,
    summary="Remove all tokens from a card (damage, threat, status) - use when clearing damage or resetting card state",
    operation_id="zero_tokens",
)
async def zero_tokens(
    session_id: SessionIdentifier,
    action: ZeroTokensAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/mulligan_draw_hand",
    response_model=ExecuteActionResponse,
    summary="Draw one player up to their hand size - never discards, and does nothing if the hand is already full; use for the setup mulligan after discarding the unwanted cards yourself, or to refill one player's hand (preferred over draw_card, which draws an exact count)",
    operation_id="mulligan_draw_hand",
)
async def mulligan_draw_hand(
    session_id: SessionIdentifier,
    action: MulliganDrawHandAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/shadows_of_the_past",
    response_model=ExecuteActionResponse,
    summary="Resolve a player's nemesis encounter: move nemesis minion and side scheme into play, add acceleration to main scheme",
    operation_id="shadows_of_the_past",
)
async def shadows_of_the_past(
    session_id: SessionIdentifier,
    action: ShadowsOfThePastAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/player_end_phase",
    response_model=ExecuteActionResponse,
    summary="End the player phase: players discard to hand limit and draw up to hand size, then ready all cards; begins villain phase",
    operation_id="player_end_phase",
)
async def player_end_phase(
    session_id: SessionIdentifier,
    action: PlayerEndPhaseAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/villain_encounter_phase",
    response_model=ExecuteActionResponse,
    summary="Execute villain encounter phase - villain deals one encounter card to each player (Step 3 of villain phase)",
    operation_id="villain_encounter_phase",
)
async def villain_encounter_phase(
    session_id: SessionIdentifier,
    action: VillainEncounterPhaseAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/villain_end_phase",
    response_model=ExecuteActionResponse,
    summary="End villain phase and begin next player phase - pass first player token clockwise",
    operation_id="villain_end_phase",
)
async def villain_end_phase(
    session_id: SessionIdentifier,
    action: VillainEndPhaseAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/multiple_double_sided_villains",
    response_model=ExecuteActionResponse,
    summary="Handle setup for scenarios with multiple double-sided villains - use during scenario setup",
    operation_id="multiple_double_sided_villains",
)
async def multiple_double_sided_villains(
    session_id: SessionIdentifier,
    action: MultipleDoubleSidedVillainsAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/discard_minion",
    response_model=ExecuteActionResponse,
    summary="Discard cards from player deck until a minion is found - use when searching for minion cards",
    operation_id="discard_minion",
)
async def discard_minion(
    session_id: SessionIdentifier,
    action: DiscardMinionAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/discard_side_scheme",
    response_model=ExecuteActionResponse,
    summary="Discard cards from player deck until a side scheme is found - use when searching for side scheme cards",
    operation_id="discard_side_scheme",
)
async def discard_side_scheme(
    session_id: SessionIdentifier,
    action: DiscardSideSchemeAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/modify_tokens",
    response_model=ExecuteActionResponse,
    summary="Add or remove damage/threat/status tokens on a card - use for all damage, threat, or status operations",
    operation_id="modify_tokens",
)
async def modify_tokens(
    session_id: SessionIdentifier,
    action: ModifyTokensAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )
