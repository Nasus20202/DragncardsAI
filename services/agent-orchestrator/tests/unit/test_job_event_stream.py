from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_orchestrator.runtime.job_event_stream import JobEventStreamService
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


async def _prepare_running_job(repo: Repository):
    session = await repo.create_session("demo", {})
    job = await repo.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None
    return session, job, claimed


def _payload_from_frame(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


@pytest.mark.asyncio
async def test_job_event_stream_replays_then_yields_live_events(repository: Repository):
    session, job, _ = await _prepare_running_job(repository)
    await repository.append_event(job.id, session.id, "tool_call", {"tool": "one"})

    bus = InMemoryLiveEventBus()
    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=bus,
        poll_interval_seconds=0.01,
    )
    stream = stream_service.stream(job.id, is_disconnected=lambda: _false())

    first = await anext(stream)
    second = await anext(stream)
    await bus.publish(job.id, "model_output", {"text": "partial", "stream": True})
    third = await anext(stream)

    assert first.startswith("id: ")
    assert _payload_from_frame(second)["event_type"] == "tool_call"
    # A live frame is identified too, so a client can key on it like any other.
    assert third.startswith("id: ")
    assert _payload_from_frame(third)["event_type"] == "model_output"
    await stream.aclose()


def _id_from_frame(frame: str) -> str:
    return _payload_from_frame(frame)["id"]


async def _collect_frames(stream, event_type: str, count: int) -> list[str]:
    """Read frames of one type, skipping the `progress` row claiming a job emits."""
    collected: list[str] = []
    for _ in range(count + 5):
        frame = await anext(stream)
        if _payload_from_frame(frame)["event_type"] == event_type:
            collected.append(frame)
            if len(collected) == count:
                return collected
    raise AssertionError(f"stream never yielded {count} {event_type} frames")


@pytest.mark.asyncio
async def test_live_copy_of_a_durable_event_reuses_its_id(repository: Repository):
    """DRA-34: one question must not reach the browser as two events.

    Almost every publish is preceded by an `append_event`, and this stream serves
    both sources — it polls `list_events` *and* forwards the live bus. The client
    de-duplicates on the event id, so the live copy has to carry the durable
    row's id rather than the bus's own. Without that, `ask_user` rendered two
    identical question cards.
    """
    session, job, _ = await _prepare_running_job(repository)

    bus = InMemoryLiveEventBus()
    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=bus,
        poll_interval_seconds=0.01,
    )
    stream = stream_service.stream(job.id, is_disconnected=lambda: _false())

    payload = {"question_id": "q-1", "question": "Which hero?"}
    durable_event_id = await repository.append_event(
        job.id, session.id, "user_question", payload
    )
    await bus.publish(
        job.id, "user_question", payload, durable_event_id=durable_event_id
    )

    frames = await _collect_frames(stream, "user_question", 2)
    await stream.aclose()

    # Both copies of the one event, so both carry the one id.
    assert {_id_from_frame(frame) for frame in frames} == {str(durable_event_id)}


@pytest.mark.asyncio
async def test_live_event_without_a_durable_row_keeps_the_bus_id(
    repository: Repository,
):
    """A publish with no `job_events` twin still needs an id of its own.

    `compaction` is the case: its summary lives on a separate compaction job, so
    nothing in this job's event list will ever repeat it.
    """
    _, job, _ = await _prepare_running_job(repository)

    bus = InMemoryLiveEventBus()
    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=bus,
        poll_interval_seconds=0.01,
    )
    stream = stream_service.stream(job.id, is_disconnected=lambda: _false())

    published = await bus.publish(job.id, "compaction", {"summary_text": "so far"})
    frame = (await _collect_frames(stream, "compaction", 1))[0]
    await stream.aclose()

    assert _id_from_frame(frame) == published.id


@pytest.mark.asyncio
async def test_job_event_stream_honors_reconnect_cursor(repository: Repository):
    session, job, _ = await _prepare_running_job(repository)
    first_id = await repository.append_event(
        job.id, session.id, "tool_call", {"step": 1}
    )
    await repository.append_event(job.id, session.id, "completion", {"text": "done"})
    await repository.mark_job_completed(job.id, "done")

    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=InMemoryLiveEventBus(),
        poll_interval_seconds=0.01,
    )
    frames = []
    async for frame in stream_service.stream(
        job.id,
        after=first_id,
        is_disconnected=lambda: _false(),
    ):
        frames.append(frame)

    assert frames
    payloads = [_payload_from_frame(frame) for frame in frames]
    assert all(int(payload["id"]) > first_id for payload in payloads)
    assert payloads[-1]["event_type"] == "completion"


@pytest.mark.asyncio
async def test_job_event_stream_flushes_terminal_db_events_before_close(
    repository: Repository,
):
    session, job, _ = await _prepare_running_job(repository)
    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=InMemoryLiveEventBus(),
        poll_interval_seconds=0.01,
    )
    stream = stream_service.stream(job.id, is_disconnected=lambda: _false())

    _ = await anext(stream)

    await repository.append_event(job.id, session.id, "completion", {"text": "done"})
    await repository.mark_job_completed(job.id, "done")

    terminal_frame = await anext(stream)
    terminal_payload = _payload_from_frame(terminal_frame)
    assert terminal_payload["event_type"] == "completion"

    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def _false() -> bool:
    return False
