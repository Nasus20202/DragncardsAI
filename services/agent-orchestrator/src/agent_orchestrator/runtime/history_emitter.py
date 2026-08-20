from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol, TypedDict
from urllib.parse import urlparse
from uuid import uuid4

from agent_orchestrator.runtime.session_modes import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
)
from agent_orchestrator.runtime.platforms import (
    DEFAULT_PLATFORM,
    MARVEL_LCG_CATALOG_TOOLS,
    PLATFORM_MARVEL_LCG,
    normalize_platform,
)
from agent_orchestrator.storage.valkey import RespConnection
from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

ENVELOPE_VERSION = 1
HISTORY_ACTOR_AGENT = "agent"
HISTORY_ACTOR_USER = "user"

# An illegal-action finding is recorded as an *agent* event rather than under a
# new actor: ``actor`` is a fixed ``Literal`` in the history-service envelope
# (``agent``/``game-service``/``evaluator``/``user``), so a new actor would be a
# schema change every consumer has to learn. The event type is what distinguishes
# it, and eval-service's ``is_agent_move`` predicate is what keeps it from being
# graded as a move.
HISTORY_EVENT_TYPE_ILLEGAL_ACTION = "illegal_action"
MARVEL_LCG_OPTION_PAYLOAD_KEY = "marvel_lcg_option"


class MarvelLcgOptionIdentity(TypedDict):
    """The durable option identity consumed by platform-aware evaluation."""

    id: str | int
    name: str
    event: str


# Resolution states an illegal-action finding can be recorded in.
ILLEGAL_ACTION_STATUS_OPEN = "open"
ILLEGAL_ACTION_STATUS_RESOLVED = "resolved"

# Keys used inside AgentSession.metadata_json to carry history-related state.
SESSION_GAME_ID_KEY = "game_id"
SESSION_PLATFORM_KEY = "platform"
SESSION_RESTORED_CONTEXT_KEY = "restored_conversation_context"


def restored_conversation_context(session: Any) -> list[dict[str, Any]]:
    """The conversation a restore attached to this session, or an empty list.

    It is prepended to every request the session ever sends, it is whatever the
    restoring caller supplied, and compaction never touches it — so anything
    estimating what a turn costs has to count it. Shared with the context
    estimate for exactly that reason.
    """
    metadata = getattr(session, "metadata_json", None) or {}
    context = metadata.get(SESSION_RESTORED_CONTEXT_KEY)
    if isinstance(context, list) and context:
        return context
    return []


# game-service MCP tools that observe state without mutating the game.
# Everything else exposed by the game-service MCP is treated as game-mutating
# and therefore worth emitting as an agent move/decision event.
_NON_MUTATING_GAME_SERVICE_TOOLS = frozenset(
    {
        "create_game",
        "attach_game",
        "delete_game",
        "get_game_state",
        "get_raw_game_state_games",
        "get_gui_update",
        "get_alerts",
        "get_session_actions",
        "list_game_options",
        "list_games",
        "list_actions",
        "list_card_providers",
        "lookup_session_by_slug",
        "export_game_state_snapshot",
        *MARVEL_LCG_CATALOG_TOOLS,
    }
)

# game-service MCP tools whose result/argument identifies a game session id,
# used to capture the canonical game_id for an agent session.
_GAME_ID_SOURCE_TOOLS = frozenset(
    {"create_game", "attach_game", "lookup_session_by_slug"}
)

# Single-session read results may carry their own id and can therefore be used
# to detect a result that disagrees with the call's target. ``list_games`` is
# intentionally excluded because it contains multiple session records.
_GAME_ID_RESULT_SOURCE_TOOLS = frozenset(
    {
        *_GAME_ID_SOURCE_TOOLS,
        "get_game_state",
        "get_session_actions",
        "list_game_options",
    }
)

# Read-only responses can identify the platform of an already-created game.  Keep
# this list explicit: a nested ``platform`` in an unrelated card or catalog result
# must not bind an agent session to a game platform.
_GAME_PLATFORM_SOURCE_TOOLS = frozenset(
    {
        *_GAME_ID_SOURCE_TOOLS,
        "get_game_state",
        "get_session_actions",
        "list_game_options",
        "list_games",
    }
)


def build_idempotency_key(game_id: str, actor: str, producer_offset: int | str) -> str:
    raw = f"{game_id}|{actor}|{producer_offset}".encode()
    return hashlib.sha256(raw).hexdigest()


def stamp_session_mode(payload: dict[str, Any], session_mode: str) -> None:
    """Record the emitting session's mode on an outgoing payload.

    **The key is omitted for ``chat``, not written as ``"chat"``.** The two
    options were weighed and this one was chosen deliberately:

    - There is then exactly ONE reader rule — *absent means chat* — and it covers
      both a session running in chat mode today and every event recorded before
      the mode existed. Writing ``"chat"`` explicitly would leave two shapes that
      mean the same thing, and a reader would still need the absent-key default
      for the historical rows, so nothing is actually simplified.
    - A chat event's stored payload stays byte-identical to what it was before
      orchestrated mode existed, so no consumer, export bundle, or recorded
      fixture shifts underneath this change. That is the "the addition changes no
      stored meaning" guarantee, kept at the level of the bytes rather than
      asserted about them.
    - It is also the more queryable of the two, contrary to first impressions.
      The question worth asking of the store is "which events came from
      orchestrated play", and ``payload ->> 'session_mode' = 'orchestrated'``
      answers it under either scheme. The complement,
      ``payload ->> 'session_mode' IS DISTINCT FROM 'orchestrated'``, correctly
      includes the pre-mode rows — whereas an ``= 'chat'`` predicate against an
      always-written key would silently miss every one of them.

    It also matches the ``player`` key immediately below, which is likewise
    absent rather than null when it does not apply.
    """
    if session_mode != SESSION_MODE_CHAT:
        payload["session_mode"] = session_mode


def is_game_mutating_tool(assignment: str | None, tool_name: str) -> bool:
    """Return True when a game-service MCP tool call mutates game state."""
    if assignment != "game-service":
        return False
    return tool_name not in _NON_MUTATING_GAME_SERVICE_TOOLS


def is_game_id_source_tool(assignment: str | None, tool_name: str) -> bool:
    return assignment == "game-service" and tool_name in _GAME_ID_SOURCE_TOOLS


def extract_game_id(
    *,
    assignment: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any] | None,
) -> str | None:
    """Best-effort extraction of the game-service session id (canonical game_id).

    Conservative by design: the session id is read from a tool *result* only
    for lifecycle tools and single-session reads whose result is an authoritative
    carrier. ``list_games`` is excluded because it contains multiple rows. For
    all other tools the id is taken solely from the call's own ``session_id``
    argument — never from arbitrary nested ids in an unrelated result payload
    (which could mis-attribute moves to a session the call never targeted).
    """
    if assignment != "game-service":
        return None

    result_id = extract_game_id_from_result(
        assignment=assignment,
        tool_name=tool_name,
        result=result,
    )
    if result_id is not None:
        return result_id
    return extract_game_id_from_arguments(
        assignment=assignment,
        arguments=arguments,
    )


def extract_game_id_from_arguments(
    *, assignment: str | None, arguments: dict[str, Any]
) -> str | None:
    if assignment != "game-service":
        return None
    argument_id = arguments.get("session_id")
    return argument_id if isinstance(argument_id, str) and argument_id else None


def extract_game_id_from_result(
    *, assignment: str | None, tool_name: str, result: dict[str, Any] | None
) -> str | None:
    if (
        assignment != "game-service"
        or result is None
        or tool_name not in _GAME_ID_RESULT_SOURCE_TOOLS
    ):
        return None
    return _game_id_from_result(result)


def extract_game_platform(
    *,
    assignment: str | None,
    tool_name: str,
    result: dict[str, Any] | None,
    arguments: dict[str, Any] | None = None,
    expected_game_id: str | None = None,
) -> str | None:
    """Extract a supported platform from a game-service result.

    Lifecycle responses have appeared both as a nested ``session`` object and
    as a flat session-shaped object. A state read may instead put the platform
    alongside ``session_id`` or inside ``state``. MCP may carry any shape as
    JSON text in ``content`` or as structured content, so the decoder accepts
    all of those equivalent representations.

    When a caller supplies an expected game id, only a matching session record is
    trusted. This matters for reads such as ``list_games`` that can describe more
    than one session. A missing or unsupported platform is deliberately returned
    as ``None``; callers then retain the legacy DragnCards default because there
    was no supported platform fact to bind.
    """
    if (
        result is None
        or assignment != "game-service"
        or tool_name not in _GAME_PLATFORM_SOURCE_TOOLS
    ):
        return None

    argument_id = extract_game_id_from_arguments(
        assignment=assignment,
        arguments=arguments or {},
    )
    result_id = extract_game_id_from_result(
        assignment=assignment,
        tool_name=tool_name,
        result=result,
    )
    if argument_id is not None and result_id is not None and argument_id != result_id:
        return None
    if expected_game_id is not None and (
        argument_id not in (None, expected_game_id)
        or result_id not in (None, expected_game_id)
    ):
        return None
    target_game_id = expected_game_id or argument_id or result_id
    for decoded in _decoded_result_values(result):
        session = _session_metadata_from_decoded(decoded)

        # ``list_games`` recursively yields both its outer response and each
        # session row.  A platform on a row is only useful when that row names
        # the session we are resolving; otherwise the first unrelated game's
        # platform could win through the flattened fallback below.  Without an
        # expected id, no list row is demonstrably associated with this session.
        if tool_name == "list_games" and (
            target_game_id is None
            or session is None
            or not _session_matches(session, target_game_id)
        ):
            continue

        if session is not None and _session_matches(session, target_game_id):
            platform = _supported_platform(session.get(SESSION_PLATFORM_KEY))
            if platform is not None:
                return platform

        # ``get_game_state`` responses commonly look like
        # ``{"session_id": ..., "state": {"platform": ...}}``. The state
        # itself is not session-shaped, so associate it with the enclosing id
        # (or with the read's session_id argument when the response omits it).
        state = decoded.get("state") if isinstance(decoded, dict) else None
        if isinstance(state, dict):
            enclosing_id = _session_id_from_decoded(decoded)
            if enclosing_id is None:
                enclosing_id = target_game_id
            if target_game_id is None or enclosing_id == target_game_id:
                platform = _supported_platform(state.get(SESSION_PLATFORM_KEY))
                if platform is not None:
                    return platform
                # The neutral game-state contract keeps ``pendingSeats`` only
                # for the enumerated-option platform. This lets an older
                # game-service state response identify marvel-lcg even before
                # its response model carries an explicit platform field.
                if tool_name == "get_game_state" and "pendingSeats" in state:
                    return PLATFORM_MARVEL_LCG

        if (
            tool_name == "get_session_actions"
            and isinstance(decoded, dict)
            and (session is None or _session_matches(session, target_game_id))
        ):
            plugin_metadata = decoded.get("plugin_metadata")
            if isinstance(plugin_metadata, dict):
                platform = _supported_platform(plugin_metadata.get("platform"))
                if platform is not None:
                    return platform
            if decoded.get("plugin_name") == PLATFORM_MARVEL_LCG:
                return PLATFORM_MARVEL_LCG

        # This operation is only exposed by the marvel-lcg move surface. A
        # successful response carrying its option list is therefore a read-only
        # platform fact even when the response model has no platform field.
        if (
            tool_name == "list_game_options"
            and isinstance(decoded, dict)
            and "options" in decoded
            and (session is None or _session_matches(session, target_game_id))
        ):
            return PLATFORM_MARVEL_LCG

        # Some state/read response models flatten ``platform`` beside the
        # state and omit ``session_id`` from the response. The tool argument is
        # still the authoritative target in that shape. If an id is present,
        # however, it must agree with that target; otherwise this fallback could
        # re-associate another game's platform with the current session.
        if target_game_id is not None and isinstance(decoded, dict):
            decoded_id = _session_id_from_decoded(decoded)
            if decoded_id is None or decoded_id == target_game_id:
                platform = _supported_platform(decoded.get(SESSION_PLATFORM_KEY))
                if platform is not None:
                    return platform
    return None


def _supported_platform(value: Any) -> str | None:
    if isinstance(value, str) and value in {DEFAULT_PLATFORM, PLATFORM_MARVEL_LCG}:
        return value
    return None


def _session_matches(session: dict[str, Any], expected_game_id: str | None) -> bool:
    if expected_game_id is None:
        return True
    return session.get("session_id") == expected_game_id


def _game_id_from_result(result: dict[str, Any]) -> str | None:
    for decoded in _decoded_result_values(result):
        candidate = _session_id_from_decoded(decoded)
        if candidate:
            return candidate
    return None


def _decoded_result_values(value: Any):
    """Yield dictionaries represented by the equivalent MCP result shapes."""
    pending: list[Any] = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            try:
                pending.append(json.loads(current))
            except TypeError, ValueError:
                continue
            continue
        if isinstance(current, dict):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            yield current
            pending.extend(current.values())
            continue
        if isinstance(current, list):
            pending.extend(current)


def _session_metadata_from_decoded(decoded: Any) -> dict[str, Any] | None:
    if not isinstance(decoded, dict):
        return None
    session = decoded.get("session")
    if isinstance(session, dict):
        return session
    if "session_id" in decoded:
        return decoded
    return None


def _session_id_from_decoded(decoded: Any) -> str | None:
    session = _session_metadata_from_decoded(decoded)
    if session is None:
        return None
    session_id = session.get("session_id")
    if isinstance(session_id, str) and session_id:
        return session_id
    return None


class HistoryEventBus(Protocol):
    async def publish(self, envelope: dict[str, Any]) -> None: ...

    async def next_producer_offset(self, game_id: str) -> int: ...

    async def aclose(self) -> None: ...


class InMemoryHistoryEventBus:
    """In-process history bus for tests and local fallback."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._offsets: dict[str, int] = {}

    async def publish(self, envelope: dict[str, Any]) -> None:
        self.events.append(envelope)

    async def next_producer_offset(self, game_id: str) -> int:
        nxt = self._offsets.get(game_id, 0) + 1
        self._offsets[game_id] = nxt
        return nxt

    async def aclose(self) -> None:
        return None


class ValkeyHistoryEventBus:
    """Publishes history envelopes to the shared ``history:ingest`` Valkey stream."""

    def __init__(
        self,
        url: str,
        *,
        stream_key: str = "history:ingest",
        max_stream_length: int = 100_000,
        offset_key_prefix: str = "agent-orchestrator:history-offset:",
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        self._stream_key = stream_key
        self._max_stream_length = max_stream_length
        self._offset_key_prefix = offset_key_prefix
        self._conn = RespConnection(parsed.hostname or "localhost", parsed.port or 6379)
        logger.info(
            "Configured Valkey history event bus stream=%s maxlen=%s",
            stream_key,
            max_stream_length,
        )

    async def next_producer_offset(self, game_id: str) -> int:
        value = await self._conn.execute("INCR", f"{self._offset_key_prefix}{game_id}")
        return int(value)

    async def publish(self, envelope: dict[str, Any]) -> None:
        await self._conn.execute(
            "XADD",
            self._stream_key,
            "MAXLEN",
            "~",
            str(self._max_stream_length),
            "*",
            "envelope_json",
            json.dumps(envelope),
        )

    async def aclose(self) -> None:
        await self._conn.aclose()


class HistoryEventEmitter:
    """Builds and emits agent move/decision envelopes to the history bus.

    Emission is best-effort: a publish failure is logged and swallowed so it can
    never break a prompt job's tool round.

    Ordering: emissions are fired as detached tasks so they never block a tool
    round, but the offset-assignment (``next_producer_offset``) and the publish
    (``bus.publish``) of a single event MUST NOT interleave with another
    emission's — the history-service assigns each game's authoritative ``seq``
    by stream arrival order, so if a later-offset event reached the stream first
    the durable timeline would be reordered (e.g. a move recorded before the
    ``user_prompt`` that produced it). A per-emitter async lock makes the
    offset-then-publish pair a single critical section, so within a worker
    process events for a game reach the stream in the same order their offsets
    were assigned.
    """

    def __init__(self, *, bus: HistoryEventBus, enabled: bool = True) -> None:
        self._bus = bus
        self._enabled = enabled
        self._publish_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def emit_agent_move(
        self,
        *,
        game_id: str,
        intended_action: str,
        reasoning: str,
        arguments: dict[str, Any],
        conversation_context: list[dict[str, Any]],
        event_type: str = "agent_move",
        player: str | None = None,
        session_mode: str = SESSION_MODE_CHAT,
        platform: str = DEFAULT_PLATFORM,
        marvel_lcg_option: MarvelLcgOptionIdentity | None = None,
    ) -> dict[str, Any] | None:
        """Build and publish an agent move/decision envelope. Best-effort.

        For a Marvel LCG choice, ``marvel_lcg_option`` is the additive payload
        field with the exact shape ``{"id", "name", "event"}``. The prompt
        runtime supplies it only after matching a successful
        ``list_game_options`` result; the option id in the submitted arguments
        is not enough to populate this field.
        """
        if not self._enabled:
            return None
        try:
            # Assign the offset and publish under one lock so concurrent
            # emissions reach the stream in offset order (see class docstring).
            async with self._publish_lock:
                producer_offset = await self._bus.next_producer_offset(game_id)
                envelope = self.build_envelope(
                    game_id=game_id,
                    intended_action=intended_action,
                    reasoning=reasoning,
                    arguments=arguments,
                    conversation_context=conversation_context,
                    producer_offset=producer_offset,
                    event_type=event_type,
                    player=player,
                    session_mode=session_mode,
                    platform=platform,
                    marvel_lcg_option=marvel_lcg_option,
                )
                await self._bus.publish(envelope)
            return envelope
        except Exception:
            logger.warning(
                "Failed to emit history event for game %s (continuing)",
                game_id,
                exc_info=True,
            )
            return None

    async def emit_user_prompt(
        self,
        *,
        game_id: str,
        prompt: str,
        session_mode: str = SESSION_MODE_CHAT,
        platform: str = DEFAULT_PLATFORM,
    ) -> dict[str, Any] | None:
        """Build and publish a ``user_prompt`` envelope. Best-effort.

        Records the prompt text that triggered an agent turn so the history
        timeline can show what the user asked for, inline with the moves it
        produced. Uses the same game_id + producer-offset envelope mechanism as
        :meth:`emit_agent_move`.

        The mode travels on this event too: a prompt given to an orchestrated
        session is as much a part of that timeline as the moves it caused, and a
        consumer reading a span should not have to reach for a neighbouring move
        to learn which kind of play it is looking at.
        """
        if not self._enabled:
            return None
        try:
            # Assign the offset and publish under one lock so concurrent
            # emissions reach the stream in offset order (see class docstring).
            async with self._publish_lock:
                producer_offset = await self._bus.next_producer_offset(game_id)
                envelope = self.build_user_prompt_envelope(
                    game_id=game_id,
                    prompt=prompt,
                    producer_offset=producer_offset,
                    session_mode=session_mode,
                    platform=platform,
                )
                await self._bus.publish(envelope)
            return envelope
        except Exception:
            logger.warning(
                "Failed to emit user_prompt history event for game %s (continuing)",
                game_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def build_envelope(
        *,
        game_id: str,
        intended_action: str,
        reasoning: str,
        arguments: dict[str, Any],
        conversation_context: list[dict[str, Any]],
        producer_offset: int | str,
        event_type: str = "agent_move",
        player: str | None = None,
        session_mode: str = SESSION_MODE_CHAT,
        platform: str = DEFAULT_PLATFORM,
        marvel_lcg_option: MarvelLcgOptionIdentity | None = None,
    ) -> dict[str, Any]:
        # ``player`` names the seat that made this move in a multi-player
        # orchestrated game. It is omitted entirely for moves that belong to no
        # seat (the orchestrator's own phase and villain automation) so
        # downstream consumers can tell "seat unknown" from "no seat".
        #
        # ``marvel_lcg_option`` is deliberately separate from ``arguments``: it
        # is producer-confirmed option metadata for the evaluator, not a second
        # model-authored representation of the choice.
        #
        # The mode and the seat are independent, and the combination is what makes
        # the orchestrator's own bookkeeping legible: an orchestrated event with
        # no ``player`` is the coordinating agent acting for the table, which is a
        # different thing from a seat's play and must not be attributed to one.
        resolved_platform = normalize_platform(platform)
        payload: dict[str, Any] = {
            "intended_action": intended_action,
            "reasoning": reasoning,
            "arguments": arguments,
            "conversation_context": conversation_context,
        }
        stamp_session_mode(payload, session_mode)
        if marvel_lcg_option is not None and resolved_platform == PLATFORM_MARVEL_LCG:
            payload[MARVEL_LCG_OPTION_PAYLOAD_KEY] = marvel_lcg_option
        if player:
            payload["player"] = player
        return {
            "envelope_version": ENVELOPE_VERSION,
            "event_id": str(uuid4()),
            "game_id": game_id,
            "platform": resolved_platform,
            "actor": HISTORY_ACTOR_AGENT,
            "event_type": event_type,
            "payload": payload,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": build_idempotency_key(
                game_id, HISTORY_ACTOR_AGENT, producer_offset
            ),
            "producer_offset": producer_offset,
        }

    @staticmethod
    def build_user_prompt_envelope(
        *,
        game_id: str,
        prompt: str,
        producer_offset: int | str,
        session_mode: str = SESSION_MODE_CHAT,
        platform: str = DEFAULT_PLATFORM,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"prompt": prompt}
        stamp_session_mode(payload, session_mode)
        return {
            "envelope_version": ENVELOPE_VERSION,
            "event_id": str(uuid4()),
            "game_id": game_id,
            "platform": normalize_platform(platform),
            "actor": HISTORY_ACTOR_USER,
            "event_type": "user_prompt",
            "payload": payload,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": build_idempotency_key(
                game_id, HISTORY_ACTOR_USER, producer_offset
            ),
            "producer_offset": producer_offset,
        }

    async def emit_illegal_action(
        self,
        *,
        game_id: str,
        player: str,
        violation: str,
        required_undo: str,
        status: str = ILLEGAL_ACTION_STATUS_OPEN,
        resolution_note: str | None = None,
        round_number: int | None = None,
        platform: str = DEFAULT_PLATFORM,
    ) -> dict[str, Any] | None:
        """Build and publish an ``illegal_action`` finding envelope. Best-effort.

        A finding is the orchestrator's own record that a seat's action broke the
        rules, written into the durable timeline so the judge is given it as
        recorded evidence instead of having to re-derive a violation from the move
        list. It is emitted whether it is still ``open`` or already ``resolved``,
        because "the seat undid it" is itself part of the record.

        It rides on the ``agent`` actor (see
        :data:`HISTORY_EVENT_TYPE_ILLEGAL_ACTION`) and carries no
        ``conversation_context``: a finding is a decision the orchestrator made
        about game state, not a turn of a conversation, and nothing downstream
        grades it as a move.
        """
        if not self._enabled:
            return None
        try:
            # Assign the offset and publish under one lock so concurrent
            # emissions reach the stream in offset order (see class docstring).
            async with self._publish_lock:
                producer_offset = await self._bus.next_producer_offset(game_id)
                envelope = self.build_illegal_action_envelope(
                    game_id=game_id,
                    player=player,
                    violation=violation,
                    required_undo=required_undo,
                    status=status,
                    resolution_note=resolution_note,
                    round_number=round_number,
                    producer_offset=producer_offset,
                    platform=platform,
                )
                await self._bus.publish(envelope)
            return envelope
        except Exception:
            logger.warning(
                "Failed to emit illegal_action history event for game %s (continuing)",
                game_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def build_illegal_action_envelope(
        *,
        game_id: str,
        player: str,
        violation: str,
        required_undo: str,
        producer_offset: int | str,
        status: str = ILLEGAL_ACTION_STATUS_OPEN,
        resolution_note: str | None = None,
        round_number: int | None = None,
        platform: str = DEFAULT_PLATFORM,
    ) -> dict[str, Any]:
        # A finding always names a seat — an action with no seat has no seat to
        # hold responsible — so ``player`` is required here rather than optional as
        # it is on a move. The mode is always ``orchestrated`` for the same reason:
        # only an orchestrated session has seats and a coordinator to judge them,
        # so the mode is stated rather than taken as an argument.
        payload: dict[str, Any] = {
            "player": player,
            "violation": violation,
            "required_undo": required_undo,
            "status": status,
            "session_mode": SESSION_MODE_ORCHESTRATED,
        }
        if resolution_note is not None:
            payload["resolution_note"] = resolution_note
        if round_number is not None:
            payload["round_number"] = round_number
        return {
            "envelope_version": ENVELOPE_VERSION,
            "event_id": str(uuid4()),
            "game_id": game_id,
            "platform": normalize_platform(platform),
            "actor": HISTORY_ACTOR_AGENT,
            "event_type": HISTORY_EVENT_TYPE_ILLEGAL_ACTION,
            "payload": payload,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": build_idempotency_key(
                game_id, HISTORY_ACTOR_AGENT, producer_offset
            ),
            "producer_offset": producer_offset,
        }
