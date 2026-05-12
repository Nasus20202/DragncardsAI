"""Router: room control and room event observation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
from game_service.api.models import (
    AlertsResponse,
    GuiUpdateResponse,
    ResetGameRequest,
    ResetGameResponse,
    SendAlertRequest,
    SetPlayerCountRequest,
    SetPlayerCountResponse,
    SetSeatRequest,
    SetSpectatorRequest,
)
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-room"])


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
    logger.info(
        "reset_game: session_id=%s save=%s reload_plugin=%s",
        session_id,
        body.save,
        body.reload_plugin,
    )
    async with manager.session_operation_lock(session_id):
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
    logger.info(
        "set_seat: session_id=%s player_index=%s user_id=%s",
        session_id,
        body.player_index,
        body.user_id,
    )
    async with manager.session_operation_lock(session_id):
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
    logger.info(
        "set_spectator: session_id=%s user_id=%s spectating=%s",
        session_id,
        body.user_id,
        body.spectating,
    )
    async with manager.session_operation_lock(session_id):
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
    logger.info("send_alert: session_id=%s message=%r", session_id, body.message)
    async with manager.session_operation_lock(session_id):
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
    logger.info("save_replay: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
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
    logger.info(
        "set_player_count: session_id=%s num_players=%s layout_id=%r",
        session_id,
        body.num_players,
        body.layout_id,
    )
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        new_state = await session.set_player_count(
            num_players=body.num_players, layout_id=body.layout_id
        )
    logger.info("set_player_count: session_id=%s -> success", session_id)
    return SetPlayerCountResponse(session_id=session_id, state=new_state)


@router.get(
    "/games/{session_id}/alerts",
    response_model=AlertsResponse,
    summary="Get buffered room alerts",
    operation_id="get_alerts",
)
async def get_alerts(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    session = await manager.get_session(session_id)
    return AlertsResponse(session_id=session_id, alerts=session.get_alerts())


@router.get(
    "/games/{session_id}/gui-update",
    response_model=GuiUpdateResponse,
    summary="Get latest GUI update hints",
    operation_id="get_gui_update",
)
async def get_gui_update(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    session = await manager.get_session(session_id)
    return GuiUpdateResponse(session_id=session_id, updates=session.get_gui_updates())
