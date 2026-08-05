from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Any, Protocol
from urllib.parse import urlparse

from agent_orchestrator.storage.valkey import RespConnection
from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# How many stream entries one ``XREAD`` may return. A streaming model publishes
# one live event per token, so a consumer that took a single entry per command
# would match the producer's command rate one for one. Reading a batch keeps the
# consumer's Valkey traffic proportional to bursts rather than to tokens, while
# staying well below the per-job stream cap so no single reply is unbounded.
DEFAULT_READ_BATCH_SIZE = 64


@dataclass(frozen=True)
class LiveJobEvent:
    id: str
    event_type: str
    payload_json: dict[str, Any]
    created_at: datetime
    #: The ``job_events.id`` of the durable row this is the live copy of, when
    #: the publisher had already persisted one.
    #:
    #: Nearly every publish is preceded by an ``append_event``, and the SSE
    #: stream serves both sources: it polls ``list_events`` *and* forwards this
    #: bus. Without this field the two copies reach the browser under two
    #: unrelated ids — a Postgres integer and a Valkey stream id — and the
    #: client's id-keyed de-duplication cannot tell they are one event, so the
    #: transcript renders the row twice (DRA-34). Carrying the durable id lets
    #: the stream label the live copy with it so the two collapse.
    durable_event_id: str | None = None


class LiveEventSubscriber(Protocol):
    async def get(self, timeout_seconds: float) -> LiveJobEvent | None: ...

    async def aclose(self) -> None: ...


class LiveEventBus(Protocol):
    #: ``None`` means the event never reached the bus. Publishing is best-effort
    #: by design — see ``BestEffortLiveEventBus``, which every consumer in the
    #: running service is handed: the durable ``job_events`` row written before
    #: the publish is the source of truth, and the SSE stream polls it. Callers
    #: are not expected to read this value, and none in this service do.
    async def publish(
        self,
        job_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        *,
        durable_event_id: int | str | None = None,
    ) -> LiveJobEvent | None: ...

    async def subscribe(self, job_id: str) -> LiveEventSubscriber: ...

    async def aclose(self) -> None: ...


class InMemoryLiveEventSubscriber:
    def __init__(
        self,
        job_id: str,
        queue: asyncio.Queue[LiveJobEvent],
        bus: "InMemoryLiveEventBus",
    ):
        self._job_id = job_id
        self._queue = queue
        self._bus = bus

    async def get(self, timeout_seconds: float) -> LiveJobEvent | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_seconds)
        except TimeoutError:
            return None

    async def aclose(self) -> None:
        self._bus.unsubscribe(self._job_id, self._queue)


class InMemoryLiveEventBus:
    def __init__(self, replay_buffer_size: int = 512):
        self._next_id = count(start=1_000_000_000)
        self._subscribers: dict[str, set[asyncio.Queue[LiveJobEvent]]] = defaultdict(
            set
        )
        self._replay: dict[str, deque[LiveJobEvent]] = defaultdict(
            lambda: deque(maxlen=replay_buffer_size)
        )

    async def publish(
        self,
        job_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        *,
        durable_event_id: int | str | None = None,
    ) -> LiveJobEvent:
        event = LiveJobEvent(
            id=str(next(self._next_id)),
            event_type=event_type,
            payload_json=payload_json,
            created_at=datetime.now(timezone.utc),
            durable_event_id=(
                None if durable_event_id is None else str(durable_event_id)
            ),
        )
        self._replay[job_id].append(event)
        for queue in tuple(self._subscribers[job_id]):
            queue.put_nowait(event)
        return event

    async def subscribe(self, job_id: str) -> InMemoryLiveEventSubscriber:
        queue: asyncio.Queue[LiveJobEvent] = asyncio.Queue()
        # Replay buffered events so late subscribers catch up
        for event in self._replay[job_id]:
            queue.put_nowait(event)
        self._subscribers[job_id].add(queue)
        return InMemoryLiveEventSubscriber(job_id, queue, self)

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[LiveJobEvent]) -> None:
        subscribers = self._subscribers.get(job_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    async def aclose(self) -> None:
        logger.info("Closing in-memory live event bus")
        return None


def _decode_entry(entry_id: str, fields: list[str]) -> LiveJobEvent:
    payload = {fields[index]: fields[index + 1] for index in range(0, len(fields), 2)}
    return LiveJobEvent(
        id=entry_id,
        event_type=payload["event_type"],
        payload_json=json.loads(payload["payload_json"]),
        created_at=datetime.fromisoformat(payload["created_at"]),
        # Absent on entries written before this field existed, and on
        # publishes that persist nothing of their own.
        durable_event_id=payload.get("durable_event_id") or None,
    )


class ValkeyLiveEventSubscriber:
    """Reads one job's live-event stream, a batch of entries per round trip.

    ``get`` hands back a single event because that is what every caller wants,
    but reading one entry per ``XREAD`` would put a whole Valkey command — and,
    with the per-command RESP client, a whole TCP connection — behind every
    event delivered. A streaming model emits one event per token, so the
    consumer would issue as many commands as the producer. Each ``XREAD``
    therefore asks for up to ``batch_size`` entries and the surplus is held in
    ``_pending`` until ``get`` is asked for them.

    ``_pending`` is per-subscriber, and a subscriber lives for exactly one SSE
    request or one subagent wait, so this is a request-scoped buffer of entries
    already taken off the stream — not process-lifetime cached state. It holds
    at most ``batch_size`` entries.
    """

    def __init__(
        self,
        connection: RespConnection,
        stream_key: str,
        last_id: str = "0-0",
        *,
        batch_size: int = DEFAULT_READ_BATCH_SIZE,
    ):
        self._conn = connection
        self._stream_key = stream_key
        self._last_id = last_id
        self._batch_size = max(1, batch_size)
        self._pending: deque[LiveJobEvent] = deque()

    async def get(self, timeout_seconds: float) -> LiveJobEvent | None:
        # Entries already fetched are handed out without touching Valkey. The
        # caller asked to wait *up to* this long for the next event, and the
        # next event is already here.
        if self._pending:
            return self._pending.popleft()

        block_ms = max(1, int(timeout_seconds * 1000))
        response = await self._conn.execute(
            "XREAD",
            "BLOCK",
            str(block_ms),
            "COUNT",
            str(self._batch_size),
            "STREAMS",
            self._stream_key,
            self._last_id,
        )
        if not response:
            return None
        _, entries = response[0]
        for entry_id, fields in entries:
            self._last_id = entry_id
            self._pending.append(_decode_entry(entry_id, fields))
        if not self._pending:
            return None
        return self._pending.popleft()

    async def aclose(self) -> None:
        self._pending.clear()
        return None


# Appends one live event and refreshes the stream's TTL in a single round trip.
# The TTL has to be re-armed on every append: a job that publishes nothing for
# longer than the TTL would otherwise lose its stream mid-run, and the next
# append would recreate the key with no expiry at all and leak it.
# ARGV[1] is the stream cap and ARGV[2] the TTL; everything from ARGV[3] on is
# the event's field/value pairs, passed through verbatim so an optional field
# (`durable_event_id`) needs no second script and no branch here.
_PUBLISH_SCRIPT = """
local fields = {'XADD', KEYS[1], 'MAXLEN', '~', ARGV[1], '*'}
for index = 3, #ARGV do
  fields[#fields + 1] = ARGV[index]
end
local id = redis.call(unpack(fields))
redis.call('EXPIRE', KEYS[1], ARGV[2])
return id
"""


class ValkeyLiveEventBus:
    def __init__(
        self,
        url: str,
        *,
        stream_prefix: str = "agent-orchestrator:live-events:",
        max_stream_length: int = 512,
        event_ttl_seconds: int = 300,
        read_batch_size: int = DEFAULT_READ_BATCH_SIZE,
    ):
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 6379
        self._stream_prefix = stream_prefix
        self._max_stream_length = max_stream_length
        self._event_ttl_seconds = event_ttl_seconds
        self._read_batch_size = read_batch_size
        self._conn = RespConnection(self._host, self._port)
        logger.info(
            "Configured Valkey live event bus at %s:%s stream_prefix=%s ttl=%ss",
            self._host,
            self._port,
            self._stream_prefix,
            self._event_ttl_seconds,
        )

    def _stream_key(self, job_id: str) -> str:
        return f"{self._stream_prefix}{job_id}"

    async def publish(
        self,
        job_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        *,
        durable_event_id: int | str | None = None,
    ) -> LiveJobEvent:
        created_at = datetime.now(timezone.utc)
        stream_key = self._stream_key(job_id)
        # Kept out of `payload_json` on purpose: the payload is forwarded to the
        # browser verbatim, and this is stream plumbing rather than event data.
        fields = [
            "event_type",
            event_type,
            "payload_json",
            json.dumps(payload_json),
            "created_at",
            created_at.isoformat(),
        ]
        if durable_event_id is not None:
            fields += ["durable_event_id", str(durable_event_id)]
        # One round trip, not two. A streaming model publishes an event per
        # token, so an `EXPIRE` issued as its own command doubled the Valkey
        # commands, the TCP connections and the spans of the busiest path in the
        # service. The script performs exactly the append and the TTL refresh
        # the two commands performed, in the same order, and returns the same
        # entry id `XADD` returned.
        #
        # This is also why there is no partial-failure branch here. DRA-42 had to
        # tolerate a reset arriving between the append and the TTL refresh, since
        # that reset aborted a publish whose event was already in the stream. One
        # atomic command has no "between": it either appends and refreshes or
        # does neither, and either way the caller's best-effort wrapper decides
        # what a failure means.
        event_id = await self._conn.execute(
            "EVAL",
            _PUBLISH_SCRIPT,
            "1",
            stream_key,
            str(self._max_stream_length),
            str(self._event_ttl_seconds),
            *fields,
        )
        return LiveJobEvent(
            id=str(event_id),
            event_type=event_type,
            payload_json=payload_json,
            created_at=created_at,
            durable_event_id=(
                None if durable_event_id is None else str(durable_event_id)
            ),
        )

    async def subscribe(self, job_id: str) -> ValkeyLiveEventSubscriber:
        return ValkeyLiveEventSubscriber(
            self._conn, self._stream_key(job_id), batch_size=self._read_batch_size
        )

    async def aclose(self) -> None:
        logger.info("Closing Valkey live event bus")
        return None
