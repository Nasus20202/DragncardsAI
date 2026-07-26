"""History ingestion emitter.

The game-service is a *producer* for the history-service event log. After each
executed game action it publishes a versioned envelope describing the resulting
game state and status onto the shared Valkey stream ``history:ingest``.

Emission is strictly best-effort: it must never change the action result
returned to the caller and must never break action execution. Any failure to
publish is logged and swallowed. Emission can be disabled entirely via
``HISTORY_INGEST_ENABLED=false``.

The envelope shape is the shared cross-service contract (see the
``history-event-store`` OpenSpec change, design.md). This producer fills the
fields it owns and deliberately leaves ``seq``/``recorded_at`` for the
history-service to assign at commit time.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

from game_service.coordination.session_store import _RespConnection
from game_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

#: Shared Valkey stream key consumed by the history-service consumer group.
HISTORY_INGEST_STREAM = "history:ingest"

#: Stream field carrying the JSON-encoded envelope. MUST match the field name
#: the history-service ingester reads and the agent-orchestrator producer writes.
ENVELOPE_FIELD = "envelope_json"

#: Generic game-service action endpoint suffix used to replay a recorded action
#: forward: ``POST /games/{id}/actions`` with the serialized action body.
GENERIC_ACTION_PATH = "actions"

#: Envelope contract version. Bump when the shape changes incompatibly.
ENVELOPE_VERSION = 1

#: Actor identity stamped on every event this service emits.
ACTOR = "game-service"

#: Valkey key prefix for the durable per-game producer offset. Lives on the
#: shared history Valkey (HISTORY_VALKEY_URL), mirroring the agent-orchestrator
#: ``agent-orchestrator:history-offset:{game_id}`` counter so a session restore
#: or service restart never regenerates a previously used idempotency key.
OFFSET_KEY_PREFIX = "game-service:history-offset:"

#: Event type for a post-action game-state/status observation.
EVENT_TYPE_STATE = "game_state"


def _game_status(state: Any) -> str:
    """Extract the game status (``mode``) from a raw DragnCards state payload.

    DragnCards stores status as ``game["mode"]`` (``unknown`` / ``in progress``
    / ``win`` / ``loss``). Returns ``"unknown"`` when the payload is missing or
    malformed so the envelope always carries a status string.
    """
    if isinstance(state, dict):
        game = state.get("game")
        if isinstance(game, dict):
            mode = game.get("mode")
            if isinstance(mode, str) and mode:
                return mode
    return "unknown"


def _state_digest(state: Any) -> str:
    """Return a stable content digest of the resulting game state.

    The digest lets the history-service detect divergence cheaply without
    diffing the full payload, while the full representation is still carried in
    the payload for restore/replay.
    """
    try:
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
    except TypeError, ValueError:
        canonical = repr(state)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_key(game_id: str, actor: str, producer_offset: int) -> str:
    """Stable hash of ``(game_id, actor, producer_offset)``.

    The history-service dedupes inbound duplicates on
    ``(game_id, idempotency_key)`` under at-least-once delivery, so this MUST be
    deterministic for a given action emission.
    """
    raw = f"{game_id}\x00{actor}\x00{producer_offset}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_state_envelope(
    *,
    game_id: str,
    producer_offset: int,
    state: Any,
    action_args: dict[str, Any] | None = None,
    plugin_name: str | None = None,
) -> dict[str, Any]:
    """Build the history envelope for a post-action state observation.

    Only the fields this producer owns are populated. ``seq`` and
    ``recorded_at`` are intentionally omitted: the history-service assigns them
    authoritatively at commit time.

    When ``action_args`` is supplied it is a JSON-serializable representation of
    the executed action (the body accepted by ``POST /games/{id}/actions``). It
    is carried alongside the resulting ``state`` so the history-service can
    replay the event forward via the generic action endpoint
    (``action_path``/``action_args``). Events without a replayable action are
    skipped during restore replay.

    ``plugin_name`` is the session's plugin slug. It is recorded on every state
    event so a branchable ("new") restore can materialize a fresh session even
    when no snapshot has been taken yet (short games): the slug is the only
    game-service input needed to create the branch room before forward replay.
    """
    payload: dict[str, Any] = {
        "state": state,
        "state_digest": _state_digest(state),
        "status": _game_status(state),
    }
    if plugin_name:
        payload["plugin_name"] = plugin_name
    if action_args is not None:
        payload["action_path"] = GENERIC_ACTION_PATH
        payload["action_args"] = action_args
    return {
        "envelope_version": ENVELOPE_VERSION,
        "event_id": str(uuid.uuid4()),
        "game_id": game_id,
        "actor": ACTOR,
        "event_type": EVENT_TYPE_STATE,
        "payload": payload,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": _idempotency_key(game_id, ACTOR, producer_offset),
        "producer_offset": producer_offset,
    }


class HistoryEmitter(Protocol):
    async def next_producer_offset(self, game_id: str) -> int | None: ...

    async def emit_state_event(
        self,
        *,
        game_id: str,
        producer_offset: int,
        state: Any,
        action_args: dict[str, Any] | None = None,
        plugin_name: str | None = None,
    ) -> None: ...


class NullHistoryEmitter:
    """No-op emitter used when history ingestion is disabled."""

    async def next_producer_offset(self, game_id: str) -> int | None:
        return None

    async def emit_state_event(
        self,
        *,
        game_id: str,
        producer_offset: int,
        state: Any,
        action_args: dict[str, Any] | None = None,
        plugin_name: str | None = None,
    ) -> None:
        return None


class ValkeyHistoryEmitter:
    """Publishes history envelopes to the shared Valkey ``history:ingest`` stream.

    All publishing is best-effort: any error is logged and swallowed so action
    execution is never affected.
    """

    def __init__(
        self,
        url: str,
        *,
        stream_key: str = HISTORY_INGEST_STREAM,
        maxlen: int | None = 100_000,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 6379
        self._stream_key = stream_key
        self._maxlen = maxlen
        self._offset_key_prefix = OFFSET_KEY_PREFIX
        self._conn = _RespConnection(self._host, self._port)

    async def next_producer_offset(self, game_id: str) -> int | None:
        """Atomically allocate the next durable per-game producer offset.

        Sourced from a Valkey ``INCR`` on the shared history Valkey so the
        offset survives session restore and service restarts. Returns ``None``
        on failure; callers must then skip emission rather than fabricate a
        non-durable offset (which would collide with a future durable one).
        """
        try:
            value = await self._conn.execute(
                "INCR", f"{self._offset_key_prefix}{game_id}"
            )
            return int(value)
        except Exception as exc:  # best-effort: never break the action
            logger.warning(
                "history emit: INCR offset failed for game %s: %s", game_id, exc
            )
            return None

    async def emit_state_event(
        self,
        *,
        game_id: str,
        producer_offset: int,
        state: Any,
        action_args: dict[str, Any] | None = None,
        plugin_name: str | None = None,
    ) -> None:
        envelope = build_state_envelope(
            game_id=game_id,
            producer_offset=producer_offset,
            state=state,
            action_args=action_args,
            plugin_name=plugin_name,
        )
        await self._publish(envelope)

    async def _publish(self, envelope: dict[str, Any]) -> None:
        try:
            payload = json.dumps(envelope, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            logger.warning(
                "history emit: failed to serialize envelope for game %s: %s",
                envelope.get("game_id"),
                exc,
            )
            return

        args: list[str] = ["XADD", self._stream_key]
        if self._maxlen is not None:
            # Approximate trimming keeps the transport bounded; PostgreSQL is the
            # durable record on the consumer side.
            args += ["MAXLEN", "~", str(self._maxlen)]
        args += ["*", ENVELOPE_FIELD, payload]

        try:
            with tracer.start_as_current_span(
                "history.emit_state_event",
                attributes={
                    "db.system": "redis",
                    "db.operation.name": "XADD",
                    "history.stream": self._stream_key,
                    "game.id": envelope.get("game_id"),
                },
            ):
                await self._conn.execute(*args)
        except Exception as exc:  # best-effort: never break the action
            logger.warning(
                "history emit: XADD to %s failed for game %s: %s",
                self._stream_key,
                envelope.get("game_id"),
                exc,
            )


def build_history_emitter(*, enabled: bool, valkey_url: str | None) -> HistoryEmitter:
    """Construct the configured emitter.

    Returns a :class:`NullHistoryEmitter` when ingestion is disabled or when no
    Valkey URL is available, so callers can always emit unconditionally.
    """
    if not enabled or not valkey_url:
        return NullHistoryEmitter()
    try:
        return ValkeyHistoryEmitter(valkey_url)
    except ValueError as exc:
        logger.warning(
            "history emit: disabling emitter, invalid Valkey URL %r: %s",
            valkey_url,
            exc,
        )
        return NullHistoryEmitter()
