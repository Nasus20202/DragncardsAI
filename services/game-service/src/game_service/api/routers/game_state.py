"""Router: game state and snapshot endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
from game_service.api.models import GameStateSnapshot, GameStateResponse
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-state"])


@router.get(
    "/games/{session_id}/state",
    response_model=GameStateResponse,
    summary="Get current game state",
    operation_id="get_game_state",
)
async def get_game_state(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("get_game_state: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        state = await session.get_state()
    logger.debug(
        "get_game_state: session_id=%s -> state keys=%s",
        session_id,
        list(state.keys()) if isinstance(state, dict) else type(state).__name__,
    )
    return GameStateResponse(session_id=session_id, state=state)


@router.get(
    "/games/{session_id}/snapshot",
    response_model=GameStateSnapshot,
    summary="Export a reusable game state snapshot",
    operation_id="export_game_state_snapshot",
)
async def export_game_state_snapshot(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("export_game_state_snapshot: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        return await session.export_state()


@router.put(
    "/games/{session_id}/snapshot",
    response_model=GameStateResponse,
    summary="Load a game state snapshot",
    operation_id="load_game_state_snapshot",
)
async def load_game_state_snapshot(
    session_id: str,
    snapshot: GameStateSnapshot,
    manager: SessionManager = Depends(get_manager),
):
    logger.info(
        "load_game_state_snapshot: session_id=%s plugin_name=%r schema_version=%s",
        session_id,
        snapshot.plugin_name,
        snapshot.schema_version,
    )
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        state = await session.load_state(snapshot)
    return GameStateResponse(session_id=session_id, state=state)
