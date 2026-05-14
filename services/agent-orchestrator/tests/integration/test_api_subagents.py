from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeMcp:
    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance game",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        return {"is_error": False, "content": [{"type": "text", "text": "advanced"}]}


class SpawnSubagentBifrost:
    """Bifrost that makes the parent call spawn_subagent, and the child completes directly."""

    def __init__(self):
        self._call_count = 0

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
        from agent_orchestrator.integrations.bifrost import ChatDelta

        self._call_count += 1
        user_messages = [m for m in messages if m.get("role") == "user"]
        last_prompt = user_messages[-1]["content"] if user_messages else ""

        if "subagent-task" in last_prompt:
            if on_delta:
                await on_delta(ChatDelta(content="child done"))
            return ChatResponse(content="child done", tool_calls=[], raw={})

        if self._call_count == 1:
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-spawn",
                        name="spawn_subagent",
                        arguments={"prompt": "subagent-task"},
                    )
                ],
                raw={},
            )

        if on_delta:
            await on_delta(ChatDelta(content="parent done"))
        return ChatResponse(content="parent done", tool_calls=[], raw={})


@pytest.mark.asyncio
async def test_spawn_subagent_creates_child_and_emits_events(tmp_path: Path):
    """Master job spawns a child and parent receives subagent lifecycle events."""
    database_path = tmp_path / "subagent-test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    bifrost = SpawnSubagentBifrost()
    app = create_app(
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            SKILL_ROOTS=str(skill_root),
        ),
        repository=repository,
        bifrost_client=bifrost,
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeMcp(),
        skill_registry=SkillRegistry((skill_root,)),
    )
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                create_response = await client.post("/sessions", json={"name": "subagent-test"})
                session_id = create_response.json()["session"]["id"]
                await client.put(
                    f"/sessions/{session_id}/model-config",
                    json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
                )

                prompt_response = await client.post(
                    f"/sessions/{session_id}/prompts",
                    json={"prompt": "run a subagent"},
                )
                assert prompt_response.status_code == 202
                job_id = prompt_response.json()["job"]["id"]

                for _ in range(120):
                    job_response = await client.get(f"/jobs/{job_id}")
                    status = job_response.json()["job"]["status"]
                    if status in ("completed", "failed"):
                        break
                    await asyncio.sleep(0.1)

                job = job_response.json()["job"]
                assert job["status"] == "completed", f"Job failed: {job}"
                events = job["events"]
                event_types = [e["event_type"] for e in events]
                assert "subagent_started" in event_types

                started_event = next(
                    e for e in events if e["event_type"] == "subagent_started"
                )
                assert "name" in started_event["payload"]
                assert started_event["payload"]["name"] == "subagent-task"

                for _ in range(20):
                    job_response = await client.get(f"/jobs/{job_id}")
                    events = job_response.json()["job"]["events"]
                    if any(e["event_type"] == "subagent_completed" for e in events):
                        break
                    await asyncio.sleep(0.05)

                event_types = [e["event_type"] for e in events]
                assert "subagent_completed" in event_types

                child_session_id = started_event["payload"]["child_session_id"]
                child_session = None
                for _ in range(20):
                    child_session_response = await client.get(f"/sessions/{child_session_id}")
                    assert child_session_response.status_code == 200
                    child_session = child_session_response.json()["session"]
                    if child_session["status"] == "terminated":
                        break
                    await asyncio.sleep(0.05)

                assert child_session is not None
                assert child_session["status"] == "terminated"

                sessions_response = await client.get("/sessions")
                assert sessions_response.status_code == 200
                listed_session_ids = [
                    session["id"] for session in sessions_response.json()["sessions"]
                ]
                assert session_id in listed_session_ids
                assert child_session_id not in listed_session_ids
    finally:
        await engine.dispose()
