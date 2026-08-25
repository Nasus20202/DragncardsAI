"""Router: game action execution and action catalogue endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import (
    ActionRequest,
    ExecuteActionResponse,
    SessionActionsResponse,
)
from game_service.catalog.service import get_plugin_action_catalog
from game_service.api.routers.meta import build_generic_action_catalog
from game_service.logic.session_manager import SessionManager
from game_service.logic.platform import DRAGNCARDS_PLATFORM, MARVEL_LCG_PLATFORM

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-actions"])


@router.post(
    "/games/{session_id}/actions",
    response_model=ExecuteActionResponse,
    summary="DEBUG ONLY: Execute a game action (generic endpoint)",
    operation_id="execute_action",
)
async def execute_action(
    session_id: SessionIdentifier,
    action: ActionRequest,
    manager: SessionManager = Depends(get_manager),
):
    logger.info(
        "execute_action: session_id=%s action=%s",
        session_id,
        action,
    )
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        await session.execute_action(action)

        # Check for error alerts from the action execution
        alerts = session.get_alerts()
        error: str | None = None
        for alert in alerts:
            if isinstance(alert, dict) and alert.get("level") == "error":
                error = alert.get("text", str(alert))

    logger.info("execute_action: session_id=%s -> success", session_id)
    return ExecuteActionResponse(session_id=session_id, success=True, error=error)


@router.get(
    "/games/{session_id}/actions",
    response_model=SessionActionsResponse,
    summary="List all actions accepted by this session",
    operation_id="get_session_actions",
)
async def get_session_actions(
    session_id: SessionIdentifier,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("get_session_actions: session_id=%s", session_id)
    session = await manager.get_session(session_id)
    catalog = session.driver.action_catalog()
    platform = getattr(session, "platform", DRAGNCARDS_PLATFORM)
    if platform not in {DRAGNCARDS_PLATFORM, MARVEL_LCG_PLATFORM}:
        platform = DRAGNCARDS_PLATFORM
    move_surface = getattr(session.driver, "move_surface", "typed_actions")
    if move_surface not in {"typed_actions", "enumerated_options"}:
        move_surface = "typed_actions"
    if catalog.get("plugin_metadata") is None:
        actions, raw_ops = build_generic_action_catalog()
        plugin_metadata = get_plugin_action_catalog(session.plugin_name)
        catalog = {
            "actions": actions,
            "raw_ops": raw_ops,
            "load_groups": plugin_metadata.load_groups,
            "plugin_metadata": plugin_metadata.to_dict(),
        }
    plugin_metadata = dict(catalog["plugin_metadata"] or {})
    plugin_metadata["platform"] = platform
    plugin_metadata["move_surface"] = move_surface
    return SessionActionsResponse(
        session_id=session.session_id,
        plugin_name=session.plugin_name or session.platform,
        platform=platform,
        move_surface=move_surface,
        actions=catalog["actions"],
        raw_ops=catalog["raw_ops"],
        load_groups=catalog["load_groups"],
        plugin_metadata=plugin_metadata,
    )
