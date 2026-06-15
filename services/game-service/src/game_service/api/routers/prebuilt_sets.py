"""Router: Marvel Champions prebuilt set catalog."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from game_service.api.models import ListPrebuiltSetsResponse, PrebuiltSetSummary
from game_service.catalog.service import search_prebuilt_sets

logger = logging.getLogger(__name__)

router = APIRouter(tags=["prebuilt-sets"])


def _search_prebuilt_sets_response(name: str | None, type: str | None):
    results = search_prebuilt_sets(name=name, type=type)
    sets = [PrebuiltSetSummary.model_validate(item) for item in results]
    return ListPrebuiltSetsResponse(total=len(sets), sets=sets)


@router.get(
    "/prebuilt-sets/marvel-champions",
    response_model=ListPrebuiltSetsResponse,
    operation_id="search_prebuilt_sets_marvel_champions",
    summary="Search prebuilt Marvel Champions sets",
)
async def list_available_prebuilt_sets(
    name: str | None = Query(default=None, description="Substring match on set name"),
    type: str | None = Query(default=None, description="Exact match on set type"),
):
    logger.info("search_prebuilt_sets_marvel_champions: name=%r type=%r", name, type)
    return _search_prebuilt_sets_response(name, type)
