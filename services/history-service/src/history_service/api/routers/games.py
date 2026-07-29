from __future__ import annotations

from fastapi import APIRouter, Depends

from history_service.api.deps import get_repository
from history_service.api.validation import GameIdPath
from history_service.schemas.api import (
    GameDeletionResponse,
    GameListResponse,
    GameSummaryResponse,
)
from history_service.storage.repository import Repository

router = APIRouter(tags=["games"])


@router.get(
    "/games",
    response_model=GameListResponse,
    operation_id="list_recorded_games",
)
async def list_games(
    repo: Repository = Depends(get_repository),
) -> GameListResponse:
    summaries = await repo.list_games()
    return GameListResponse(
        games=[
            GameSummaryResponse(
                game_id=summary.game_id,
                event_count=summary.event_count,
                first_recorded_at=summary.first_recorded_at,
                last_recorded_at=summary.last_recorded_at,
            )
            for summary in summaries
        ]
    )


@router.delete(
    "/games/{game_id}",
    response_model=GameDeletionResponse,
    operation_id="delete_game_history",
)
async def delete_game(
    game_id: GameIdPath,
    repo: Repository = Depends(get_repository),
) -> GameDeletionResponse:
    """Delete all history for a game.

    Idempotent: an absent game returns 200 with zero counts (never 404).
    """
    result = await repo.delete_game_history(game_id)
    return GameDeletionResponse(
        game_id=result.game_id,
        deleted_events=result.deleted_events,
        deleted_snapshots=result.deleted_snapshots,
    )
