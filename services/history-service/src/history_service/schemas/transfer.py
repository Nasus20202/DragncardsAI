from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from history_service.schemas.envelope import GAME_ID_PATTERN, Actor

# A bundle is NDJSON: one self-contained JSON object per line, keys sorted, in
# the order header -> events (ascending seq) -> snapshots (ascending
# snapshot_at_seq) -> footer. One event is exactly one line, so two exports of
# the same scenario diff to the events that actually differ, and a malformed
# file can be reported with the line number that broke.
BUNDLE_FORMAT = "dragncards-ai.game-history"
BUNDLE_FORMAT_VERSION = 1

BUNDLE_MEDIA_TYPE = "application/x-ndjson"
BUNDLE_FILE_SUFFIX = ".ndjson"

# Field bounds mirror the storage column widths in ``storage/models.py`` so an
# oversized value from an untrusted file is rejected by schema validation with a
# readable message instead of surfacing as a database error mid-transaction.
_EVENT_ID_MAX = 64
_EVENT_TYPE_MAX = 128
_IDEMPOTENCY_KEY_MAX = 128
_PRODUCER_OFFSET_MAX = 128
_GAME_ID_MAX = 64
_PLUGIN_NAME_MAX = 128


class BundleHeader(BaseModel):
    """First line of a bundle: what it is and how much it should contain.

    ``extra="ignore"`` on every bundle record means unknown keys from a newer
    (or hand-edited) file are dropped rather than carried into storage.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["header"]
    format: str = Field(min_length=1, max_length=128)
    format_version: int = Field(ge=1)
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=_GAME_ID_MAX)
    plugin_name: str | None = Field(default=None, max_length=_PLUGIN_NAME_MAX)
    exported_at: datetime
    event_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)


class BundleEvent(BaseModel):
    """One stored event, verbatim apart from the dropped ``game_id``.

    ``game_id`` is deliberately absent: the target game is chosen at import
    time, so carrying a per-line copy would only create a second, conflicting
    source of truth. ``payload`` is a plain JSON object stored verbatim, exactly
    as the ingest path already stores producer payloads.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["event"]
    seq: int = Field(ge=1)
    event_id: str = Field(min_length=1, max_length=_EVENT_ID_MAX)
    envelope_version: int = Field(ge=1)
    actor: Actor
    event_type: str = Field(min_length=1, max_length=_EVENT_TYPE_MAX)
    payload: dict[str, Any]
    occurred_at: datetime
    recorded_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=_IDEMPOTENCY_KEY_MAX)
    producer_offset: int | str | None = None

    @field_validator("producer_offset")
    @classmethod
    def validate_producer_offset(cls, value: int | str | None) -> int | str | None:
        # Stored as text, so bound the rendered length rather than the int value.
        if value is not None and len(str(value)) > _PRODUCER_OFFSET_MAX:
            raise ValueError(
                f"producer_offset must be at most {_PRODUCER_OFFSET_MAX} characters"
            )
        return value


class BundleSnapshot(BaseModel):
    """One stored snapshot: a verbatim game-service ``GameStateSnapshot``."""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["snapshot"]
    snapshot_at_seq: int = Field(ge=1)
    snapshot: dict[str, Any]
    created_at: datetime


class BundleFooter(BaseModel):
    """Last line of a bundle: the counts, repeated.

    Repeating them is what makes a truncated download or a concatenated file a
    loud error instead of a silently partial import.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["footer"]
    event_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)


class ImportResponse(BaseModel):
    """What an accepted import wrote, and where."""

    game_id: str
    source_game_id: str
    imported_events: int
    imported_snapshots: int
    first_seq: int | None = None
    last_seq: int | None = None
