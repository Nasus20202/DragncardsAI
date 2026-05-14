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


class LoadSkillBifrost:
    """Bifrost that loads a skill, then one listed reference, then completes."""

    def __init__(self):
        self.calls_list = []
        self._round = 0

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

        self.calls_list.append({"tools": tools})
        if self._round == 0:
            self._round += 1
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-ls",
                        name="load_skill",
                        arguments={"skill_name": "test-skill"},
                    )
                ],
                raw={},
            )
        if self._round == 1:
            self._round += 1
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-lsr",
                        name="load_skill_reference",
                        arguments={
                            "skill_name": "test-skill",
                            "reference_name": "guide.md",
                        },
                    )
                ],
                raw={},
            )
        if on_delta is not None:
            await on_delta(ChatDelta(content="Skill loaded!"))
        return ChatResponse(content="Skill loaded!", tool_calls=[], raw={})


@pytest.mark.asyncio
async def test_load_skill_emits_skill_loaded_event(tmp_path: Path):
    """Session with skill assigned emits a skill_loaded event after load_skill."""
    database_path = tmp_path / "skill-test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    test_skill = skill_root / "test-skill"
    test_skill.mkdir()
    (test_skill / "SKILL.md").write_text(
        "# Test Skill\n\nPlay safely.", encoding="utf-8"
    )
    reference_dir = test_skill / "reference"
    reference_dir.mkdir()
    (reference_dir / "guide.md").write_text("Guide content.", encoding="utf-8")

    bifrost = LoadSkillBifrost()
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
                create_response = await client.post(
                    "/sessions", json={"name": "skill-test"}
                )
                session_id = create_response.json()["session"]["id"]
                await client.put(
                    f"/sessions/{session_id}/model-config",
                    json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
                )
                await client.post(
                    f"/sessions/{session_id}/skills",
                    json={"skill_name": "test-skill"},
                )

                prompt_response = await client.post(
                    f"/sessions/{session_id}/prompts",
                    json={"prompt": "use the skill"},
                )
                assert prompt_response.status_code == 202
                job_id = prompt_response.json()["job"]["id"]

                for _ in range(60):
                    job_response = await client.get(f"/jobs/{job_id}")
                    if job_response.json()["job"]["status"] == "completed":
                        break
                    await asyncio.sleep(0.05)

                job = job_response.json()["job"]
                assert job["status"] == "completed"
                events = job["events"]
                skill_loaded = [e for e in events if e["event_type"] == "skill_loaded"]
                assert len(skill_loaded) == 1
                assert skill_loaded[0]["payload"]["skill_name"] == "test-skill"
                assert skill_loaded[0]["payload"]["reference_file_count"] == 1
    finally:
        await engine.dispose()
