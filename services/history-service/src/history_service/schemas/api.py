from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from history_service.schemas.envelope import (
    SESSION_MODE_CHAT,
    StoredEvent,
    StoredSnapshot,
    session_mode_of,
)


class EventResponse(BaseModel):
    """A stored event as a reader receives it.

    ``session_mode`` is the one field here that is not a stored column: it is the
    orchestration mode the producing agent session ran in, projected out of the
    payload by :func:`~history_service.schemas.envelope.session_mode_of` so a
    consumer can tell an orchestrated timeline from a chat one directly. It is
    surfaced as a field rather than left for the consumer to dig out of
    ``payload`` because the payload only carries the key when the mode is
    orchestrated, and a consumer should neither have to know that nor be tempted
    to read the absence of a seat identifier as evidence of chat mode — which
    would misclassify the orchestrating agent's own seatless events. Reads
    ``chat`` for every event recorded before the mode existed.
    """

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
    session_mode: str = SESSION_MODE_CHAT

    @classmethod
    def from_stored(cls, event: StoredEvent) -> "EventResponse":
        return cls(
            **event.model_dump(),
            session_mode=session_mode_of(event.payload),
        )


class EventListResponse(BaseModel):
    game_id: str
    events: list[EventResponse]
    next_after_seq: int | None = None


class TimelineEventResponse(EventResponse):
    """A timeline entry: the same shape as an event, with a lighter payload.

    ``payload_complete`` is false for every entry a timeline listing produces, so
    a client can tell that the unbounded payload fields (the raw DragnCards
    ``state`` and an agent move's ``conversation_context``) were left out and must
    be fetched per event before they are shown. ``payload["state"]["game"]`` still
    carries ``roundNumber`` and ``stepId``, which is all the round and phase
    labels need.
    """

    payload_complete: bool = False


class TimelineListResponse(BaseModel):
    game_id: str
    events: list[TimelineEventResponse]
    next_after_seq: int | None = None


class SnapshotResponse(BaseModel):
    game_id: str
    snapshot_at_seq: int
    created_at: datetime
    snapshot: dict[str, Any]

    @classmethod
    def from_stored(cls, snapshot: StoredSnapshot) -> "SnapshotResponse":
        return cls(**snapshot.model_dump())


class SnapshotListResponse(BaseModel):
    game_id: str
    snapshots: list[SnapshotResponse]


class BackfillResponse(BaseModel):
    game_id: str
    seq: int
    inserted: bool


class GameSummaryResponse(BaseModel):
    game_id: str
    event_count: int
    first_recorded_at: datetime
    last_recorded_at: datetime


class GameListResponse(BaseModel):
    games: list[GameSummaryResponse]


class GameDeletionResponse(BaseModel):
    game_id: str
    deleted_events: int
    deleted_snapshots: int


class RestoreRequest(BaseModel):
    target_seq: int = Field(ge=1)
    mode: Literal["new", "in_place"] = "new"
    # When true, a ``mode="new"`` restore creates an *ephemeral* branch session:
    # a non-emitting, server-reaped reconstruction used only for viewing a past
    # moment. It never pollutes history and is reclaimed after a TTL even if the
    # client never tears it down. Ignored for ``mode="in_place"``.
    ephemeral: bool = False
    # An existing game-service session to restore *into*, instead of creating one.
    # A caller viewing a second moment of the same game already owns a room, and
    # re-pointing that room at the new moment was measured at ~55 ms against
    # ~730 ms to build a replacement.
    #
    # Honoured only for an ``ephemeral`` ``mode="new"`` restore, and only when a
    # full-state base at or before the target exists.
    #
    # The base is what makes it correct: loading it issues the DragnCards
    # ``set_game`` action, which replaces the room's game document outright, so
    # nothing from the moment the session previously held can survive. A restore
    # with no base replays forward onto whatever the session already holds, so it
    # always creates a fresh session and leaves the supplied one untouched.
    #
    # ``ephemeral`` is what keeps the field aimed at the flow it exists for. It
    # overwrites a session the caller names rather than one the restore created,
    # and an ephemeral reconstruction is by definition a throwaway built for
    # viewing; a kept branch restore owns the room it produces.
    reuse_session_id: str | None = Field(default=None, max_length=200)


class RestoreResponse(BaseModel):
    # ``status`` and ``session_id`` form the success contract the dashboard
    # discriminates on: a 2xx body with ``status="restored"`` is success, while
    # failures return a non-2xx HTTP error carrying ``detail``. ``session_id``
    # mirrors ``game_session_id`` so the UI can name the restored session.
    status: Literal["restored"] = "restored"
    game_id: str
    target_seq: int
    mode: Literal["new", "in_place"]
    game_session_id: str
    session_id: str
    orchestrator_session_id: str | None = None
    snapshot_at_seq: int | None = None
    replayed_event_seqs: list[int] = Field(default_factory=list)
    status_verified: bool | None = None
    divergence: str | None = None
    # The DragnCards room holding the restored state. Populated for a branch
    # ("new") restore, whose product is a room the caller then has to open — so
    # the slug travels with the response rather than forcing the caller to list
    # every live session and search it by id.
    room_slug: str | None = None
    # Whether the agent conversation was rebuilt alongside the game state, and a
    # human-readable reason when it was not. A game with no active agent session
    # bound to it has none to resume; that is a normal state for a game being
    # browsed in history, so it is reported here instead of failing the restore.
    agent_context_restored: bool = False
    agent_context_note: str | None = None
