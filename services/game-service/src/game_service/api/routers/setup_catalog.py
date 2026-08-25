"""Backend-neutral game setup discovery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from game_service.api.deps import get_manager
from game_service.api.models import SetupCatalogResponse
from game_service.logic.platform import DRAGNCARDS_PLATFORM, PlatformSlug
from game_service.logic.session_manager import SessionManager

router = APIRouter(tags=["game-setup"])


@router.get(
    "/games/setup-catalog",
    response_model=SetupCatalogResponse,
    summary="Discover setup selections for a game platform",
    operation_id="list_game_setup_catalog",
)
async def list_game_setup_catalog(
    platform: PlatformSlug = Query(
        DRAGNCARDS_PLATFORM,
        description="Platform whose opaque setup ids should be returned",
    ),
    manager: SessionManager = Depends(get_manager),
):
    return await manager.list_setup_catalog(platform)
