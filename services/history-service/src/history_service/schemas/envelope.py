from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ENVELOPE_VERSION = 1
VALID_ACTORS = ("agent", "game-service", "evaluator", "user")
Actor = Literal["agent", "game-service", "evaluator", "user"]

# The orchestration mode the agent session that produced an event ran in.
# ``chat`` is the original single-agent flow; ``orchestrated`` is a table of
# per-seat agents driven by a coordinating agent.
SESSION_MODE_CHAT = "chat"
SESSION_MODE_ORCHESTRATED = "orchestrated"

# Agent event types that carry no ``conversation_context``, and so can never be
# the event an agent-context restore rebuilds a conversation from.
#
# ``illegal_action`` is the orchestrator's record that a seat broke the rules. It
# is a judgement about game state rather than a turn of a conversation, so it is
# emitted with no context — which is precisely why it has to be excluded here.
# Without the exclusion, a finding recorded after a game's last move is the latest
# ``agent`` event, so the restore selects it, finds no context, and silently
# rebuilds an EMPTY conversation. It degrades quietly rather than failing, which is
# the worst shape this could take.
#
# Any future agent event type carrying no conversation context belongs in this set.
# The alternative — allow-listing the types that *do* carry one — was rejected
# because it would silently stop restoring already-stored rows whose type nobody
# remembered to list, and a restore that quietly finds nothing is the very failure
# being fixed here.
AGENT_EVENT_TYPES_WITHOUT_CONTEXT = frozenset({"illegal_action"})

# A game id is an opaque session identifier produced by the game-service. It is
# interpolated into both database lookups and outbound internal-service URLs, so
# it is constrained to a short, URL-safe token: no slashes, dots,
# percent-encoding, or oversized values that could smuggle extra path segments
# or traversal into a trusted upstream call. Enforced at the route boundary
# (``api.validation.GameIdPath``) and on any game id read out of an import file.
GAME_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


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

    An event produced by an agent session MAY likewise carry an optional
    ``session_mode`` key naming the orchestration mode that session ran in. It is
    absent on a chat-mode event and on every event recorded before the mode
    existed, which is why nothing reads it directly: :func:`session_mode_of`
    resolves it, with ``chat`` as the default.
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


def session_mode_of(payload: Mapping[str, Any]) -> str:
    """The orchestration mode a stored payload came from, defaulting to ``chat``.

    The single place the default lives, so no caller has to remember it and no
    two callers can disagree about it. Three cases collapse to ``chat`` here: a
    payload from a chat-mode session (which omits the key), a payload recorded
    before the mode existed (which could not have carried it), and a payload
    whose ``session_mode`` is not a mode this service knows — a value from a
    future producer is not worth propagating as if it were understood.

    Deliberately derived from the payload alone. The mode must be readable
    WITHOUT inferring it from the presence or absence of a seat identifier: an
    orchestrated event with no ``player`` is the coordinating agent's own
    bookkeeping, not a chat event, and treating a missing seat as evidence of
    chat mode would misread exactly those events.
    """
    value = payload.get("session_mode")
    if value == SESSION_MODE_ORCHESTRATED:
        return SESSION_MODE_ORCHESTRATED
    return SESSION_MODE_CHAT


class StoredSnapshot(BaseModel):
    game_id: str
    snapshot_at_seq: int
    snapshot: dict[str, Any]
    created_at: datetime
