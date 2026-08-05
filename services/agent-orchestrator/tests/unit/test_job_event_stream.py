from __future__ import annotations

import asyncio
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
        idle_block_seconds=0.01,
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
        idle_block_seconds=0.01,
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
        idle_block_seconds=0.01,
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
        idle_block_seconds=0.01,
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
        idle_block_seconds=0.01,
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


@pytest.mark.asyncio
async def test_job_event_stream_closes_without_waiting_an_idle_interval(
    repository: Repository,
):
    """A terminal event from the database must not cost one idle interval.

    The idle interval only exists as a fallback for a job that went terminal
    without publishing. Once the terminal event has been delivered all that
    remains is a final database pass, so waiting on the live bus first would make
    a long fallback interval visible to the user as a hung stream.
    """
    session, job, _ = await _prepare_running_job(repository)
    await repository.append_event(job.id, session.id, "completion", {"text": "done"})
    await repository.mark_job_completed(job.id, "done")

    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=InMemoryLiveEventBus(),
        # Long enough that closing the stream would visibly hang if the loop
        # waited on the live bus after seeing the terminal event.
        idle_block_seconds=600.0,
    )

    frames = []
    async with asyncio.timeout(5):
        async for frame in stream_service.stream(
            job.id, is_disconnected=lambda: _false()
        ):
            frames.append(frame)

    # Reaching here at all is the assertion: the generator ran to completion
    # well inside the timeout instead of blocking on the 600s fallback wait.
    assert [_payload_from_frame(frame)["event_type"] for frame in frames][-1] == (
        "completion"
    )


@pytest.mark.asyncio
async def test_cancelling_a_job_reaches_an_open_stream_without_waiting_the_idle_interval(
    repository: Repository,
):
    """Cancel must land on an open stream at once, not on its next fallback poll.

    This pins the interaction between two changes. DRA-34 removed the
    `cancellation` publishes because `mark_job_cancelled` appends that row
    inside the repository, and a second copy under a second id rendered the
    cancellation twice; it was safe then because the stream re-read the database
    every 200ms. DRA-37 turned that 200ms into a 15-second fallback interval, at
    which point a durable terminal row nobody publishes means the user clicks
    cancel and watches the stream hang.

    So the publish is now mandatory rather than merely nice, and the id it
    carries is still mandatory. The idle interval here is longer than the test's
    own timeout, which is what makes this fail rather than merely slow down if
    someone drops the publish or wires the interval back to the worker tick.
    """
    session, job, _ = await _prepare_running_job(repository)

    bus = InMemoryLiveEventBus()
    stream_service = JobEventStreamService(
        repository=repository,
        live_event_bus=bus,
        idle_block_seconds=600.0,
    )
    stream = stream_service.stream(job.id, is_disconnected=lambda: _false())

    # Drain the queued `progress` row so the stream is genuinely idle, i.e.
    # sitting in the fallback wait, exactly as it is while a job runs.
    _ = await anext(stream)

    # What the repository does when the worker notices the cancellation flag.
    durable_event_id = await repository.mark_job_cancelled(job.id, reason="user asked")
    assert durable_event_id is not None
    await bus.publish(
        job.id,
        "cancellation",
        {"reason": "user asked"},
        durable_event_id=durable_event_id,
    )

    async with asyncio.timeout(5):
        frame = await anext(stream)

    payload = _payload_from_frame(frame)
    assert payload["event_type"] == "cancellation"
    # And it arrives under the durable row's id, so the copy the database pass
    # yields next collapses into it instead of showing a second cancellation.
    assert payload["id"] == str(durable_event_id)
    await stream.aclose()


@pytest.mark.asyncio
async def test_requesting_cancellation_returns_ids_for_the_job_and_its_children(
    repository: Repository,
):
    """The cancel endpoint can only publish what the repository hands back.

    `request_cancel` appends a terminal `cancellation` for the job *and* for every
    active child, and each of those jobs may have its own open stream. Returning
    the ids is what lets the endpoint announce all of them under the ids the
    durable rows already have.
    """
    session = await repository.create_session("demo", {})
    parent = await repository.enqueue_prompt_job(
        session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    assert parent is not None
    await repository.claim_next_job()
    child = await repository.enqueue_prompt_job(
        session.id, prompt="child", metadata_json={}, max_attempts=1
    )
    assert child is not None
    await repository.set_parent_job_id(child.id, parent.id)
    await repository.claim_next_job()  # the child must be active to be propagated to

    cancelled, appended = await repository.request_cancel(parent.id)

    assert cancelled is not None
    assert [record.job_id for record in appended] == [parent.id, child.id]
    assert all(record.event_id is not None for record in appended)
    # Each id names the row that job's own stream will also read from Postgres.
    for record in appended:
        events = await repository.list_events(record.job_id, after_id=0)
        assert record.event_id in {event.id for event in events}


async def _false() -> bool:
    return False
