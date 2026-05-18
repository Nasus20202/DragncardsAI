from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse
from agent_orchestrator.integrations.mcp.client import McpClientError, McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.worker import WorkerService
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


class ErrorMcp(FakeMcp):
    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        raise McpClientError("tool transport failed")


class ListErrorMcp(FakeMcp):
    async def list_tools(self, server_url, transport, headers=None):
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


async def prepare_session(repo: Repository):
    session = await repo.create_session("demo", {})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repo.add_skill_registry(
        name="demo-skill",
        skill_path="/tmp/demo-skill",
        description=None,
        metadata_json={},
    )
    await repo.enable_skill_for_session(session.id, "demo-skill", enabled=True)
    await repo.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repo.enable_mcp_for_session(
        session_id=session.id,
        mcp_name="game-service",
        enabled=True,
    )
    return session


async def prepare_session_without_model(repo: Repository):
    return await repo.create_session("demo", {})


def make_worker(
    *,
    skill_registry: SkillRegistry,
    repository,
    bifrost_client,
    mcp_client,
    live_event_bus: InMemoryLiveEventBus | None = None,
    **settings_overrides,
) -> WorkerService:
    return WorkerService(
        settings=Settings(
            SKILL_ROOTS=str(skill_registry._roots[0]),
            **settings_overrides,
        ),
        repository=repository,
        bifrost_client=bifrost_client,
        live_event_bus=live_event_bus or InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(mcp_client),
        skill_registry=skill_registry,
    )
