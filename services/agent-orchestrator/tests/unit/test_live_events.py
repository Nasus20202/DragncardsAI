"""Unit tests for InMemoryLiveEventBus — replay buffer and subscriber cleanup."""
from __future__ import annotations

import asyncio
import pytest

from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus


@pytest.mark.asyncio
async def test_late_subscriber_receives_buffered_events():
    """A subscriber that joins after events were published still gets them via replay."""
    bus = InMemoryLiveEventBus()
    await bus.publish("job-1", "reasoning", {"text": "chunk1"})
    await bus.publish("job-1", "reasoning", {"text": "chunk2"})

    sub = await bus.subscribe("job-1")
    try:
        event1 = await sub.get(timeout_seconds=0.1)
        event2 = await sub.get(timeout_seconds=0.1)
        assert event1 is not None and event1.payload_json["text"] == "chunk1"
        assert event2 is not None and event2.payload_json["text"] == "chunk2"
        # No more events
        assert await sub.get(timeout_seconds=0.05) is None
    finally:
        await sub.aclose()


@pytest.mark.asyncio
async def test_subscriber_receives_new_events_after_replay():
    """After replaying buffered events, new publishes are still delivered."""
    bus = InMemoryLiveEventBus()
    await bus.publish("job-1", "reasoning", {"text": "old"})

    sub = await bus.subscribe("job-1")
    try:
        old = await sub.get(timeout_seconds=0.1)
        assert old is not None and old.payload_json["text"] == "old"

        await bus.publish("job-1", "model_output", {"text": "new"})
        new = await sub.get(timeout_seconds=0.1)
        assert new is not None and new.payload_json["text"] == "new"
    finally:
        await sub.aclose()


@pytest.mark.asyncio
async def test_aclose_unsubscribes_from_future_events():
    """After aclose(), the subscriber no longer receives new publishes."""
    bus = InMemoryLiveEventBus()
    sub = await bus.subscribe("job-1")
    await sub.aclose()

    await bus.publish("job-1", "model_output", {"text": "after close"})
    # No active queues should be present for job-1
    assert len(bus._subscribers.get("job-1", set())) == 0


@pytest.mark.asyncio
async def test_replay_buffer_is_per_job():
    """Replay buffer is scoped per job_id — different jobs don't bleed into each other."""
    bus = InMemoryLiveEventBus()
    await bus.publish("job-A", "reasoning", {"text": "A"})
    await bus.publish("job-B", "reasoning", {"text": "B"})

    sub_a = await bus.subscribe("job-A")
    sub_b = await bus.subscribe("job-B")
    try:
        ea = await sub_a.get(timeout_seconds=0.1)
        eb = await sub_b.get(timeout_seconds=0.1)
        assert ea is not None and ea.payload_json["text"] == "A"
        assert eb is not None and eb.payload_json["text"] == "B"
        # Neither bleeds into the other
        assert await sub_a.get(timeout_seconds=0.05) is None
        assert await sub_b.get(timeout_seconds=0.05) is None
    finally:
        await sub_a.aclose()
        await sub_b.aclose()


@pytest.mark.asyncio
async def test_replay_buffer_respects_max_size():
    """Oldest events are evicted when the buffer exceeds max size."""
    bus = InMemoryLiveEventBus(replay_buffer_size=3)
    for i in range(5):
        await bus.publish("job-1", "reasoning", {"seq": i})

    sub = await bus.subscribe("job-1")
    try:
        events = []
        while True:
            e = await sub.get(timeout_seconds=0.05)
            if e is None:
                break
            events.append(e)
        # Only the last 3 events should be replayed
        assert len(events) == 3
        assert [e.payload_json["seq"] for e in events] == [2, 3, 4]
    finally:
        await sub.aclose()
