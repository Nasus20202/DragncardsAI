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

from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


@dataclass(frozen=True)
class LiveJobEvent:
    id: str
    event_type: str
    payload_json: dict[str, Any]
    created_at: datetime


class LiveEventSubscriber(Protocol):
    async def get(self, timeout_seconds: float) -> LiveJobEvent | None: ...

    async def aclose(self) -> None: ...


class LiveEventBus(Protocol):
    async def publish(
        self, job_id: str, event_type: str, payload_json: dict[str, Any]
    ) -> LiveJobEvent: ...

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
        self, job_id: str, event_type: str, payload_json: dict[str, Any]
    ) -> LiveJobEvent:
        event = LiveJobEvent(
            id=str(next(self._next_id)),
            event_type=event_type,
            payload_json=payload_json,
            created_at=datetime.now(timezone.utc),
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


class _RespError(RuntimeError):
    pass


def _encode_resp_array(parts: list[str]) -> bytes:
    payload = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        data = part.encode()
        payload.append(f"${len(data)}\r\n".encode())
        payload.append(data)
        payload.append(b"\r\n")
    return b"".join(payload)


async def _read_line(reader: asyncio.StreamReader) -> bytes:
    line = await reader.readline()
    if not line:
        raise _RespError("unexpected EOF from Valkey")
    return line[:-2]


async def _read_resp(reader: asyncio.StreamReader) -> Any:
    prefix = await reader.readexactly(1)
    if prefix == b"+":
        return (await _read_line(reader)).decode()
    if prefix == b":":
        return int((await _read_line(reader)).decode())
    if prefix == b"$":
        length = int((await _read_line(reader)).decode())
        if length == -1:
            return None
        data = await reader.readexactly(length)
        await reader.readexactly(2)
        return data.decode()
    if prefix == b"*":
        length = int((await _read_line(reader)).decode())
        if length == -1:
            return None
        return [await _read_resp(reader) for _ in range(length)]
    if prefix == b"-":
        raise _RespError((await _read_line(reader)).decode())
    raise _RespError(f"unknown RESP prefix: {prefix!r}")


class _RespConnection:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port

    async def execute(self, *parts: object) -> Any:
        command = str(parts[0]).upper() if parts else "UNKNOWN"
        with tracer.start_as_current_span(
            "valkey.live_events.execute",
            attributes={
                "db.system": "redis",
                "db.operation.name": command,
                "server.address": self._host,
                "server.port": self._port,
            },
        ):
            reader, writer = await asyncio.open_connection(self._host, self._port)
            try:
                writer.write(_encode_resp_array([str(part) for part in parts]))
                await writer.drain()
                return await _read_resp(reader)
            finally:
                writer.close()
                await writer.wait_closed()


class ValkeyLiveEventSubscriber:
    def __init__(
        self, connection: _RespConnection, stream_key: str, last_id: str = "0-0"
    ):
        self._conn = connection
        self._stream_key = stream_key
        self._last_id = last_id

    async def get(self, timeout_seconds: float) -> LiveJobEvent | None:
        block_ms = max(1, int(timeout_seconds * 1000))
        response = await self._conn.execute(
            "XREAD",
            "BLOCK",
            str(block_ms),
            "COUNT",
            "1",
            "STREAMS",
            self._stream_key,
            self._last_id,
        )
        if not response:
            return None
        _, entries = response[0]
        entry_id, fields = entries[0]
        self._last_id = entry_id
        payload = {
            fields[index]: fields[index + 1] for index in range(0, len(fields), 2)
        }
        raw_payload = json.loads(payload["payload_json"])
        return LiveJobEvent(
            id=entry_id,
            event_type=payload["event_type"],
            payload_json=raw_payload,
            created_at=datetime.fromisoformat(payload["created_at"]),
        )

    async def aclose(self) -> None:
        return None


class ValkeyLiveEventBus:
    def __init__(
        self,
        url: str,
        *,
        stream_prefix: str = "agent-orchestrator:live-events:",
        max_stream_length: int = 512,
        event_ttl_seconds: int = 300,
    ):
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 6379
        self._stream_prefix = stream_prefix
        self._max_stream_length = max_stream_length
        self._event_ttl_seconds = event_ttl_seconds
        self._conn = _RespConnection(self._host, self._port)
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
        self, job_id: str, event_type: str, payload_json: dict[str, Any]
    ) -> LiveJobEvent:
        created_at = datetime.now(timezone.utc)
        stream_key = self._stream_key(job_id)
        event_id = await self._conn.execute(
            "XADD",
            stream_key,
            "MAXLEN",
            "~",
            str(self._max_stream_length),
            "*",
            "event_type",
            event_type,
            "payload_json",
            json.dumps(payload_json),
            "created_at",
            created_at.isoformat(),
        )
        await self._conn.execute("EXPIRE", stream_key, str(self._event_ttl_seconds))
        return LiveJobEvent(
            id=str(event_id),
            event_type=event_type,
            payload_json=payload_json,
            created_at=created_at,
        )

    async def subscribe(self, job_id: str) -> ValkeyLiveEventSubscriber:
        return ValkeyLiveEventSubscriber(self._conn, self._stream_key(job_id))

    async def aclose(self) -> None:
        logger.info("Closing Valkey live event bus")
        return None
