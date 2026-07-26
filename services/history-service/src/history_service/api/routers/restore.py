from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from history_service.api.deps import get_restore_service
from history_service.api.validation import GameIdPath
from history_service.runtime.restore import RestoreError, RestoreService
from history_service.schemas.api import RestoreRequest, RestoreResponse

router = APIRouter(tags=["restore"])


@router.post("/games/{game_id}/restore", response_model=RestoreResponse)
async def restore_game(
    game_id: GameIdPath,
    body: RestoreRequest,
    restore_service: RestoreService = Depends(get_restore_service),
) -> RestoreResponse:
    try:
        result = await restore_service.restore(
            game_id,
            target_seq=body.target_seq,
            mode=body.mode,
            ephemeral=body.ephemeral,
        )
    except RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RestoreResponse(
        status="restored",
        game_id=result.game_id,
        target_seq=result.target_seq,
        mode=result.mode,
        game_session_id=result.game_session_id,
        session_id=result.game_session_id,
        orchestrator_session_id=result.orchestrator_session_id,
        snapshot_at_seq=result.snapshot_at_seq,
        replayed_event_seqs=result.replayed_event_seqs,
        status_verified=result.status_verified,
        divergence=result.divergence,
    )
