"""Unit tests for auto-compaction trigger in the worker (_maybe_auto_compact)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.worker import WorkerService
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrost:
    def __init__(self, responses=None):
        self.responses = list(
            responses
            or [
                ChatResponse(
                    content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
                )
            ]
        )
        self.calls = []
        self.compact_calls = 0

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
        self.calls.append({"provider_id": provider_id, "messages_count": len(messages)})
        if on_delta is not None:
            # Check if this is the compaction call (no tools) — return compact response
            if not tools and len(self.responses) > 1:
                self.compact_calls += 1
                return ChatResponse(
                    content="summary text",
                    tool_calls=[],
                    raw={"usage": {"total_tokens": 25}},
                )
        response = (
            self.responses.pop(0)
            if self.responses
            else ChatResponse(content="done", tool_calls=[], raw={})
        )
        if on_delta is not None and response.content:
            await on_delta(
                SimpleNamespace(
                    content=response.content, reasoning="", reasoning_details=[]
                )
            )
        return response


class FakeMcp:
    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


@pytest.fixture
async def repository():
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
    await repo.add_mcp_assignment(
        session.id,
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    return session


async def _make_completed_job(
    repo: Repository, session_id: str, tokens: int = 100
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt="hi", metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": "ok"})
    await repo.update_job_tokens_used(job.id, tokens)
    await repo.mark_job_completed(job.id, "ok")
    return job.id


def _make_worker(
    repo: Repository,
    bifrost: FakeBifrost,
    skill_registry: SkillRegistry,
    settings: Settings | None = None,
    live_event_bus: InMemoryLiveEventBus | None = None,
) -> WorkerService:
    mcp_catalog = McpToolCatalog(FakeMcp())  # type: ignore[arg-type]
    return WorkerService(
        settings=settings
        or Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS="openai,gemini",
        ),
        repository=repo,
        bifrost_client=bifrost,  # type: ignore[arg-type]
        live_event_bus=live_event_bus or InMemoryLiveEventBus(),
        mcp_tool_catalog=mcp_catalog,
        skill_registry=skill_registry,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_compact_fires_above_threshold(
    repository: Repository, skill_registry: SkillRegistry
):
    """When tokens_used exceeds threshold, compaction is triggered before history."""
    session = await _prepare_session(repository)
    # Add enough token usage to exceed threshold (128000 * 0.8 = 102400)
    await _make_completed_job(repository, session.id, tokens=110000)

    bifrost = FakeBifrost(
        responses=[
            # compaction LLM call
            ChatResponse(
                content="game summary here",
                tool_calls=[],
                raw={"usage": {"total_tokens": 30}},
            ),
            # actual job LLM call
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            ),
        ]
    )
    worker = _make_worker(repository, bifrost, skill_registry)

    # Enqueue and run the new job
    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )

    with patch(
        "agent_orchestrator.runtime.prompt_run.perform_compaction",
        wraps=__import__(
            "agent_orchestrator.runtime.compaction", fromlist=["perform_compaction"]
        ).perform_compaction,
    ) as mock_compact:
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    # After running, compaction record should exist
    records = await repository.count_compaction_records(session.id)
    assert records == 1


@pytest.mark.asyncio
async def test_auto_compact_publishes_live_compaction_event(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    await _make_completed_job(repository, session.id, tokens=110000)

    live_event_bus = InMemoryLiveEventBus()
    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="game summary here",
                tool_calls=[],
                raw={"usage": {"total_tokens": 30}},
            ),
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            ),
        ]
    )
    worker = _make_worker(
        repository, bifrost, skill_registry, live_event_bus=live_event_bus
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    assert current_job is not None

    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    subscriber = await live_event_bus.subscribe(current_job.id)
    try:
        seen_compaction = False
        while True:
            event = await subscriber.get(0.01)
            if event is None:
                break
            if event.event_type == "compaction":
                seen_compaction = True
                assert event.payload_json["summary_text"] == "game summary here"
                assert event.payload_json["tokens_used"] == 30
                assert isinstance(event.payload_json.get("compaction_job_id"), str)
        assert seen_compaction is True
    finally:
        await subscriber.aclose()


@pytest.mark.asyncio
async def test_auto_compact_does_not_fire_below_threshold(
    repository: Repository, skill_registry: SkillRegistry
):
    """When tokens_used is below threshold, no compaction happens."""
    session = await _prepare_session(repository)
    # Add token usage well below threshold
    await _make_completed_job(repository, session.id, tokens=500)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(repository, bifrost, skill_registry)

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    records = await repository.count_compaction_records(session.id)
    assert records == 0


@pytest.mark.asyncio
async def test_auto_compact_skipped_when_memory_disabled(
    repository: Repository, skill_registry: SkillRegistry
):
    """When multi_turn_memory is False, _maybe_auto_compact is never called."""
    session = await _prepare_session(repository)
    await repository.update_multi_turn_memory(session.id, multi_turn_memory=False)
    # Even with very high token usage, no compaction should occur
    await _make_completed_job(repository, session.id, tokens=200000)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(repository, bifrost, skill_registry)

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    records = await repository.count_compaction_records(session.id)
    assert records == 0
