"""Router: card database search endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from game_service.api.models import CardResult, SearchCardsResponse
from game_service.session.card_db import search_cards

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cards"])


@router.get(
    "/cards",
    response_model=SearchCardsResponse,
    operation_id="search_cards",
    summary="Search the card database",
)
async def search_cards_endpoint(
    name: str | None = Query(
        default=None,
        description="Substring match on card name (case-insensitive), e.g. 'Spider-Man'",
    ),
    type_code: str | None = Query(
        default=None,
        description=(
            "Exact match on card type. One of: hero, alter_ego, ally, event, upgrade, "
            "support, resource, villain, main_scheme, side_scheme, minion, attachment, "
            "treachery, environment, obligation, player_side_scheme, leader"
        ),
    ),
    classification: str | None = Query(
        default=None,
        description=(
            "Substring match on classification/aspect, e.g. 'Justice', 'Aggression', "
            "'Leadership', 'Protection', 'Basic', 'Hero'"
        ),
    ),
    official_only: bool = Query(
        default=True,
        description="If true (default), exclude custom/unofficial cards",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of results to return",
    ),
):
    """
    Search the DragnCards card database by name, type, and/or classification.

    Returns card records including the `database_id` (UUID) needed to construct
    a `load_cards` action. Searches are case-insensitive substring matches.

    Examples:
    - `?name=Spider-Man&type_code=hero` — find hero cards named Spider-Man
    - `?name=Black Panther` — all cards with Black Panther in the name
    - `?type_code=villain` — all villain cards (use limit to page)
    - `?type_code=ally&classification=Justice` — Justice aspect allies
    """
    logger.info(
        "search_cards: name=%r type_code=%r classification=%r official_only=%s limit=%d",
        name,
        type_code,
        classification,
        official_only,
        limit,
    )
    results = search_cards(
        name=name,
        type_code=type_code,
        classification=classification,
        official_only=official_only,
        limit=limit,
    )
    cards = [CardResult(**r) for r in results]
    return SearchCardsResponse(total=len(cards), cards=cards)
