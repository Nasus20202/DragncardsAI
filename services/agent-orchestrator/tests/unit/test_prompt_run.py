from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
)
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrost:
    def __init__(self, responses=None, error: BifrostError | None = None):
        self.responses = responses or []
        self.error = error

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


class FakeMcp:
    def __init__(self):
        self.calls = []

    async def list_tools(self, server_url, transport, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        self.calls.append(
            {"server_url": server_url, "tool_name": tool_name, "arguments": arguments}
        )
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


@pytest.fixture
async def repository(tmp_path: Path):
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
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
    await repo.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repo.enable_mcp_for_session(session.id, "game-service", enabled=True)
    return session


def _make_prompt_run_service(
    repo: Repository,
    bifrost: FakeBifrost,
    mcp: FakeMcp,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus | None = None,
) -> PromptRunService:
    bus = live_event_bus or InMemoryLiveEventBus()
    return PromptRunService(
        dependencies=PromptRunDependencies(
            settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
            repository=repo,
            bifrost_client=bifrost,
            live_event_bus=bus,
            mcp_tool_catalog=McpToolCatalog(mcp),
            skill_registry=skill_registry,
        ),
        transcript_service=SessionTranscriptService(repo),
        schedule_child_job=lambda job_id: None,
    )


@pytest.mark.asyncio
async def test_prompt_run_service_completes_prompt_with_tool(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    mcp = FakeMcp()
    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tool-1", name="game-service_next_step", arguments={}
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
    )

    await prompt_run.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "finished"
    assert mcp.calls[0]["tool_name"] == "next_step"


@pytest.mark.asyncio
async def test_prompt_run_service_marks_cancellation_before_execution(
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

    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(responses=[ChatResponse(content="done", tool_calls=[], raw={})]),
        FakeMcp(),
        skill_registry,
    )

    await prompt_run.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "cancelled"


@pytest.mark.asyncio
async def test_prompt_run_service_records_failure(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(error=BifrostError("gateway_error", "fatal", retryable=False)),
        FakeMcp(),
        skill_registry,
    )

    await prompt_run.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "gateway_error"
    events = await repository.list_events(job.id)
    failure = next(event for event in events if event.event_type == "failure")
    assert failure.payload_json["message"] == "fatal"
