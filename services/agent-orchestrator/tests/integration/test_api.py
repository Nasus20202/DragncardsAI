from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrost:
    def __init__(self):
        self.healthy = True
        self.responses = [
            ChatResponse(
                content="",
                tool_calls=[ToolCall(id="call-1", name="game-service_next_step", arguments={})],
                raw={},
            ),
            ChatResponse(content="All set", tool_calls=[], raw={}),
        ]

    async def health(self) -> bool:
        return self.healthy

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return None

    async def chat_completion(self, *args, **kwargs):
        await asyncio.sleep(0.02)
        on_delta = kwargs.get("on_delta")
        response = self.responses.pop(0)
        if on_delta is not None and response.content:
            from agent_orchestrator.integrations.bifrost import ChatDelta

            await on_delta(ChatDelta(content=response.content))
        return response


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


@pytest.fixture
async def app(tmp_path: Path):
    database_path = tmp_path / "integration.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    test_skill = skill_root / "test-skill"
    test_skill.mkdir()
    (test_skill / "SKILL.md").write_text("Play safely", encoding="utf-8")

    app = create_app(
        settings=Settings(database_url=f"sqlite+aiosqlite:///{database_path}", SKILL_ROOTS=str(skill_root)),
        repository=repository,
        bifrost_client=FakeBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeMcp(),
        skill_registry=SkillRegistry((skill_root,)),
    )
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_run_completes_background_job(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]

        sessions_response = await client.get("/sessions", params={"limit": 10, "offset": 0})
        assert sessions_response.status_code == 200
        assert sessions_response.json()["page"]["total"] >= 1

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"})
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        tools_response = await client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        assert tools_response.json()["tools"][0]["server_url"] == "http://game-service/mcp/"

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "take the next step"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(40):
            job_response = await client.get(f"/jobs/{job_id}")
            if job_response.json()["job"]["status"] == "completed":
                break
            await asyncio.sleep(0.05)
        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "All set"
        assert job["available_tools"][0]["name"] == "game-service_next_step"
        assert job["latest_event_type"] == "completion"
        assert any(event["event_type"] == "tool_result" for event in job["events"])
        assert not any(event["event_type"] == "model_output" and event["payload"].get("stream") for event in job["events"])
        tool_call_event = next(event for event in job["events"] if event["event_type"] == "tool_call")
        assert tool_call_event["payload"]["server_url"] == "http://game-service/mcp/"

        session_jobs_response = await client.get(f"/sessions/{session_id}/jobs")
        assert session_jobs_response.status_code == 200
        assert session_jobs_response.json()["jobs"][0]["id"] == job_id
        assert session_jobs_response.json()["page"]["total"] == 1

        filtered_jobs_response = await client.get(
            f"/sessions/{session_id}/jobs",
            params={"status": "completed", "limit": 10, "offset": 0},
        )
        assert filtered_jobs_response.status_code == 200
        assert filtered_jobs_response.json()["jobs"][0]["status"] == "completed"

        status_response = await client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["job"]["status"] == "completed"

        filtered_events_response = await client.get(
            f"/jobs/{job_id}/events",
            params={"event_type": "tool_call"},
        )
        assert filtered_events_response.status_code == 200
        filtered_events = filtered_events_response.json()["events"]
        assert len(filtered_events) == 1
        assert filtered_events[0]["event_type"] == "tool_call"


@pytest.mark.asyncio
async def test_event_stream_replays_and_resumes(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"})
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        job_id = (await client.post(f"/sessions/{session_id}/prompts", json={"prompt": "go"})).json()["job"]["id"]

        async with client.stream("GET", f"/jobs/{job_id}/events/stream") as response:
            assert response.status_code == 200
            lines = [line async for line in response.aiter_lines() if line]

        ids = [line.removeprefix("id: ") for line in lines if line.startswith("id: ")]
        events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: ")]
        assert any(event["event_type"] == "model_output" and event["payload"].get("stream") for event in events)
        assert any(event["event_type"] == "tool_call" for event in events)
        assert events[-1]["event_type"] == "completion"

        resume_cursor = ids[0]
        async with client.stream(
            "GET",
            f"/jobs/{job_id}/events/stream",
            params={"after": resume_cursor},
        ) as resumed_response:
            assert resumed_response.status_code == 200
            resumed_lines = [line async for line in resumed_response.aiter_lines() if line]

        resumed_ids = [line.removeprefix("id: ") for line in resumed_lines if line.startswith("id: ")]
        resumed_events = [
            json.loads(line.removeprefix("data: ")) for line in resumed_lines if line.startswith("data: ")
        ]
        assert resumed_ids
        assert all(event_id > resume_cursor for event_id in resumed_ids)
        assert any(event["event_type"] == "completion" for event in resumed_events)
