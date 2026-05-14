from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpClientError, McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.worker import WorkerService
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FailingClaimRepository:
    def __init__(self):
        self.calls = 0
        self.recovered = asyncio.Event()

    async def claim_next_job(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary claim failure")
        self.recovered.set()
        return None


class FakeBifrost:
    def __init__(self, responses=None, error: BifrostError | None = None):
        self.responses = responses or []
        self.error = error
        self.calls = []

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return None

    async def chat_completion(
        self,
        provider_id,
        model_name,
        messages,
        tools,
        gateway_options,
        provider_options,
        on_delta=None,
    ):
        self.calls.append(
            {"provider_id": provider_id, "model_name": model_name, "tools": tools}
        )
        if self.error is not None:
            raise self.error
        response = self.responses.pop(0)
        if on_delta is not None and response.content:
            await on_delta(
                SimpleNamespace(
                    content=response.content, reasoning="", reasoning_details=[]
                )
            )
        return response


class StreamingFakeBifrost(FakeBifrost):
    async def chat_completion(
        self,
        provider_id,
        model_name,
        messages,
        tools,
        gateway_options,
        provider_options,
        on_delta=None,
    ):
        self.calls.append(
            {"provider_id": provider_id, "model_name": model_name, "tools": tools}
        )
        if on_delta is not None:
            from agent_orchestrator.integrations.bifrost import (
                ChatDelta,
                ReasoningDetail,
            )

            await on_delta(
                ChatDelta(
                    reasoning="thinking...",
                    reasoning_details=[
                        ReasoningDetail(index=0, type="text", text="thinking...")
                    ],
                )
            )
            await on_delta(ChatDelta(content="partial answer"))
        return self.responses.pop(0)


class FakeMcp:
    def __init__(self):
        self.calls = []

    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        self.calls.append(
            {"server_url": server_url, "tool_name": tool_name, "arguments": arguments}
        )
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


class ErrorMcp(FakeMcp):
    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        raise McpClientError("tool transport failed")


class ListErrorMcp(FakeMcp):
    async def list_tools(self, server_url, headers=None):
        raise McpClientError("tool discovery failed")


@pytest.fixture
async def repository(tmp_path: Path):
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    yield repo
    await engine.dispose()


@pytest.fixture
def skill_registry(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    skill_dir = root / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("follow instructions", encoding="utf-8")
    return SkillRegistry((root,))


async def _prepare_session(repo: Repository):
    session = await repo.create_session("demo", {})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repo.add_skill_assignment(session.id, "demo-skill", "/tmp/demo-skill")
    await repo.add_mcp_assignment(
        session.id,
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    return session


async def _prepare_session_without_model(repo: Repository):
    return await repo.create_session("demo", {})


@pytest.mark.asyncio
async def test_worker_completes_prompt_with_tool(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(id="tool-1", name="game-service_next_step", arguments={})
                ],
                raw={},
            ),
            ChatResponse(content="finished", tool_calls=[], raw={}),
        ]
    )
    mcp = FakeMcp()
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=bifrost,
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(mcp),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "finished"
    assert len(bifrost.calls) == 2
    assert mcp.calls[0]["tool_name"] == "next_step"
    events = await repository.list_events(job.id)
    assert [event.event_type for event in events][-1] == "completion"


@pytest.mark.asyncio
async def test_worker_survives_transient_claim_failures(skill_registry: SkillRegistry):
    repository = FailingClaimRepository()
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    task = asyncio.create_task(worker.run_forever())
    await asyncio.wait_for(repository.recovered.wait(), timeout=1)
    await worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert repository.calls >= 2


@pytest.mark.asyncio
async def test_worker_retries_gateway_errors(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=2
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("gateway_error", "temporary", retryable=True)
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)
    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "queued"


@pytest.mark.asyncio
async def test_worker_cancels_before_tool_call(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
    await repository.request_cancel(job.id)

    mcp = FakeMcp()
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[ChatResponse(content="done", tool_calls=[], raw={})]
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(mcp),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)
    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "cancelled"
    assert mcp.calls == []


def test_worker_formats_nested_execution_error(skill_registry: SkillRegistry):
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=SimpleNamespace(),
        bifrost_client=SimpleNamespace(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=SimpleNamespace(),
        skill_registry=skill_registry,
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
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session_without_model(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "missing_model_config"


@pytest.mark.asyncio
async def test_worker_fails_on_unknown_tool_request(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
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
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
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
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(
            SKILL_ROOTS=str(skill_registry._roots[0]), worker_max_tool_rounds=1
        ),
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
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "execution_error"
    assert stored.error_message == "tool round limit exceeded"


@pytest.mark.asyncio
async def test_worker_continues_when_mcp_tool_call_fails(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
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
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(ErrorMcp()),
        skill_registry=skill_registry,
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
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=2
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
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
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(ErrorMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.error_code == "mcp_transport_error"


@pytest.mark.asyncio
async def test_worker_continues_when_mcp_tool_discovery_fails(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    bifrost = FakeBifrost(
        responses=[ChatResponse(content="finished", tool_calls=[], raw={})]
    )
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=bifrost,
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(ListErrorMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "finished"
    # MCP tools are absent due to discovery failure; builtin skill tools are always present
    tool_names = {t["function"]["name"] for t in bifrost.calls[0]["tools"]}
    assert "load_skill" in tool_names
    assert "load_skill_reference" in tool_names


@pytest.mark.asyncio
async def test_worker_marks_non_retryable_bifrost_error_as_failed(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=2
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("gateway_error", "fatal", retryable=False)
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "gateway_error"
    assert stored.error_message == "fatal"


def test_worker_classifies_errors(skill_registry: SkillRegistry):
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=SimpleNamespace(),
        bifrost_client=SimpleNamespace(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=SimpleNamespace(),
        skill_registry=skill_registry,
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
