"""Router: game state and snapshot endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import GameStateSnapshot, GameStateResponse
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-state"])


def _normalise_session_state(session: Any, state: Any) -> Any:
    """Delegate state projection to the session's platform driver."""
    normalised = session.normalise_state(state)
    if not isinstance(normalised, (dict, list, BaseModel)):
        raise TypeError("platform driver returned an invalid normalized state")
    return normalised


@router.get(
    "/games/{session_id}/state/raw",
    summary="DEBUG ONLY: Get raw game state without simplification",
    operation_id="get_raw_game_state_games",
)
async def get_raw_game_state(
    session_id: SessionIdentifier,
    manager: SessionManager = Depends(get_manager),
):
    """Get the raw game state without any simplification or transformation."""
    logger.info("get_raw_game_state: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        return await session.get_state()


@router.get(
    "/games/{session_id}/state",
    response_model=GameStateResponse,
    summary="Get current game state",
    operation_id="get_game_state",
)
async def get_game_state(
    session_id: SessionIdentifier,
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

    state = _normalise_session_state(session, state)

    return GameStateResponse(session_id=session_id, state=state)


@router.get(
    "/games/{session_id}/snapshot",
    response_model=GameStateSnapshot,
    summary="Export a reusable game state snapshot",
    operation_id="export_game_state_snapshot",
)
async def export_game_state_snapshot(
    session_id: SessionIdentifier,
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
    session_id: SessionIdentifier,
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

    state = _normalise_session_state(session, state)

    return GameStateResponse(session_id=session_id, state=state)
