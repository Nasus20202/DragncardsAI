from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from agent_orchestrator.storage.valkey import RespConnection
from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

ENVELOPE_VERSION = 1
HISTORY_ACTOR_AGENT = "agent"
HISTORY_ACTOR_USER = "user"

# Keys used inside AgentSession.metadata_json to carry history-related state.
SESSION_GAME_ID_KEY = "game_id"
SESSION_RESTORED_CONTEXT_KEY = "restored_conversation_context"

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
        "list_games",
        "list_actions",
        "list_card_providers",
        "lookup_session_by_slug",
        "export_game_state_snapshot",
    }
)

# game-service MCP tools whose result/argument identifies a game session id,
# used to capture the canonical game_id for an agent session.
_GAME_ID_SOURCE_TOOLS = frozenset(
    {"create_game", "attach_game", "lookup_session_by_slug"}
)


def build_idempotency_key(game_id: str, actor: str, producer_offset: int | str) -> str:
    raw = f"{game_id}|{actor}|{producer_offset}".encode()
    return hashlib.sha256(raw).hexdigest()


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

    Conservative by design: the session id is only read from a tool *result*
    body for the create/attach/lookup lifecycle tools (``_GAME_ID_SOURCE_TOOLS``)
    whose result is the authoritative carrier of a session id. For every other
    game-service tool the id is taken solely from the call's own ``session_id``
    argument — never from arbitrary nested ids in an unrelated result payload
    (which could mis-attribute moves to a session the call never targeted).
    """
    if assignment != "game-service":
        return None

    # Only lifecycle tools' results are trusted to name a session id.
    if result is not None and tool_name in _GAME_ID_SOURCE_TOOLS:
        candidate = _game_id_from_result(result)
        if candidate:
            return candidate

    argument_id = arguments.get("session_id")
    if isinstance(argument_id, str) and argument_id:
        return argument_id
    return None


def _game_id_from_result(result: dict[str, Any]) -> str | None:
    content = result.get("content")
    if not isinstance(content, list):
        return None
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        try:
            decoded = json.loads(text)
        except ValueError:
            continue
        candidate = _session_id_from_decoded(decoded)
        if candidate:
            return candidate
    return None


def _session_id_from_decoded(decoded: Any) -> str | None:
    if not isinstance(decoded, dict):
        return None
    session = decoded.get("session")
    if isinstance(session, dict):
        session_id = session.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
    session_id = decoded.get("session_id")
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
    ) -> dict[str, Any] | None:
        """Build and publish an agent move/decision envelope. Best-effort."""
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
    ) -> dict[str, Any] | None:
        """Build and publish a ``user_prompt`` envelope. Best-effort.

        Records the prompt text that triggered an agent turn so the history
        timeline can show what the user asked for, inline with the moves it
        produced. Uses the same game_id + producer-offset envelope mechanism as
        :meth:`emit_agent_move`.
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
    ) -> dict[str, Any]:
        # ``player`` names the seat that made this move in a multi-player
        # orchestrated game. It is omitted entirely for moves that belong to no
        # seat (the orchestrator's own phase and villain automation) so
        # downstream consumers can tell "seat unknown" from "no seat".
        payload: dict[str, Any] = {
            "intended_action": intended_action,
            "reasoning": reasoning,
            "arguments": arguments,
            "conversation_context": conversation_context,
        }
        if player:
            payload["player"] = player
        return {
            "envelope_version": ENVELOPE_VERSION,
            "event_id": str(uuid4()),
            "game_id": game_id,
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
    ) -> dict[str, Any]:
        return {
            "envelope_version": ENVELOPE_VERSION,
            "event_id": str(uuid4()),
            "game_id": game_id,
            "actor": HISTORY_ACTOR_USER,
            "event_type": "user_prompt",
            "payload": {"prompt": prompt},
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": build_idempotency_key(
                game_id, HISTORY_ACTOR_USER, producer_offset
            ),
            "producer_offset": producer_offset,
        }
