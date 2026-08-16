"""Snapshot models shared by session logic and the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from game_service.schemas.base import StrictRequest

SNAPSHOT_SCHEMA_VERSION = 1


class GameStateSnapshot(StrictRequest):
    """Versioned snapshot document for setup import/export."""

    schema_version: int = Field(
        default=SNAPSHOT_SCHEMA_VERSION,
        description="Snapshot schema version used by the game-service",
    )
    plugin_name: str = Field(description="Plugin identity for the snapshot")
    game: dict[str, Any] = Field(
        description="Inner DragnCards game payload accepted by set_game"
    )
