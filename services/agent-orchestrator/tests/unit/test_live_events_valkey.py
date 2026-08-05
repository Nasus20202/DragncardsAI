from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from agent_orchestrator.runtime.live_events import (
    ValkeyLiveEventBus,
    ValkeyLiveEventSubscriber,
)
from agent_orchestrator.storage.valkey import RespConnection


class _ExplodingReader:
    async def readexactly(self, _: int) -> bytes:
        raise GeneratorExit


class _FakeWriter:
    def __init__(self) -> None:
        self.closed = False
        self.wait_closed_awaited = False

    def write(self, _: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_awaited = True


@pytest.mark.asyncio
async def test_resp_connection_skips_wait_closed_during_generator_exit(monkeypatch):
    writer = _FakeWriter()

    async def fake_open_connection(host: str, port: int):
        assert host == "localhost"
        assert port == 6379
        return _ExplodingReader(), writer

    monkeypatch.setattr(
        "dragncards_common.resp.asyncio.open_connection",
        fake_open_connection,
    )

    conn = RespConnection("localhost", 6379)

    with pytest.raises(GeneratorExit):
        await conn.execute("PING")

    assert writer.closed is True
    assert writer.wait_closed_awaited is False


class _RecordingConnection:
    """Counts the commands a caller actually puts on the wire.

    Every command is one TCP connection and one `valkey.execute` span, so the
    command count is the quantity these tests are protecting.
    """

    def __init__(self, replies: list[Any] | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self._replies = list(replies or [])

    async def execute(self, *parts: object) -> Any:
        self.commands.append(tuple(str(part) for part in parts))
        if self._replies:
            return self._replies.pop(0)
        return "1-0"

    @property
    def command_names(self) -> list[str]:
        return [command[0].upper() for command in self.commands]


def _entry(
    index: int,
    event_type: str = "model_output",
    *,
    durable_event_id: str | None = None,
) -> list[Any]:
    fields = [
        "event_type",
        event_type,
        "payload_json",
        json.dumps({"text": f"chunk-{index}"}),
        "created_at",
        datetime.now(timezone.utc).isoformat(),
    ]
    if durable_event_id is not None:
        fields += ["durable_event_id", durable_event_id]
    return [f"{index}-0", fields]


@pytest.mark.asyncio
async def test_publish_costs_one_command_not_two():
    """Appending an event and refreshing its stream TTL is one round trip.

    A streaming model publishes one live event per token, so an `EXPIRE` issued
    as its own command doubled the commands, TCP connections and spans of the
    busiest path in the service.
    """
    bus = ValkeyLiveEventBus("valkey://localhost:6379")
    conn = _RecordingConnection(replies=["1700000000000-0"])
    bus._conn = conn

    event = await bus.publish("job-1", "model_output", {"text": "hello"})

    assert conn.command_names == ["EVAL"]
    script = conn.commands[0][1]
    assert "XADD" in script
    assert "EXPIRE" in script
    # The key travels as a declared KEYS entry, not interpolated into the script.
    assert conn.commands[0][2] == "1"
    assert conn.commands[0][3] == "agent-orchestrator:live-events:job-1"
    assert event.id == "1700000000000-0"
    assert event.payload_json == {"text": "hello"}
    # No durable row was named, so no `durable_event_id` field is written.
    assert "durable_event_id" not in conn.commands[0]


@pytest.mark.asyncio
async def test_publish_carries_a_durable_event_id_in_the_same_one_command():
    """DRA-34's field must survive being folded into the single round trip.

    The live copy of a persisted row has to reach the client under that row's id
    or the transcript renders the event twice, so the optional field travels as
    two more script arguments rather than as a second command or a second script.
    """
    bus = ValkeyLiveEventBus("valkey://localhost:6379")
    conn = _RecordingConnection(replies=["1700000000000-7"])
    bus._conn = conn

    event = await bus.publish(
        "job-1", "tool_call", {"tool": "next_step"}, durable_event_id=42
    )

    assert conn.command_names == ["EVAL"]
    command = conn.commands[0]
    assert command[command.index("durable_event_id") + 1] == "42"
    assert event.durable_event_id == "42"


@pytest.mark.asyncio
async def test_subscriber_reads_back_the_durable_event_id():
    conn = _RecordingConnection(
        replies=[[["stream", [_entry(1, "tool_call", durable_event_id="42")]]]]
    )
    subscriber = ValkeyLiveEventSubscriber(conn, "stream")

    event = await subscriber.get(15.0)

    assert event is not None
    assert event.durable_event_id == "42"


@pytest.mark.asyncio
async def test_subscriber_drains_a_batch_in_one_read():
    """One `XREAD` serves many events, so the consumer is not token-paced."""
    conn = _RecordingConnection(
        replies=[[["stream", [_entry(1), _entry(2), _entry(3)]]], None]
    )
    subscriber = ValkeyLiveEventSubscriber(conn, "stream", batch_size=64)

    first = await subscriber.get(15.0)
    second = await subscriber.get(15.0)
    third = await subscriber.get(15.0)

    assert [event.id for event in (first, second, third)] == ["1-0", "2-0", "3-0"]
    # Three events delivered, one command issued.
    assert conn.command_names == ["XREAD"]
    assert "COUNT" in conn.commands[0]
    assert conn.commands[0][conn.commands[0].index("COUNT") + 1] == "64"

    # Only once the buffer is empty does a second read reach Valkey, and it
    # resumes from the last entry handed out rather than replaying the batch.
    assert await subscriber.get(15.0) is None
    assert conn.command_names == ["XREAD", "XREAD"]
    assert conn.commands[1][-1] == "3-0"


@pytest.mark.asyncio
async def test_subscriber_buffer_is_dropped_when_the_subscription_ends():
    """The drain buffer belongs to one subscription, not to the process."""
    conn = _RecordingConnection(replies=[[["stream", [_entry(1), _entry(2)]]]])
    subscriber = ValkeyLiveEventSubscriber(conn, "stream")

    assert (await subscriber.get(15.0)).id == "1-0"
    await subscriber.aclose()

    assert len(subscriber._pending) == 0
