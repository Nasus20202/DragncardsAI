"""DRA-42: a transient Valkey error must not kill a job or an SSE stream.

Every test here pins a failure the reporter actually hit. On the code before this
change each one fails: the stream test raises `ConnectionResetError` out of the
generator (which is the `500 in 41s` the browser saw), the publish tests fail the
job that was mid-response, and the TTL test aborts a publish whose event was
already in the stream.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse
from agent_orchestrator.runtime.builtin_tools import resolve_child_outcome
from agent_orchestrator.runtime.job_event_stream import JobEventStreamService
from agent_orchestrator.runtime.live_event_resilience import (
    BestEffortLiveEventBus,
    FailureStreak,
    LiveBusDegradation,
    best_effort_live_event_bus,
    unwrap_live_event_bus,
)
from agent_orchestrator.runtime.live_events import (
    InMemoryLiveEventBus,
    ValkeyLiveEventBus,
)
from agent_orchestrator.storage.repository import Repository

from .worker_test_support import (  # noqa: F401
    FakeBifrost,
    FakeMcp,
    StreamingFakeBifrost,
    make_worker,
    prepare_session,
    repository,
    skill_registry,
)

# A reset is the failure the report is made of, and it is not a subclass of
# anything the code special-cases, so it exercises the generic guard.
RESET = ConnectionResetError(104, "Connection reset by peer")


async def _false() -> bool:
    return False


def _make_stream_service(repo: Repository, bus) -> JobEventStreamService:
    """One place to build the service, so a rename of its timing knob is one edit."""
    return JobEventStreamService(
        repository=repo,
        live_event_bus=bus,
        poll_interval_seconds=0.01,
    )


async def _prepare_running_job(repo: Repository):
    session = await repo.create_session("demo", {})
    job = await repo.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None
    return session, job


class BrokenSubscriberBus(InMemoryLiveEventBus):
    """A bus whose subscribers fail their reads, like Valkey resetting mid-XREAD."""

    def __init__(self, *, failures: int | None = None):
        super().__init__()
        self.failures_remaining = failures
        self.get_calls = 0

    async def subscribe(self, job_id: str):
        inner = await super().subscribe(job_id)
        bus = self

        class Subscriber:
            async def get(self, timeout_seconds: float):
                bus.get_calls += 1
                if bus.failures_remaining is None or bus.failures_remaining > 0:
                    if bus.failures_remaining is not None:
                        bus.failures_remaining -= 1
                    raise RESET
                return await inner.get(timeout_seconds)

            async def aclose(self) -> None:
                await inner.aclose()

        return Subscriber()


class ExplodingLiveEventBus(InMemoryLiveEventBus):
    """A bus whose publishes always fail."""

    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def publish(self, *args, **kwargs):
        self.attempts += 1
        raise RESET


class FlakyRespConnection:
    """Records commands; fails whichever ones the test names."""

    def __init__(self, *, fail_commands: set[str], xadd_id: str = "1-1"):
        self.fail_commands = fail_commands
        self.xadd_id = xadd_id
        self.commands: list[str] = []

    async def execute(self, *parts):
        command = str(parts[0]).upper()
        self.commands.append(command)
        if command in self.fail_commands:
            raise RESET
        if command == "XADD":
            return self.xadd_id
        return 1


# --------------------------------------------------------------------------- #
# 1. The SSE stream must degrade to poll-only rather than die.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_live_subscriber_failure_does_not_end_the_stream(repository: Repository):
    """The reporter's `GET .../events/stream 500 in 41s`, from the server side.

    An unguarded `live_subscriber.get` propagated a reset out of the async
    generator, through Starlette's `stream_response`, and killed the response —
    so the live transcript stopped and the Next.js proxy reported
    `failed to pipe response`. Degrading costs latency; it must not cost the
    stream.
    """
    session, job = await _prepare_running_job(repository)
    bus = BrokenSubscriberBus()  # never recovers
    stream = _make_stream_service(repository, bus).stream(
        job.id, is_disconnected=lambda: _false()
    )

    # The `progress` row the claim wrote arrives from Postgres even though the
    # live bus is down for the whole run.
    first = await asyncio.wait_for(anext(stream), timeout=5)
    assert "progress" in first

    await repository.append_event(job.id, session.id, "tool_call", {"tool": "one"})
    second = await asyncio.wait_for(anext(stream), timeout=5)
    assert "tool_call" in second

    assert bus.get_calls >= 1, "the stream never even tried the live bus"
    await stream.aclose()


@pytest.mark.asyncio
async def test_stream_still_closes_on_a_terminal_job_while_the_bus_is_down(
    repository: Repository,
):
    """Degrading must not turn into hanging.

    Terminal detection used to sit only on the subscriber's timeout path, so
    swallowing a live-bus error and continuing would leave a finished job's
    stream open forever. The guard routes a failure into the same path a timeout
    takes.
    """
    session, job = await _prepare_running_job(repository)
    stream = _make_stream_service(repository, BrokenSubscriberBus()).stream(
        job.id, is_disconnected=lambda: _false()
    )
    _ = await asyncio.wait_for(anext(stream), timeout=5)

    await repository.append_event(job.id, session.id, "completion", {"text": "done"})
    await repository.mark_job_completed(job.id, "done")

    frames = []
    with pytest.raises(StopAsyncIteration):
        for _ in range(10):
            frames.append(await asyncio.wait_for(anext(stream), timeout=5))
    assert any("completion" in frame for frame in frames)


@pytest.mark.asyncio
async def test_stream_resumes_live_delivery_after_the_bus_recovers(
    repository: Repository,
):
    """A recovered bus is used again — the stream is not permanently downgraded."""
    _, job = await _prepare_running_job(repository)
    bus = BrokenSubscriberBus(failures=2)
    stream = _make_stream_service(repository, bus).stream(
        job.id, is_disconnected=lambda: _false()
    )
    _ = await asyncio.wait_for(anext(stream), timeout=5)

    await bus.publish(job.id, "model_output", {"text": "back", "stream": True})
    frames = []
    for _ in range(6):
        frames.append(await asyncio.wait_for(anext(stream), timeout=10))
        if any("model_output" in frame for frame in frames):
            break
    assert any("model_output" in frame for frame in frames)
    await stream.aclose()


@pytest.mark.asyncio
async def test_degradation_backoff_grows_and_resets():
    """Neither a hot retry nor a long block: short, doubling, capped, reset on success."""
    degradation = LiveBusDegradation(
        "job-1", min_seconds=0.001, max_seconds=0.004, log=logging.getLogger("test")
    )
    assert not degradation.degraded

    delays = []
    for _ in range(4):
        delays.append(degradation.delay_seconds)
        try:
            raise RESET
        except ConnectionResetError:
            await degradation.note_failure()

    assert delays == [0.001, 0.002, 0.004, 0.004]
    assert degradation.degraded
    degradation.note_success()
    assert not degradation.degraded
    assert degradation.delay_seconds == 0.001


# --------------------------------------------------------------------------- #
# 2. A publish failure must not fail its caller.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_best_effort_publish_returns_none_instead_of_raising():
    inner = ExplodingLiveEventBus()
    bus = BestEffortLiveEventBus(inner)
    assert await bus.publish("job-1", "model_output", {"text": "hi"}) is None
    assert inner.attempts == 1


@pytest.mark.asyncio
async def test_best_effort_wrap_is_idempotent_and_unwrappable():
    inner = InMemoryLiveEventBus()
    once = best_effort_live_event_bus(inner)
    assert best_effort_live_event_bus(once) is once
    assert unwrap_live_event_bus(once) is inner
    assert unwrap_live_event_bus(inner) is inner


@pytest.mark.asyncio
async def test_a_publish_failure_during_a_delta_does_not_fail_the_job(
    repository: Repository,
    skill_registry,
):
    """The reporter's second traceback: a reset inside `on_bifrost_delta`.

    The publish sits inside the streaming callback that `_stream_chat_completion`
    awaits, which sits inside the job's own `try`. So one failed publish aborted
    the model call and then marked a healthy job failed. The job must complete.
    """
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    bus = ExplodingLiveEventBus()
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=StreamingFakeBifrost(
            responses=[ChatResponse(content="final answer", tool_calls=[], raw={})]
        ),
        mcp_client=FakeMcp(),
        live_event_bus=bus,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "final answer"
    # Every publish was attempted and every one failed, so the tolerance — not
    # luck about which ones ran — is what kept the job alive.
    assert bus.attempts > 0


@pytest.mark.asyncio
async def test_the_transcript_survives_a_total_live_bus_outage(
    repository: Repository,
    skill_registry,
):
    """What the browser still gets: the durable rows, in full.

    This is the whole justification for swallowing. Nothing is lost, only
    delayed to the stream's next poll.
    """
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=StreamingFakeBifrost(
            responses=[ChatResponse(content="final answer", tool_calls=[], raw={})]
        ),
        mcp_client=FakeMcp(),
        live_event_bus=ExplodingLiveEventBus(),
    )
    await worker._run_job(claimed)

    events = await repository.list_events(job.id, after_id=0)
    types = [event.event_type for event in events]
    assert "completion" in types
    assert "model_output" in types


# --------------------------------------------------------------------------- #
# 3. A failing TTL refresh must not undo a successful XADD.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_expire_failure_after_a_successful_xadd_still_publishes():
    """The exact frames in the report: `publish` threw on `EXPIRE`, not `XADD`.

    The event was in the stream and every subscriber would have seen it. Throwing
    anyway is what aborted the model call.
    """
    bus = ValkeyLiveEventBus("valkey://localhost:6379")
    conn = FlakyRespConnection(fail_commands={"EXPIRE"}, xadd_id="7-7")
    bus._conn = conn

    event = await bus.publish("job-1", "model_output", {"text": "hi"})

    assert event is not None
    assert event.id == "7-7"
    assert conn.commands == ["XADD", "EXPIRE"]


@pytest.mark.asyncio
async def test_a_failing_xadd_still_fails_the_publish():
    """The guard is narrow. Losing the event itself is still an error the bus reports.

    Tolerating it is the wrapper's job, one layer out, where the durable row is
    known to exist.
    """
    bus = ValkeyLiveEventBus("valkey://localhost:6379")
    bus._conn = FlakyRespConnection(fail_commands={"XADD"})

    with pytest.raises(ConnectionResetError):
        await bus.publish("job-1", "model_output", {"text": "hi"})


# --------------------------------------------------------------------------- #
# 4. A job must reach a terminal status even when announcing its failure fails.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_job_fails_cleanly_when_its_failure_publish_fails(
    repository: Repository,
    skill_registry,
):
    """The reporter's third traceback: `record_failure`'s own publish threw.

    The job did still reach `failed` before this change, because
    `_force_terminal_failure` guards each of its steps — but it got there by the
    crash path, so the recorded cause was `worker_crash` instead of the real
    error and the event list carried the failure twice. Tolerating the publish
    keeps `record_failure` intact, so the diagnosis survives.
    """
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("provider_error", "upstream exploded", retryable=False)
        ),
        mcp_client=FakeMcp(),
        live_event_bus=ExplodingLiveEventBus(),
    )
    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "provider_error"

    failures = [
        event
        for event in await repository.list_events(job.id, after_id=0)
        if event.event_type == "failure"
    ]
    assert len(failures) == 1
    assert failures[0].payload_json["code"] == "provider_error"


# --------------------------------------------------------------------------- #
# 5. Logging discipline: one traceback per outage, then a thinning trail.
# --------------------------------------------------------------------------- #


def test_failure_streak_logs_one_traceback_then_powers_of_two():
    log = logging.getLogger("dra42-streak-test")
    streak = FailureStreak(log=log)
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        for _ in range(20):
            try:
                raise RESET
            except ConnectionResetError:
                streak.note_failure("publish failed")
        streak.note_success("publishing recovered")
    finally:
        log.removeHandler(handler)

    # 20 failures: a traceback for the first, warnings at 2, 4, 8 and 16, and one
    # recovery line. Twenty lines for twenty failures is the flood DRA-35 fixed
    # elsewhere and this avoids here.
    assert sum(1 for r in records if r.exc_info) == 1
    warnings = [r for r in records if r.levelno == logging.WARNING]
    assert len(warnings) == 4
    assert all("consecutive" in r.getMessage() for r in warnings)
    assert sum(1 for r in records if r.levelno == logging.INFO) == 1
    assert streak.count == 0


# --------------------------------------------------------------------------- #
# 6. A subagent wait must survive the live bus too.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_subagent_wait_survives_a_dead_live_bus(repository: Repository):
    """The fourth unguarded read, and the one closest to "orchestrator mode".

    `resolve_child_outcome` consumes the live bus to return the moment a child
    finishes, but the child's row has always been the authority. The read was
    unguarded, so a reset escaped `wait_for_subagent` into the parent job's own
    handler and failed the *parent* — on the multi-agent path DRA-42 was reported
    against. The wait must fall back to the row.
    """
    parent_session = await prepare_session(repository)
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="orchestrate", metadata_json={}, max_attempts=1
    )
    child_session = await prepare_session(repository)
    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="scout", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None and child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)
    assert await repository.claim_next_job() is not None  # parent
    claimed_child = await repository.claim_next_job()
    assert claimed_child is not None

    # Deliberately no fiddling with the backoff constants: the wait must resolve
    # from the child's row on its own default cadence, and a test that pins the
    # constant names would break on every tuning change.
    async def complete_the_child_shortly() -> None:
        await asyncio.sleep(0.05)
        await repository.mark_job_completed(claimed_child.id, "scouted")

    completer = asyncio.create_task(complete_the_child_shortly())
    # On the unguarded code this await raises the reset straight out of the wait,
    # which is exactly how a dead live bus failed the *parent* job.
    outcome = await asyncio.wait_for(
        resolve_child_outcome(
            repository=repository,
            live_event_bus=BrokenSubscriberBus(),
            child_job_id=claimed_child.id,
            timeout_seconds=30.0,
            poll_interval_seconds=0.05,
        ),
        timeout=20,
    )
    await completer

    assert outcome.kind == "completed"
    assert outcome.has_result
