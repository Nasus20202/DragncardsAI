from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from history_service.schemas.envelope import GAME_ID_PATTERN, Actor

# A bundle is NDJSON: one self-contained JSON object per line, keys sorted, in
# the order header -> blob/event/snapshot -> footer, with events in ascending
# ``seq`` and snapshots after them in ascending ``snapshot_at_seq``. One event is
# exactly one line, so two exports of the same scenario diff to the events that
# actually differ, and a malformed file can be reported with the line number that
# broke.
BUNDLE_FORMAT = "dragncards-ai.game-history"

# Version 2 adds the ``blob`` record kind: any repeated value is carried once and
# referenced, which is what takes a real recorded game from tens of megabytes to
# a file whose every record fits on a screen. Version 1 bundles are still read —
# they already declared their version, so detection is a field read rather than a
# guess — but they may not contain blobs, because that kind did not exist yet.
BUNDLE_FORMAT_VERSION = 2
BUNDLE_SUPPORTED_FORMAT_VERSIONS = (1, 2)

BUNDLE_MEDIA_TYPE = "application/x-ndjson"
BUNDLE_FILE_SUFFIX = ".ndjson"

# ``full`` is lossless. ``minimal`` elides the LLM prompt material and nothing
# else: the captured system prompt, tool schemas, prior turns and tool results
# that were sent to the model. What the agent decided — its reasoning, intended
# action and arguments — is the substance of a recorded game, not prompt
# material, and stays in both modes.
BundleMode = Literal["full", "minimal"]
BUNDLE_MODES: tuple[BundleMode, ...] = ("full", "minimal")

AGENT_MOVE_EVENT_TYPE = "agent_move"
CONVERSATION_CONTEXT_FIELD = "conversation_context"

# Declared in the header of a ``minimal`` bundle, as ``<event type>.<field>``.
MINIMAL_OMITTED_PAYLOAD_FIELDS: tuple[str, ...] = (
    f"{AGENT_MOVE_EVENT_TYPE}.{CONVERSATION_CONTEXT_FIELD}",
)


def omitted_payload_fields_for(mode: BundleMode) -> list[str]:
    """What a mode declares it left out, in header order."""
    return list(MINIMAL_OMITTED_PAYLOAD_FIELDS) if mode == "minimal" else []


# Field bounds mirror the storage column widths in ``storage/models.py`` so an
# oversized value from an untrusted file is rejected by schema validation with a
# readable message instead of surfacing as a database error mid-transaction.
_EVENT_ID_MAX = 64
_EVENT_TYPE_MAX = 128
_IDEMPOTENCY_KEY_MAX = 128
_PRODUCER_OFFSET_MAX = 128
_GAME_ID_MAX = 64
_PLUGIN_NAME_MAX = 128
# Blob ids are minted by the exporter and paths are bounded by nesting depth;
# both are bounded here so a hand-edited file cannot carry an unbounded string.
_BLOB_ID_MAX = 32
_FIRST_SEEN_MAX = 512


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
    # Defaulted so a version 1 header — which predates both fields — validates
    # and reads as what it is: a lossless export.
    mode: BundleMode = "full"
    omitted_payload_fields: list[str] = Field(default_factory=list)


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


class BundleBlob(BaseModel):
    """One value carried once and referenced from wherever it occurs.

    ``first_seen`` is the dotted path at which the value was first encountered
    (``event[42].payload.state.game.cardById``). It is what keeps the format
    readable: a bare ``{"$ref": "b412"}`` says nothing, but
    ``grep '"first_seen": "event\\[42\\]'`` answers what event 42 actually
    carried, without decoding the file.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["blob"]
    id: str = Field(pattern=r"^b[1-9][0-9]*$", max_length=_BLOB_ID_MAX)
    first_seen: str = Field(min_length=1, max_length=_FIRST_SEEN_MAX)
    # Only objects and arrays are ever extracted; a scalar is never worth a line.
    value: dict[str, Any] | list[Any]


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
    # Only the footer can declare this: blobs are discovered while the export
    # streams, so the header — written first — cannot know how many there will
    # be without buffering the whole bundle. Defaulted for version 1, which had
    # none.
    blob_count: int = Field(default=0, ge=0)


class ImportResponse(BaseModel):
    """What an accepted import wrote, and where."""

    game_id: str
    source_game_id: str
    imported_events: int
    imported_snapshots: int
    first_seq: int | None = None
    last_seq: int | None = None
    # The mode the bundle's header declared, so a caller can tell a minimal
    # import from a full one rather than inferring it from empty conversations.
    mode: BundleMode = "full"
    # Imported payloads are recorded evidence and are never rewritten, so an
    # import onto a new id leaves references to the source game inside them.
    # Counting them is what stops that from being silent. Zero when the target
    # and the source are the same id, because then they are current, not stale.
    source_id_references: int = 0
