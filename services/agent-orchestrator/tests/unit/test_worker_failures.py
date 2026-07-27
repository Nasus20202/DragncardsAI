from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpClientError
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.session_transcript import build_message_history
from agent_orchestrator.storage.repository import Repository

from .worker_test_support import (
    ErrorMcp,
    FakeBifrost,
    FakeMcp,
    ListErrorMcp,
    make_worker,
    prepare_session,
    prepare_session_without_model,
    repository,
    skill_registry,
)


@pytest.mark.asyncio
async def test_worker_retries_gateway_errors(repository: Repository, skill_registry):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=2
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("gateway_error", "temporary", retryable=True)
        ),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)
    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "queued"


@pytest.mark.asyncio
async def test_worker_cancels_before_tool_call(repository: Repository, skill_registry):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
    await repository.request_cancel(job.id)

    mcp = FakeMcp()
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[ChatResponse(content="done", tool_calls=[], raw={})]
        ),
        mcp_client=mcp,
    )

    await worker._run_job(claimed)
    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "cancelled"
    assert mcp.calls == []


def test_worker_formats_nested_execution_error(skill_registry):
    worker = make_worker(
        skill_registry=skill_registry,
        repository=SimpleNamespace(),
        bifrost_client=SimpleNamespace(),
        mcp_client=SimpleNamespace(),
        live_event_bus=InMemoryLiveEventBus(),
    )

    error = ExceptionGroup(
        "wrapper", [RuntimeError("Redirect response '307 Temporary Redirect'")]
    )
    assert (
        worker._format_execution_error(error)
        == "Redirect response '307 Temporary Redirect'"
    )


@pytest.mark.asyncio
async def test_worker_fails_without_model_config(
    repository: Repository, skill_registry
):
    session = await prepare_session_without_model(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "missing_model_config"


@pytest.mark.asyncio
async def test_worker_fails_on_unknown_tool_request(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id="tool-1", name="unknown_tool", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(content="recovered", tool_calls=[], raw={}),
            ]
        ),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "recovered"
    events = await repository.list_events(job.id)
    tool_result = next(event for event in events if event.event_type == "tool_result")
    assert tool_result.payload_json["is_error"] is True
    assert tool_result.payload_json["result"]["content"][0]["text"] == (
        "Unknown tool requested: unknown_tool"
    )


@pytest.mark.asyncio
async def test_worker_fails_when_tool_round_limit_is_exceeded(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tool-1", name="game-service_next_step", arguments={}
                        )
                    ],
                    raw={},
                )
            ]
        ),
        mcp_client=FakeMcp(),
        worker_max_tool_rounds=1,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "interrupted"
    assert stored.error_code == "tool_round_limit"
    assert stored.error_message == "Tool round limit reached"


@pytest.mark.asyncio
async def test_worker_continues_when_mcp_tool_call_fails(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tool-1", name="game-service_next_step", arguments={}
                        )
                    ],
                    raw={},
                )
            ]
        ),
        mcp_client=ErrorMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "mcp_transport_error"
    assert stored.error_message == "tool transport failed"
    events = await repository.list_events(job.id)
    failure = next(event for event in events if event.event_type == "failure")
    assert failure.payload_json == {
        "code": "mcp_transport_error",
        "message": "tool transport failed",
        "retryable": True,
    }


@pytest.mark.asyncio
async def test_worker_retries_mcp_transport_failures(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=2
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tool-1", name="game-service_next_step", arguments={}
                        )
                    ],
                    raw={},
                )
            ]
        ),
        mcp_client=ErrorMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.error_code == "mcp_transport_error"


@pytest.mark.asyncio
async def test_worker_continues_when_mcp_tool_discovery_fails(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    bifrost = FakeBifrost(
        responses=[ChatResponse(content="finished", tool_calls=[], raw={})]
    )
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=ListErrorMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "finished"
    tool_names = {tool["function"]["name"] for tool in bifrost.calls[0]["tools"]}
    assert "load_skill" in tool_names
    assert "load_skill_reference" in tool_names


@pytest.mark.asyncio
async def test_worker_marks_non_retryable_bifrost_error_as_failed(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=2
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("gateway_error", "fatal", retryable=False)
        ),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "gateway_error"
    assert stored.error_message == "fatal"


class CrashingBifrost(FakeBifrost):
    """Raises an error type the worker does not explicitly classify."""

    def __init__(self, crash: BaseException):
        super().__init__()
        self.crash = crash

    async def chat_completion(self, *args, **kwargs):
        raise self.crash


@pytest.mark.parametrize(
    "crash",
    [
        TimeoutError("provider read timeout"),
        ExceptionGroup("wrapper", [RuntimeError("transport closed")]),
    ],
    ids=["timeout", "exception_group"],
)
@pytest.mark.asyncio
async def test_unclassified_crash_keeps_prompt_in_context(
    repository: Repository, skill_registry, crash: BaseException
):
    """A crashed run must still leave its prompt visible to the next run."""
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="remember the alamo", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=CrashingBifrost(crash),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "execution_error"
    events = await repository.list_events(job.id)
    assert any(event.event_type == "failure" for event in events)

    history = await build_message_history(repository, session.id, "next-job")
    assert history[0] == {"role": "user", "content": "remember the alamo"}
    assert history[-1]["role"] == "assistant"
    assert "Previous turn failed before completing" in history[-1]["content"]


@pytest.mark.asyncio
async def test_crash_before_the_model_call_keeps_prompt_in_context(
    repository: Repository, skill_registry, monkeypatch: pytest.MonkeyPatch
):
    """Crashes in the run prologue must not leave the job stuck in `running`."""
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="deal the encounter", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(),
        mcp_client=FakeMcp(),
    )

    async def exploding_cancellation_check(_job_id: str) -> bool:
        raise TimeoutError("database read timed out")

    monkeypatch.setattr(
        repository, "get_job_cancellation_requested", exploding_cancellation_check
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"

    history = await build_message_history(repository, session.id, "next-job")
    assert history[0] == {"role": "user", "content": "deal the encounter"}


@pytest.mark.asyncio
async def test_worker_forces_terminal_status_when_prompt_run_raises(
    repository: Repository, skill_registry, monkeypatch: pytest.MonkeyPatch
):
    """Last-resort guard: `_run_job` is detached, so nothing else would notice."""
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="mulligan my hand", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(),
        mcp_client=FakeMcp(),
    )

    async def exploding_run(_job):
        raise TimeoutError("failure handling itself crashed")

    monkeypatch.setattr(worker._prompt_run_service, "run", exploding_run)

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "worker_crash"

    history = await build_message_history(repository, session.id, "next-job")
    assert history[0] == {"role": "user", "content": "mulligan my hand"}


def test_worker_classifies_errors(skill_registry):
    worker = make_worker(
        skill_registry=skill_registry,
        repository=SimpleNamespace(),
        bifrost_client=SimpleNamespace(),
        mcp_client=SimpleNamespace(),
        live_event_bus=InMemoryLiveEventBus(),
    )

    assert worker._classify_execution_failure(
        BifrostError("gateway_error", "temporary", retryable=True)
    ) == {
        "code": "gateway_error",
        "message": "temporary",
        "retryable": True,
    }
    assert worker._classify_execution_failure(McpClientError("transport down")) == {
        "code": "mcp_transport_error",
        "message": "transport down",
        "retryable": True,
    }
    assert worker._classify_execution_failure(RuntimeError("boom")) == {
        "code": "execution_error",
        "message": "boom",
        "retryable": False,
    }
