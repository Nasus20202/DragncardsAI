"""Explicit, per-action HTTP endpoints that wrap the generic execute_action path.

These handlers are intentionally written out (no dynamic generation) so MCP
tooling generated from the OpenAPI schema exposes one tool per action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
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
    operation_id="next_step",
)
async def next_step(session_id: str, manager: SessionManager = Depends(get_manager)):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(NextStepAction())
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/prev_step",
    response_model=ExecuteActionResponse,
    operation_id="prev_step",
)
async def prev_step(session_id: str, manager: SessionManager = Depends(get_manager)):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(PrevStepAction())
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )


@router.post(
    "/games/{session_id}/actions/draw_card",
    response_model=ExecuteActionResponse,
    operation_id="draw_card",
)
async def draw_card(
    session_id: str,
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
    operation_id="move_card",
)
async def move_card(
    session_id: str,
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
    operation_id="set_card_property",
)
async def set_card_property(
    session_id: str,
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
    # Avoid exposing the exact room-control tool name to MCP discovery;
    # keep the action type name as-is but give the OpenAPI operation a
    # distinct id so the MCP tool name differs.
    operation_id="set_player_count_action",
)
async def set_player_count(
    session_id: str,
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
    operation_id="load_cards",
)
async def load_cards(
    session_id: str,
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
    operation_id="unload_cards",
)
async def unload_cards(
    session_id: str,
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
    session_id: str, action: RawAction, manager: SessionManager = Depends(get_manager)
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
    operation_id="exhaust_card",
)
async def exhaust_card(
    session_id: str,
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
    operation_id="ready_card",
)
async def ready_card(
    session_id: str,
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
    operation_id="flip_card",
)
async def flip_card(
    session_id: str,
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
    operation_id="deal_encounter",
)
async def deal_encounter(
    session_id: str,
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
    operation_id="draw_boost",
)
async def draw_boost(
    session_id: str,
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
    operation_id="shuffle_into_deck",
)
async def shuffle_into_deck(
    session_id: str,
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
    operation_id="zero_tokens",
)
async def zero_tokens(
    session_id: str,
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
    operation_id="mulligan_draw_hand",
)
async def mulligan_draw_hand(
    session_id: str,
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
    operation_id="shadows_of_the_past",
)
async def shadows_of_the_past(
    session_id: str,
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
    operation_id="player_end_phase",
)
async def player_end_phase(
    session_id: str,
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
    operation_id="villain_encounter_phase",
)
async def villain_encounter_phase(
    session_id: str,
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
    operation_id="villain_end_phase",
)
async def villain_end_phase(
    session_id: str,
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
    operation_id="multiple_double_sided_villains",
)
async def multiple_double_sided_villains(
    session_id: str,
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
    operation_id="discard_minion",
)
async def discard_minion(
    session_id: str,
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
    operation_id="discard_side_scheme",
)
async def discard_side_scheme(
    session_id: str,
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
    operation_id="modify_tokens",
)
async def modify_tokens(
    session_id: str,
    action: ModifyTokensAction,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(
        session_id=session_id, success=True, error=session.get_action_error()
    )
