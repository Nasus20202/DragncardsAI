"""Router: room control endpoints (reset, seat, spectator, alert, replay, player-count)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager

logger = logging.getLogger(__name__)
from game_service.api.models import (
    ResetGameRequest,
    ResetGameResponse,
    SendAlertRequest,
    SetPlayerCountRequest,
    SetPlayerCountResponse,
    SetSeatRequest,
    SetSpectatorRequest,
)
from game_service.session.manager import SessionManager

router = APIRouter(tags=["room-control"])


@router.post(
    "/games/{session_id}/reset",
    response_model=ResetGameResponse,
    summary="Reset the game state",
    operation_id="reset_game",
)
async def reset_game(
    session_id: str,
    body: ResetGameRequest,
    manager: SessionManager = Depends(get_manager),
):
    """
    Reset the DragnCards game. Pass `reload_plugin: true` to reload the
    plugin after reset. Pass `save: true` to save a replay first.
    """
    logger.info(
        "reset_game: session_id=%s save=%s reload_plugin=%s",
        session_id,
        body.save,
        body.reload_plugin,
    )
    session = await manager.get_session(session_id)
    new_state = await session.reset_game(
        save=body.save, reload_plugin=body.reload_plugin
    )
    logger.info("reset_game: session_id=%s -> success", session_id)
    return ResetGameResponse(session_id=session_id, state=new_state)


@router.post(
    "/games/{session_id}/seat",
    status_code=204,
    summary="Assign a user to a player seat",
    operation_id="set_seat",
)
async def set_seat(
    session_id: str,
    body: SetSeatRequest,
    manager: SessionManager = Depends(get_manager),
):
    """Assign a DragnCards user to a specific player seat (0-indexed)."""
    logger.info(
        "set_seat: session_id=%s player_index=%s user_id=%s",
        session_id,
        body.player_index,
        body.user_id,
    )
    session = await manager.get_session(session_id)
    await session.set_seat(player_index=body.player_index, user_id=body.user_id)


@router.post(
    "/games/{session_id}/spectator",
    status_code=204,
    summary="Toggle spectator mode for a user",
    operation_id="set_spectator",
)
async def set_spectator(
    session_id: str,
    body: SetSpectatorRequest,
    manager: SessionManager = Depends(get_manager),
):
    """Enable or disable omniscient spectator mode for the given user."""
    logger.info(
        "set_spectator: session_id=%s user_id=%s spectating=%s",
        session_id,
        body.user_id,
        body.spectating,
    )
    session = await manager.get_session(session_id)
    await session.set_spectator(user_id=body.user_id, spectating=body.spectating)


@router.post(
    "/games/{session_id}/alert",
    status_code=204,
    summary="Broadcast an alert to the room",
    operation_id="send_alert",
)
async def send_alert(
    session_id: str,
    body: SendAlertRequest,
    manager: SessionManager = Depends(get_manager),
):
    """Broadcast a text alert message to all participants in the room."""
    logger.info("send_alert: session_id=%s message=%r", session_id, body.message)
    session = await manager.get_session(session_id)
    await session.send_alert(body.message)


@router.post(
    "/games/{session_id}/replay",
    status_code=204,
    summary="Save the current replay",
    operation_id="save_replay",
)
async def save_replay(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    """Manually trigger a replay save for the current game session."""
    logger.info("save_replay: session_id=%s", session_id)
    session = await manager.get_session(session_id)
    await session.save_replay()


@router.post(
    "/games/{session_id}/player-count",
    response_model=SetPlayerCountResponse,
    summary="Set the number of players",
    operation_id="set_player_count",
)
async def set_player_count(
    session_id: str,
    body: SetPlayerCountRequest,
    manager: SessionManager = Depends(get_manager),
):
    """
    Set the number of active players for the game room.

    Pass `layout_id` if the plugin uses per-player-count layouts (consult
    the plugin's playerCountMenu configuration for valid values).
    Returns the resulting game state.
    """
    logger.info(
        "set_player_count: session_id=%s num_players=%s layout_id=%r",
        session_id,
        body.num_players,
        body.layout_id,
    )
    session = await manager.get_session(session_id)
    new_state = await session.set_player_count(
        num_players=body.num_players, layout_id=body.layout_id
    )
    logger.info("set_player_count: session_id=%s -> success", session_id)
    return SetPlayerCountResponse(session_id=session_id, state=new_state)
