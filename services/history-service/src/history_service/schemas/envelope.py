from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ENVELOPE_VERSION = 1
VALID_ACTORS = ("agent", "game-service", "evaluator", "user")
Actor = Literal["agent", "game-service", "evaluator", "user"]


class EventEnvelope(BaseModel):
    """Versioned event envelope as supplied by producers.

    The history-service validates and stores this. ``seq`` and ``recorded_at``
    are assigned by the history-service at commit time and are NOT part of the
    producer-supplied envelope. Unknown additional fields are tolerated for
    forward compatibility (``extra="allow"``).

    ``payload`` is stored and returned verbatim, so structured payload keys are
    preserved on read-back. In particular an ``evaluation`` event MAY carry an
    optional ``player`` key in its payload (e.g. ``"player1"``) identifying the
    player a verdict pertains to; it is stored and returned unchanged, and is
    optional for backward compatibility with verdicts that predate per-player
    scoring.
    """

    model_config = ConfigDict(extra="allow")

    envelope_version: int = Field(default=ENVELOPE_VERSION)
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    game_id: str = Field(min_length=1)
    actor: Actor
    event_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    idempotency_key: str = Field(min_length=1)
    producer_offset: int | str | None = None


class StoredEvent(BaseModel):
    """An event as persisted, including the history-assigned fields."""

    event_id: str
    game_id: str
    seq: int
    envelope_version: int
    actor: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    recorded_at: datetime
    idempotency_key: str
    producer_offset: int | str | None = None


class StoredSnapshot(BaseModel):
    game_id: str
    snapshot_at_seq: int
    snapshot: dict[str, Any]
    created_at: datetime
