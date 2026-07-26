"""Router: prebuilt deck loading."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import LoadPrebuiltDeckResponse
from game_service.logic.exceptions import SessionError, SessionNotFoundError
from game_service.logic.session_manager import SessionManager

router = APIRouter(tags=["prebuilt-deck"])


@router.post(
    "/games/{session_id}/load-prebuilt-deck",
    response_model=LoadPrebuiltDeckResponse,
    summary="Load a prebuilt deck into a session. Use during setup to load a prebuilt deck into a session. Find a deck ID using the search_prebuilt_sets_marvel_champions endpoint.",
    operation_id="load_prebuilt_deck",
)
async def load_prebuilt_deck(
    session_id: SessionIdentifier,
    deck_id: str,
    manager: SessionManager = Depends(get_manager),
):
    try:
        await manager.load_prebuilt_deck(session_id, deck_id)
    except SessionNotFoundError as exc:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": str(exc), "type": "session_not_found"}},
        )
    except SessionError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": str(exc), "type": "session_error"}},
        )
    return LoadPrebuiltDeckResponse(session_id=session_id, success=True)
