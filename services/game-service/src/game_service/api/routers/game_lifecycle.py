"""Router: game session lifecycle endpoints."""

from __future__ import annotations

import logging
import uuid

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


def _is_uuid(value: str) -> bool:
    """True when ``value`` is a well-formed UUID (a real session identifier)."""
    try:
        uuid.UUID(str(value))
    except ValueError, AttributeError, TypeError:
        return False
    return True


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
        "its session metadata, including the canonical UUID `session_id`. This is a "
        "read-only lookup and the ONLY endpoint that accepts a room slug. State, "
        "mutation, and delete endpoints remain UUID-only because the slug is "
        "low-entropy and guessable; use the returned `session_id` to address those "
        "endpoints."
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
    async with manager.session_operation_lock(session_id):
        if close_room:
            session = await manager.get_session(session_id)
            await session.close_room()
        else:
            # Idempotent fast-path teardown: an ephemeral reconstruction may have
            # already been reclaimed by the server-side reaper (or by a prior
            # teardown), so a valid-UUID session that is already gone is treated
            # as already-deleted rather than a 404. The client teardown is
            # best-effort and never needs to distinguish "I deleted it" from "it
            # was already gone". A non-UUID identifier (e.g. a guessable room
            # slug) is NOT a valid session id and must still surface as 404 — it
            # never authorizes a delete.
            try:
                await manager.delete_session(session_id)
            except SessionNotFoundError:
                if not _is_uuid(session_id):
                    raise
                logger.info(
                    "delete_game: session_id=%s already gone (idempotent)",
                    session_id,
                )
    logger.info("delete_game: session_id=%s -> deleted", session_id)
    return DeleteGameResponse(session_id=session_id)
