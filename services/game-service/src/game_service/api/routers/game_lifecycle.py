"""Router: game session lifecycle endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import (
    AttachGameRequest,
    AttachGameResponse,
    CreateGameRequest,
    CreateGameResponse,
    DeleteGameResponse,
    ListGamesResponse,
    LookupSessionBySlugResponse,
    SessionMetadata,
)
from game_service.logic.exceptions import SessionNotFoundError
from game_service.logic.session_manager import SessionError, SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-lifecycle"])


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
    logger.info(
        "create_game: plugin_name=%r ephemeral=%s", body.plugin_name, body.ephemeral
    )
    try:
        session = await manager.create_session(
            body.plugin_name, ephemeral=body.ephemeral
        )
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
    sessions = [SessionMetadata(**m) for m in await manager.list_sessions()]
    logger.debug("list_games: %d active session(s)", len(sessions))
    return ListGamesResponse(sessions=sessions)


@router.get(
    "/games/by-slug/{room_slug}",
    response_model=LookupSessionBySlugResponse,
    summary="Look up a session by its room slug",
    description=(
        "Resolve a human-readable DragnCards room slug (e.g. `lively-fog-1234`) to "
        "its session metadata, including the canonical UUID `session_id`. Read-only: "
        "it never creates, modifies, or destroys a session. You do NOT need this "
        "before acting on a session — every session endpoint accepts a room slug "
        "directly in the `session_id` position. Use it when you want the session's "
        "full metadata, or its UUID `session_id` to disambiguate a slug shared by "
        "more than one session."
    ),
    operation_id="lookup_session_by_slug",
)
async def lookup_session_by_slug(
    room_slug: str,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("lookup_session_by_slug: room_slug=%r", room_slug)
    try:
        metadata = await manager.lookup_session_by_slug(room_slug)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LookupSessionBySlugResponse(session=SessionMetadata(**metadata))


@router.delete(
    "/games/{session_id}",
    response_model=DeleteGameResponse,
    summary="Delete a game session",
    operation_id="delete_game",
)
async def delete_game(
    session_id: SessionIdentifier,
    close_room: bool = False,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("delete_game: session_id=%s close_room=%s", session_id, close_room)
    # Resolve the identifier (UUID or room slug) once, so the response reports the
    # canonical session id and an unresolvable identifier surfaces as 404 before any
    # teardown is attempted.
    resolved_id = await manager.resolve_session_id(session_id)
    async with manager.session_operation_lock(resolved_id):
        if close_room:
            session = await manager.get_session(resolved_id)
            await session.close_room()
        else:
            # Idempotent fast-path teardown: an ephemeral reconstruction may have
            # already been reclaimed by the server-side reaper (or by a prior
            # teardown), so a resolvable session that is already gone is treated as
            # already-deleted rather than a 404. The client teardown is best-effort
            # and never needs to distinguish "I deleted it" from "it was already
            # gone".
            try:
                await manager.delete_session(resolved_id)
            except SessionNotFoundError:
                logger.info(
                    "delete_game: session_id=%s already gone (idempotent)",
                    resolved_id,
                )
    logger.info("delete_game: session_id=%s -> deleted", resolved_id)
    return DeleteGameResponse(session_id=resolved_id)
