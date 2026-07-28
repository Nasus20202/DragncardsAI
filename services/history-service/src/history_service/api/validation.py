from __future__ import annotations

from typing import Annotated

from fastapi import Path, Query

# Re-exported so route declarations and the schema layer share one definition of
# what a game id may look like, and why (see ``schemas.envelope``).
from history_service.schemas.envelope import GAME_ID_PATTERN

__all__ = ["GAME_ID_PATTERN", "GameIdPath", "GameIdQuery"]

GameIdPath = Annotated[
    str,
    Path(
        pattern=GAME_ID_PATTERN,
        description="Opaque game/session identifier (1-64 chars: A-Z a-z 0-9 _ -).",
    ),
]

# The same constraint for a game id supplied as an optional query parameter (the
# import target), so a crafted id is rejected at the boundary there too.
GameIdQuery = Annotated[
    str | None,
    Query(
        pattern=GAME_ID_PATTERN,
        description=(
            "Target game/session identifier (1-64 chars: A-Z a-z 0-9 _ -). "
            "Defaults to the game_id recorded in the bundle header."
        ),
    ),
]
