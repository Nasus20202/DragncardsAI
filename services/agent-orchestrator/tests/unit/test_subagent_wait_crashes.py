"""A crashed subagent must always end its parent's wait.

Every test here starts the parent's wait *before* the child dies, which is the
shape of the real bug: `wait_for_subagent` used to trust the live event stream
alone, so any crash that skipped publishing a terminal event left the parent
blocked for the full ten-minute event timeout.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from agent_orchestrator.runtime.builtin_tools import (
    build_builtin_registry,
    make_spawn_subagent_handler,
    make_wait_for_subagent_handler,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus, LiveJobEvent
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import make_job
from .worker_test_support import (  # noqa: F401
    FakeBifrost,
    FakeMcp,
    make_worker,
    prepare_session,
    repository,
    skill_registry,
)

# Short enough to keep the suite fast, long enough that a genuine hang still
# shows up as a test timeout rather than a passing assertion.
POLL = 0.02
BUDGET = 5.0


class CrashingBifrost(FakeBifrost):
    """Raises while the model call is in flight."""

    def __init__(self, crash: BaseException):
        super().__init__()
        self.crash = crash

    async def chat_completion(self, *args, **kwargs):
        raise self.crash


async def _parent_and_child(repository: Repository):
    """Enqueue a parent job plus a claimed child job attached to it."""
    parent_session = await prepare_session(repository)
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="orchestrate", metadata_json={}, max_attempts=1
    )
    child_session = await prepare_session(repository)
    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="scout the board", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None and child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)
    claimed_parent = await repository.claim_next_job()
    claimed_child = await repository.claim_next_job()
    assert claimed_parent is not None and claimed_parent.id == parent_job.id
    assert claimed_child is not None and claimed_child.id == child_job.id
    return parent_job, claimed_child


def _wait_handler(repository: Repository, bus, parent_job=None, **overrides):
    return make_wait_for_subagent_handler(
        live_event_bus=bus,
        repository=repository,
        session_id=parent_job.session_id if parent_job else "",
        job_id=parent_job.id if parent_job else "",
        timeout_seconds=overrides.get("timeout_seconds", BUDGET),
        poll_interval_seconds=overrides.get("poll_interval_seconds", POLL),
    )


def _default_wait_handler(repository: Repository, bus, parent_job):
    """A handler with the shipped budget, bound to the current parent context."""
    return make_wait_for_subagent_handler(
        live_event_bus=bus,
        repository=repository,
        session_id=parent_job.session_id,
        job_id=parent_job.id,
    )


def _text(result: dict) -> str:
    return result["content"][0]["text"]


@pytest.mark.parametrize(
    "crash",
    [
        RuntimeError("the board went missing"),
        TimeoutError("provider read timeout"),
        ExceptionGroup("wrapper", [RuntimeError("transport closed")]),
    ],
    ids=["exception", "timeout", "exception_group"],
)
@pytest.mark.asyncio
async def test_wait_ends_with_the_cause_when_the_child_run_crashes(
    repository: Repository, skill_registry, crash: BaseException
):
    """The waiting parent is told the child failed *and* why."""
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=CrashingBifrost(crash),
        mcp_client=FakeMcp(),
        live_event_bus=bus,
    )

    waiting = asyncio.create_task(
        _default_wait_handler(repository, bus, parent_job)({"child_job_id": child.id})
    )
    await asyncio.sleep(0)
    await worker._run_job(child)

    result = await asyncio.wait_for(waiting, timeout=BUDGET)
    assert result["is_error"] is True
    assert "failed" in _text(result)
    assert "execution_error" in _text(result)


@pytest.mark.asyncio
async def test_wait_ends_when_the_childs_failure_handling_itself_crashes(
    repository: Repository, skill_registry, monkeypatch: pytest.MonkeyPatch
):
    """The crash the live event stream never hears about.

    Failure handling raising means nothing is published for the child; only the
    worker's last-resort guard records the outcome, in the database.
    """
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=CrashingBifrost(RuntimeError("the board went missing")),
        mcp_client=FakeMcp(),
        live_event_bus=bus,
    )

    async def exploding_record_failure(*args, **kwargs):
        raise RuntimeError("failure handling itself crashed")

    monkeypatch.setattr(
        worker._prompt_run_service, "record_failure", exploding_record_failure
    )

    waiting = asyncio.create_task(
        _default_wait_handler(repository, bus, parent_job)({"child_job_id": child.id})
    )
    await asyncio.sleep(0)
    await worker._run_job(child)

    result = await asyncio.wait_for(waiting, timeout=BUDGET)
    assert result["is_error"] is True
    assert "worker_crash" in _text(result)


@pytest.mark.asyncio
async def test_worker_crash_guard_announces_the_failure(
    repository: Repository, skill_registry, monkeypatch: pytest.MonkeyPatch
):
    """Persisting the crash is not enough — waiters listen on the live bus."""
    bus = InMemoryLiveEventBus()
    _parent, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=CrashingBifrost(RuntimeError("boom")),
        mcp_client=FakeMcp(),
        live_event_bus=bus,
    )

    async def exploding_record_failure(*args, **kwargs):
        raise RuntimeError("failure handling itself crashed")

    monkeypatch.setattr(
        worker._prompt_run_service, "record_failure", exploding_record_failure
    )

    subscriber = await bus.subscribe(child.id)
    await worker._run_job(child)

    published = []
    while True:
        event = await subscriber.get(timeout_seconds=0.01)
        if event is None:
            break
        published.append(event)
    assert [event.event_type for event in published] == ["failure"]
    assert published[0].payload_json["code"] == "worker_crash"

    persisted = await repository.list_events(child.id)
    failure = next(event for event in persisted if event.event_type == "failure")
    assert failure.payload_json["code"] == "worker_crash"

    # A crashed child must not leave its session occupied either.
    child_session = await repository.get_session(child.session_id)
    assert child_session is not None
    assert child_session.status == "terminated"


@pytest.mark.asyncio
async def test_wait_returns_partial_work_of_an_interrupted_child(
    repository: Repository, skill_registry
):
    """`interrupted` is terminal: the child hit its tool round limit."""
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)
    await repository.mark_job_interrupted(child.id, result_text="got halfway")

    result = await asyncio.wait_for(
        _default_wait_handler(repository, bus, parent_job)({"child_job_id": child.id}),
        timeout=BUDGET,
    )
    assert result["is_error"] is False
    assert _text(result) == "got halfway"


@pytest.mark.asyncio
async def test_wait_gives_up_on_a_child_orphaned_by_a_dead_worker(
    repository: Repository, skill_registry
):
    """Nothing reclaims a job whose worker was killed, so the wait must bound
    itself and say what it saw."""
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)

    result = await asyncio.wait_for(
        _wait_handler(repository, bus, parent_job, timeout_seconds=0.05)(
            {"child_job_id": child.id}
        ),
        timeout=BUDGET,
    )
    assert result["is_error"] is True
    assert "Gave up waiting" in _text(result)
    assert "still recorded as running" in _text(result)

    stored = await repository.get_job(child.id)
    assert stored is not None
    assert stored.status == "running"


@pytest.mark.asyncio
async def test_abandoned_wait_is_recorded_on_the_parent_job(
    repository: Repository, skill_registry
):
    """A stalled wait must be visible in the session timeline, not just logged."""
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)

    await _wait_handler(repository, bus, parent_job, timeout_seconds=0.05)(
        {"child_job_id": child.id}
    )

    events = await repository.list_events(parent_job.id)
    abandoned = next(event for event in events if event.event_type == "subagent_failed")
    assert abandoned.payload_json["child_job_id"] == child.id
    assert abandoned.payload_json["reason"] == "wait_timeout"
    assert abandoned.payload_json["child_status"] == "running"


@pytest.mark.asyncio
async def test_wait_budget_is_absolute_not_per_event(
    repository: Repository, skill_registry
):
    """A child stuck in a loop keeps streaming; that must not renew the budget."""
    parent_job, child = await _parent_and_child(repository)

    class ChatteringSubscriber:
        def __init__(self):
            self.delivered = 0

        async def get(self, timeout_seconds: float):
            self.delivered += 1
            await asyncio.sleep(0.01)
            return LiveJobEvent(
                id=str(self.delivered),
                event_type="reasoning",
                payload_json={"text": "still thinking"},
                created_at=datetime.now(timezone.utc),
            )

        async def aclose(self) -> None:
            return None

    subscriber = ChatteringSubscriber()

    class ChatteringBus:
        async def publish(self, *args, **kwargs):
            return None

        async def subscribe(self, job_id: str):
            return subscriber

        async def aclose(self) -> None:
            return None

    result = await asyncio.wait_for(
        _wait_handler(repository, ChatteringBus(), parent_job, timeout_seconds=0.1)(
            {"child_job_id": child.id}
        ),
        timeout=BUDGET,
    )
    assert result["is_error"] is True
    assert "Gave up waiting" in _text(result)
    assert subscriber.delivered > 1


@pytest.mark.asyncio
async def test_wait_stops_when_the_parent_job_is_cancelled(
    repository: Repository, skill_registry
):
    """Cancelling the parent must not leave it blocked on a running child."""
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)

    waiting = asyncio.create_task(
        _wait_handler(repository, bus, parent_job)({"child_job_id": child.id})
    )
    await asyncio.sleep(0)
    await repository.request_cancel(parent_job.id)

    result = await asyncio.wait_for(waiting, timeout=BUDGET)
    assert result["is_error"] is True
    assert "this job was cancelled" in _text(result)


@pytest.mark.asyncio
async def test_wait_reports_a_child_cancelled_by_the_parents_cancellation(
    repository: Repository, skill_registry
):
    """Cascade the other way: a queued child is cancelled with its parent."""
    bus = InMemoryLiveEventBus()
    parent_session = await prepare_session(repository)
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="orchestrate", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None
    await repository.claim_next_job()
    child_session = await prepare_session(repository)
    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="scout", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    await repository.request_cancel(parent_job.id)

    handler = make_wait_for_subagent_handler(
        live_event_bus=bus,
        repository=repository,
        session_id=parent_session.id,
        job_id=parent_job.id,
        timeout_seconds=BUDGET,
        poll_interval_seconds=POLL,
    )
    result = await asyncio.wait_for(
        handler({"child_job_id": child_job.id}), timeout=BUDGET
    )
    assert result["is_error"] is True
    assert "was cancelled" in _text(result)


@pytest.mark.asyncio
async def test_child_monitor_reports_the_real_crash_reason(
    repository: Repository, skill_registry, monkeypatch: pytest.MonkeyPatch
):
    """`subagent_failed` must name the crash, not report a timeout."""
    bus = InMemoryLiveEventBus()
    parent_session = await prepare_session(repository)
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="orchestrate", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None
    await repository.claim_next_job()

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=CrashingBifrost(RuntimeError("the board went missing")),
        mcp_client=FakeMcp(),
        live_event_bus=bus,
    )

    async def run_the_child(child_job_id: str) -> None:
        claimed = await repository.claim_next_job()
        assert claimed is not None and claimed.id == child_job_id
        await worker._run_job(claimed)

    spawn = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        skill_registry=SkillRegistry(()),
        schedule_child_fn=run_the_child,
        monitor_timeout_seconds=BUDGET,
        monitor_poll_interval_seconds=POLL,
    )
    await spawn({"prompt": "scout the board"})

    async def failure_recorded() -> dict:
        for _ in range(200):
            events = await repository.list_events(parent_job.id)
            match = [e for e in events if e.event_type == "subagent_failed"]
            if match:
                return match[0].payload_json
            await asyncio.sleep(0.01)
        raise AssertionError("the monitor never reported the child's failure")

    payload = await failure_recorded()
    assert payload["reason"] == "failed"
    assert payload["error_code"] == "execution_error"
    assert "the board went missing" in payload["error_message"]


@pytest.mark.asyncio
async def test_registered_wait_tool_honours_the_configured_budget(
    repository: Repository, skill_registry
):
    """The registry must hand the handler the service's configured bounds."""
    parent_job, child = await _parent_and_child(repository)
    registry = build_builtin_registry(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=InMemoryLiveEventBus(),
        session_id=parent_job.session_id,
        job_id=parent_job.id,
        skill_assignments=[],
        job=make_job(parent_job_id=None, job_type="prompt"),
        subagent_wait_timeout_seconds=0.05,
        subagent_wait_poll_interval_seconds=POLL,
    )
    definition = registry.get("wait_for_subagent")
    assert definition is not None

    result = await asyncio.wait_for(
        definition.handler({"child_job_id": child.id}), timeout=BUDGET
    )
    assert result["is_error"] is True
    assert "Gave up waiting" in _text(result)
