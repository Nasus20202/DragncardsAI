from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PLATFORM_DRAGNCARDS = "dragncards"
PLATFORM_MARVEL_LCG = "marvel-lcg"
Platform = Literal["dragncards", "marvel-lcg"]


class StoredEvent(BaseModel):
    """An event as returned by the history-service read API.

    Mirrors the history-service ``StoredEvent`` shape. Unknown additional fields
    are tolerated for forward compatibility.
    """

    model_config = ConfigDict(extra="allow")

    event_id: str
    game_id: str
    platform: Platform = PLATFORM_DRAGNCARDS
    seq: int
    envelope_version: int
    actor: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    recorded_at: datetime | None = None
    idempotency_key: str | None = None
    producer_offset: int | str | None = None
