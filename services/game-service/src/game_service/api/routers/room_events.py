"""Router: room event observation endpoints (alerts, gui-update)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
from game_service.api.models import AlertsResponse, GuiUpdateResponse
from game_service.session.manager import SessionManager

router = APIRouter(tags=["room-events"])


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
    """Return the buffered server-sent alerts for the session (up to 50)."""
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
    """Return the latest GUI update hint per player for the session."""
    session = await manager.get_session(session_id)
    return GuiUpdateResponse(session_id=session_id, updates=session.get_gui_updates())
