"""Router: core game session endpoints (create, list, state, actions, delete)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from game_service.api.deps import get_manager
from game_service.api.models import (
    ActionRequest,
    AttachGameRequest,
    AttachGameResponse,
    CreateGameRequest,
    CreateGameResponse,
    DeleteGameResponse,
    ExecuteActionResponse,
    GameStateResponse,
    ListGamesResponse,
    SessionActionsResponse,
    SessionMetadata,
)
from game_service.api.routers.meta import RAW_OPS, build_action_schemas
from game_service.session.manager import SessionError, SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"])

# Load groups per plugin — the groups an agent can use in a load_cards action.
# Keys match plugin_name values registered in main.py's PLUGIN_REGISTRY.
_PLUGIN_LOAD_GROUPS: dict[str, list[str]] = {
    "marvel-champions": [
        # Per-player groups (use playerN for the active player, or player1..player4 explicitly)
        "playerNDeck",
        "playerNDeck2",
        "playerNDiscard",
        "playerNHand",
        "playerNPlay1",
        "playerNPlay2",
        "playerNPlay3",
        "playerNPlay4",
        "playerNEngaged",
        "playerNNemesisSet",
        # Shared/encounter groups
        "sharedEncounterDeck",
        "sharedEncounterDiscard",
        "sharedEncounter2Deck",
        "sharedEncounter2Discard",
        "sharedEncounter3Deck",
        "sharedMainScheme",
        "sharedMainSchemeDeck",
        "sharedVillain",
        "sharedVillainDeck",
        "sharedVictoryDisplay",
        "sharedCampaignDeck",
    ],
}


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
    """
    Create a new DragnCards game room for the specified plugin and
    return the session ID plus metadata.
    """
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
    """
    Re-attach to an existing DragnCards room by slug without creating a new room.

    Use this when the service has restarted and you need to reconnect to a
    room that is still open. You must know the room_slug (visible in the
    DragnCards browser URL or from a previous session's metadata).
    """
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
    """Return metadata for all active game sessions."""
    sessions = [SessionMetadata(**m) for m in manager.list_sessions()]
    logger.debug("list_games: %d active session(s)", len(sessions))
    return ListGamesResponse(sessions=sessions)


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
    """Return the latest cached game state for the given session."""
    logger.info("get_game_state: session_id=%s", session_id)
    session = await manager.get_session(session_id)
    state = await session.get_state()
    logger.debug(
        "get_game_state: session_id=%s -> state keys=%s",
        session_id,
        list(state.keys()) if isinstance(state, dict) else type(state).__name__,
    )
    return GameStateResponse(session_id=session_id, state=state)


@router.post(
    "/games/{session_id}/actions",
    response_model=ExecuteActionResponse,
    summary="Execute a game action",
    operation_id="execute_action",
)
async def execute_action(
    session_id: str,
    action: ActionRequest,
    manager: SessionManager = Depends(get_manager),
):
    """
    Translate and execute the given action on the specified session.
    Returns the resulting game state.
    """
    logger.info(
        "execute_action: session_id=%s action_type=%r",
        session_id,
        action.__class__.__name__,
    )
    session = await manager.get_session(session_id)
    new_state = await session.execute_action(action)
    logger.info("execute_action: session_id=%s -> success", session_id)
    return ExecuteActionResponse(session_id=session_id, state=new_state)


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
    """
    Close the WebSocket connection and clean up the session.

    Pass `?close_room=true` to first push `close_room` to the DragnCards
    backend (saving and tearing down the room server-side) before cleaning up.
    """
    logger.info("delete_game: session_id=%s close_room=%s", session_id, close_room)
    if close_room:
        session = await manager.get_session(session_id)
        await session.close_room()
    else:
        await manager.delete_session(session_id)
    logger.info("delete_game: session_id=%s -> deleted", session_id)
    return DeleteGameResponse(session_id=session_id)


@router.get(
    "/games/{session_id}/actions",
    response_model=SessionActionsResponse,
    summary="List all actions accepted by this session",
    operation_id="get_session_actions",
)
async def get_session_actions(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    """
    Return the full catalogue of action types accepted by this session's
    POST /games/{session_id}/actions endpoint, plus the valid loadGroupId
    values for the plugin this session is running.

    Use this before constructing a `load_cards` action to know which
    groups are available (e.g. 'playerNDeck', 'sharedEncounterDeck').
    """
    logger.info("get_session_actions: session_id=%s", session_id)
    session = await manager.get_session(session_id)
    load_groups = _PLUGIN_LOAD_GROUPS.get(session.plugin_name, [])
    return SessionActionsResponse(
        session_id=session_id,
        plugin_name=session.plugin_name,
        actions=build_action_schemas(),
        raw_ops=RAW_OPS,
        load_groups=load_groups,
    )
