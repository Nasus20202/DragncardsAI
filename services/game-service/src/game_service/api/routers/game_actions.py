"""Router: game action execution and action catalogue endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
from game_service.api.models import (
    ActionRequest,
    ExecuteActionResponse,
    SessionActionsResponse,
)
from game_service.catalog.service import get_plugin_action_catalog
from game_service.api.routers.meta import build_generic_action_catalog
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-actions"])


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
    actions, raw_ops = build_generic_action_catalog()
    plugin_metadata = get_plugin_action_catalog(session.plugin_name)
    return SessionActionsResponse(
        session_id=session_id,
        plugin_name=session.plugin_name,
        actions=actions,
        raw_ops=raw_ops,
        load_groups=plugin_metadata.load_groups,
        plugin_metadata=plugin_metadata.to_dict(),
    )
