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
    assert not third.startswith("id: ")
    assert _payload_from_frame(third)["event_type"] == "model_output"
    await stream.aclose()


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
