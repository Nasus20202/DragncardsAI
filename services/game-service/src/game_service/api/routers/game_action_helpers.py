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
    return ExecuteActionResponse(session_id=session_id, success=True)


@router.post(
    "/games/{session_id}/actions/prev_step",
    response_model=ExecuteActionResponse,
    operation_id="prev_step",
)
async def prev_step(session_id: str, manager: SessionManager = Depends(get_manager)):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(PrevStepAction())
    return ExecuteActionResponse(session_id=session_id, success=True)


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
    return ExecuteActionResponse(session_id=session_id, success=True)


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
    return ExecuteActionResponse(session_id=session_id, success=True)


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
    return ExecuteActionResponse(session_id=session_id, success=True)


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
    return ExecuteActionResponse(session_id=session_id, success=True)


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
    return ExecuteActionResponse(session_id=session_id, success=True)


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
    return ExecuteActionResponse(session_id=session_id, success=True)


@router.post(
    "/games/{session_id}/actions/raw",
    response_model=ExecuteActionResponse,
    operation_id="raw",
)
async def raw_action(
    session_id: str, action: RawAction, manager: SessionManager = Depends(get_manager)
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)
    return ExecuteActionResponse(session_id=session_id, success=True)
