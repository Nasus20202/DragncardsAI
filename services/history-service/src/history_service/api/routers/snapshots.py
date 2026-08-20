from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from history_service.api.deps import get_repository
from history_service.api.validation import GameIdPath
from history_service.schemas.api import SnapshotListResponse, SnapshotResponse
from history_service.schemas.envelope import PLATFORM_DRAGNCARDS, Platform
from history_service.storage.repository import Repository

router = APIRouter(tags=["snapshots"])


@router.get(
    "/games/{game_id}/snapshots",
    response_model=SnapshotListResponse,
    operation_id="list_game_snapshots",
)
async def list_snapshots(
    game_id: GameIdPath,
    platform: Platform = Query(default=PLATFORM_DRAGNCARDS),
    repo: Repository = Depends(get_repository),
) -> SnapshotListResponse:
    snapshots = await repo.list_snapshots(game_id, platform=platform)
    return SnapshotListResponse(
        game_id=game_id,
        snapshots=[SnapshotResponse.from_stored(item) for item in snapshots],
    )
