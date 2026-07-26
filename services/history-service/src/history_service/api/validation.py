from __future__ import annotations

from typing import Annotated

from fastapi import Path

# A game id is an opaque session identifier produced by the game-service. It is
# interpolated into both database lookups and outbound internal-service URLs, so
# the route boundary constrains it to a short, URL-safe token: no slashes, dots,
# percent-encoding, or oversized values that could smuggle extra path segments
# or traversal into a trusted upstream call.
GAME_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

GameIdPath = Annotated[
    str,
    Path(
        pattern=GAME_ID_PATTERN,
        description="Opaque game/session identifier (1-64 chars: A-Z a-z 0-9 _ -).",
    ),
]
