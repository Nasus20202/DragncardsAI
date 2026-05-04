"""Router: game session lifecycle endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from game_service.api.deps import get_manager
from game_service.api.models import (
    AttachGameRequest,
    AttachGameResponse,
    CreateGameRequest,
    CreateGameResponse,
    DeleteGameResponse,
    ListGamesResponse,
    SessionMetadata,
)
from game_service.logic.session_manager import SessionError, SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"])


@router.post(
    "/games",
    response_model=CreateGameResponse,
    status_code=201,
    summary="Create a new game session",
    operation_id="create_game",
)
async def create_game(
    body: CreateGameRequest,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("create_game: plugin_name=%r", body.plugin_name)
    try:
        session = await manager.create_session(body.plugin_name)
    except SessionError as exc:
        logger.warning("create_game failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("create_game: session_id=%s created", session.session_id)
    return CreateGameResponse(session=SessionMetadata(**session.to_metadata()))


@router.post(
    "/games/attach",
    response_model=AttachGameResponse,
    status_code=201,
    summary="Attach to an existing game room",
    operation_id="attach_game",
)
async def attach_game(
    body: AttachGameRequest,
    manager: SessionManager = Depends(get_manager),
):
    logger.info(
        "attach_game: plugin_name=%r room_slug=%r", body.plugin_name, body.room_slug
    )
    try:
        session = await manager.attach_session(body.plugin_name, body.room_slug)
    except SessionError as exc:
        logger.warning("attach_game failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "attach_game: session_id=%s attached to room %s",
        session.session_id,
        body.room_slug,
    )
    return AttachGameResponse(session=SessionMetadata(**session.to_metadata()))


@router.get(
    "/games",
    response_model=ListGamesResponse,
    summary="List active game sessions",
    operation_id="list_games",
)
async def list_games(manager: SessionManager = Depends(get_manager)):
    sessions = [SessionMetadata(**m) for m in manager.list_sessions()]
    logger.debug("list_games: %d active session(s)", len(sessions))
    return ListGamesResponse(sessions=sessions)


@router.delete(
    "/games/{session_id}",
    response_model=DeleteGameResponse,
    summary="Delete a game session",
    operation_id="delete_game",
)
async def delete_game(
    session_id: str,
    close_room: bool = False,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("delete_game: session_id=%s close_room=%s", session_id, close_room)
    if close_room:
        session = await manager.get_session(session_id)
        await session.close_room()
    else:
        await manager.delete_session(session_id)
    logger.info("delete_game: session_id=%s -> deleted", session_id)
    return DeleteGameResponse(session_id=session_id)
