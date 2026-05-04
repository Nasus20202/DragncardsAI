"""Router: game action execution and action catalogue endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
from game_service.api.models import ActionRequest, ExecuteActionResponse, SessionActionsResponse
from game_service.api.routers.meta import RAW_OPS, build_action_schemas
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"])

_PLUGIN_LOAD_GROUPS: dict[str, list[str]] = {
    "marvel-champions": [
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
    logger.info(
        "execute_action: session_id=%s action_type=%r",
        session_id,
        action.__class__.__name__,
    )
    session = await manager.get_session(session_id)
    new_state = await session.execute_action(action)
    logger.info("execute_action: session_id=%s -> success", session_id)
    return ExecuteActionResponse(session_id=session_id, state=new_state)


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
