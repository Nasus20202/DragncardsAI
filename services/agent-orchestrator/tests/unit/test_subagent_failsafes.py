"""Subagent failsafes: timeout, error loop, and no progress (DRA-51).

A subagent that would otherwise hang forever — a provider call that never
returns, a model-call failure repeating with the same code, or a model that
keeps answering with nothing — must fail its job instead. Each test drives a
real child job through the worker and asserts on the persisted outcome, and
where a parent is involved, on what the parent sees.
"""

from __future__ import annotations

import asyncio

import pytest

from agent_orchestrator.integrations.bifrost import (
    BifrostError,
    ChatResponse,
    ToolCall,
)
from agent_orchestrator.runtime.builtin_tools import (
    make_spawn_subagent_handler,
    make_wait_for_subagent_handler,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.subagent_failsafes import (
    SUBAGENT_ERROR_LOOP_ERROR_CODE,
    SUBAGENT_NO_PROGRESS_ERROR_CODE,
    SUBAGENT_TIMEOUT_ERROR_CODE,
    SubagentFailsafe,
    SubagentFailsafeError,
)
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

EMPTY_RESPONSE = ChatResponse(content="", tool_calls=[], raw={}, finish_reason="stop")


class HangingBifrost(FakeBifrost):
    """A provider call that never returns."""

    async def chat_completion(self, *args, **kwargs):
        await asyncio.sleep(10)
        raise AssertionError("the hanging call must have been cancelled")


class ErroringBifrost(FakeBifrost):
    """Raises the same Bifrost error on every model call."""

    def __init__(self, code: str = "upstream_error"):
        super().__init__()
        self.code = code

    async def chat_completion(self, *args, **kwargs):
        raise BifrostError(self.code, "temporary", retryable=True)


class EmptyBifrost(FakeBifrost):
    """Returns an empty response (no tool calls, no content) every call."""

    async def chat_completion(self, *args, **kwargs):
        return EMPTY_RESPONSE


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


def _text(result: dict) -> str:
    return result["content"][0]["text"]


async def _failure_event(repository: Repository, job_id: str) -> dict:
    events = await repository.list_events(job_id)
    failure = next(event for event in events if event.event_type == "failure")
    return failure.payload_json


# --- the failsafe module itself -------------------------------------------


@pytest.mark.asyncio
async def test_timeout_fires_after_the_deadline():
    failsafe = SubagentFailsafe(timeout_seconds=0.02)
    await asyncio.sleep(0.05)
    with pytest.raises(SubagentFailsafeError) as excinfo:
        failsafe.check_timeout()
    assert excinfo.value.error_code == SUBAGENT_TIMEOUT_ERROR_CODE
    assert excinfo.value.reason == "timeout"


@pytest.mark.asyncio
async def test_timeout_does_not_fire_before_the_deadline():
    failsafe = SubagentFailsafe(timeout_seconds=5.0)
    failsafe.check_timeout()
    assert failsafe.remaining_seconds() > 0


def test_error_loop_fires_after_three_identical_errors():
    failsafe = SubagentFailsafe(timeout_seconds=5.0)
    failsafe.note_model_error("transport_error", message="connection reset")
    failsafe.note_model_error("transport_error", message="connection reset")
    with pytest.raises(SubagentFailsafeError) as excinfo:
        failsafe.note_model_error("transport_error", message="connection reset")
    assert excinfo.value.error_code == SUBAGENT_ERROR_LOOP_ERROR_CODE
    assert excinfo.value.reason == "error_loop"
    assert "transport_error" in excinfo.value.message


def test_error_loop_resets_on_a_different_error():
    failsafe = SubagentFailsafe(timeout_seconds=5.0)
    failsafe.note_model_error("transport_error")
    failsafe.note_model_error("transport_error")
    # A different code is a progression, not a loop: the streak restarts.
    failsafe.note_model_error("rate_limited")
    failsafe.note_model_error("transport_error")
    failsafe.note_model_error("transport_error")
    with pytest.raises(SubagentFailsafeError) as excinfo:
        failsafe.note_model_error("transport_error")
    assert excinfo.value.error_code == SUBAGENT_ERROR_LOOP_ERROR_CODE


def test_error_loop_resets_on_a_successful_response():
    failsafe = SubagentFailsafe(timeout_seconds=5.0)
    failsafe.note_model_error("transport_error")
    failsafe.note_model_error("transport_error")
    failsafe.note_response(ChatResponse(content="work happened", tool_calls=[], raw={}))
    # The streak was reset, so two more identical errors are not yet a loop.
    failsafe.note_model_error("transport_error")
    failsafe.note_model_error("transport_error")


def test_no_progress_fires_after_three_empty_responses():
    failsafe = SubagentFailsafe(timeout_seconds=5.0)
    failsafe.note_response(EMPTY_RESPONSE)
    failsafe.note_response(EMPTY_RESPONSE)
    with pytest.raises(SubagentFailsafeError) as excinfo:
        failsafe.note_response(EMPTY_RESPONSE)
    assert excinfo.value.error_code == SUBAGENT_NO_PROGRESS_ERROR_CODE
    assert excinfo.value.reason == "no_progress"


def test_no_progress_resets_on_content_or_tool_calls():
    failsafe = SubagentFailsafe(timeout_seconds=5.0)
    failsafe.note_response(EMPTY_RESPONSE)
    failsafe.note_response(EMPTY_RESPONSE)
    # Content resets the streak, so two more empties are not yet a failure.
    failsafe.note_response(ChatResponse(content="answered", tool_calls=[], raw={}))
    failsafe.note_response(EMPTY_RESPONSE)
    failsafe.note_response(EMPTY_RESPONSE)
    # Tool calls reset it too.
    failsafe.note_response(
        ChatResponse(
            content="",
            tool_calls=[ToolCall(id="1", name="get_game_state", arguments={})],
            raw={},
        )
    )
    failsafe.note_response(EMPTY_RESPONSE)
    failsafe.note_response(EMPTY_RESPONSE)


# --- the worker-loop wiring ------------------------------------------------


@pytest.mark.asyncio
async def test_hanging_subagent_is_failed_by_the_timeout(
    repository: Repository, skill_registry
):
    """A provider call that never returns must not hold the worker forever."""
    _parent, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=HangingBifrost(),
        mcp_client=FakeMcp(),
        subagent_timeout_seconds=0.05,
    )

    await worker._run_job(child)

    stored = await repository.get_job(child.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == SUBAGENT_TIMEOUT_ERROR_CODE
    assert (await _failure_event(repository, child.id))["code"] == (
        SUBAGENT_TIMEOUT_ERROR_CODE
    )


@pytest.mark.asyncio
async def test_three_identical_model_errors_fail_the_subagent(
    repository: Repository, skill_registry
):
    """A repeating transport failure is an error loop, not a first-blip failure."""
    _parent, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=ErroringBifrost(code="upstream_error"),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(child)

    stored = await repository.get_job(child.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == SUBAGENT_ERROR_LOOP_ERROR_CODE
    failure = await _failure_event(repository, child.id)
    assert failure["code"] == SUBAGENT_ERROR_LOOP_ERROR_CODE
    assert "upstream_error" in failure["message"]


@pytest.mark.asyncio
async def test_three_empty_responses_fail_the_subagent(
    repository: Repository, skill_registry
):
    """A model answering nothing three times is not completing, it is stuck."""
    _parent, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=EmptyBifrost(),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(child)

    stored = await repository.get_job(child.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == SUBAGENT_NO_PROGRESS_ERROR_CODE
    failure = await _failure_event(repository, child.id)
    assert failure["code"] == SUBAGENT_NO_PROGRESS_ERROR_CODE


# --- propagation to the parent ---------------------------------------------


@pytest.mark.asyncio
async def test_failsafe_failure_propagates_to_a_waiting_parent(
    repository: Repository, skill_registry
):
    """`wait_for_subagent` must return the failsafe's failure, not hang."""
    bus = InMemoryLiveEventBus()
    parent_job, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=EmptyBifrost(),
        mcp_client=FakeMcp(),
        live_event_bus=bus,
    )

    waiting = asyncio.create_task(
        make_wait_for_subagent_handler(
            live_event_bus=bus,
            repository=repository,
            session_id=parent_job.session_id,
            job_id=parent_job.id,
            timeout_seconds=BUDGET,
            poll_interval_seconds=POLL,
        )({"child_job_id": child.id})
    )
    await asyncio.sleep(0)
    await worker._run_job(child)

    result = await asyncio.wait_for(waiting, timeout=BUDGET)
    assert result["is_error"] is True
    assert "subagent_no_progress" in _text(result)


@pytest.mark.asyncio
async def test_monitor_records_the_failsafe_reason_on_the_parent(
    repository: Repository, skill_registry
):
    """The parent's `subagent_failed` event names the failsafe, not a generic
    failure."""
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
        bifrost_client=EmptyBifrost(),
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
    assert payload["reason"] == "no_progress"
    assert payload["error_code"] == SUBAGENT_NO_PROGRESS_ERROR_CODE


@pytest.mark.asyncio
async def test_failsafe_failure_terminates_the_child_session(
    repository: Repository, skill_registry
):
    """A failed subagent must not leave its session occupied."""
    _parent, child = await _parent_and_child(repository)
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=EmptyBifrost(),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(child)

    child_session = await repository.get_session(child.session_id)
    assert child_session is not None
    assert child_session.status == "terminated"
