"""Router: game state and snapshot endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.enums import SeatId
from game_service.api.models import GameStateSnapshot, GameStateResponse
from game_service.logic.platform import DRAGNCARDS_PLATFORM, MARVEL_LCG_PLATFORM
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-state"])


def _normalise_session_state(
    session: Any, state: Any, *, player_n: str | None = None
) -> Any:
    """Delegate state projection to the session's platform driver."""
    normalised = session.normalise_state(state, player_n=player_n)
    if not isinstance(normalised, (dict, list, BaseModel)):
        raise TypeError("platform driver returned an invalid normalized state")
    return normalised


def _session_capabilities(session: Any) -> tuple[str, str]:
    platform = getattr(session, "platform", DRAGNCARDS_PLATFORM)
    if platform not in {DRAGNCARDS_PLATFORM, MARVEL_LCG_PLATFORM}:
        platform = DRAGNCARDS_PLATFORM
    move_surface = getattr(session.driver, "move_surface", "typed_actions")
    if move_surface not in {"typed_actions", "enumerated_options"}:
        move_surface = "typed_actions"
    return platform, move_surface


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
    response: Response,
    manager: SessionManager = Depends(get_manager),
    player_n: SeatId | None = Query(
        default=None,
        description=(
            "Seat whose engine-permitted private cards are visible. Omit for the "
            "spectator/public projection; this selector is not caller authorization."
        ),
    ),
):
    response.headers["Cache-Control"] = "private, no-store"
    logger.info("get_game_state: session_id=%s player_n=%s", session_id, player_n)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        state = await session.get_state(player_n=player_n)

    logger.debug(
        "get_game_state: session_id=%s -> state keys=%s",
        session_id,
        list(state.keys()) if isinstance(state, dict) else type(state).__name__,
    )

    state = _normalise_session_state(session, state, player_n=player_n)

    platform, move_surface = _session_capabilities(session)
    return GameStateResponse(
        session_id=session.session_id,
        platform=platform,
        move_surface=move_surface,
        state=state,
    )


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

    platform, move_surface = _session_capabilities(session)
    return GameStateResponse(
        session_id=session.session_id,
        platform=platform,
        move_surface=move_surface,
        state=state,
    )
