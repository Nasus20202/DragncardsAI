from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

GAME_SERVICE_HTTP_URL = os.environ.get("GAME_SERVICE_HTTP_URL", "http://localhost:4001")
GAME_SERVICE_MCP_URL = os.environ.get(
    "GAME_SERVICE_MCP_URL", f"{GAME_SERVICE_HTTP_URL}/mcp/"
)


class FakeGameFlowMcp:
    def __init__(self):
        self.created_session_id = "game-session-fake-001"
        self.step_count = 0

    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="create_game",
                description="Create a game session",
                input_schema={
                    "type": "object",
                    "properties": {"plugin_name": {"type": "string"}},
                    "required": ["plugin_name"],
                },
            ),
            McpToolDefinition(
                name="execute_action",
                description="Execute action in game session",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "action": {"type": "object"},
                    },
                    "required": ["session_id", "action"],
                },
            ),
        ]

    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        if tool_name == "create_game":
            payload = {
                "session": {
                    "session_id": self.created_session_id,
                    "plugin_name": arguments.get("plugin_name"),
                    "room_slug": "fake-room",
                }
            }
            return {
                "is_error": False,
                "content": [{"type": "text", "text": json.dumps(payload)}],
            }

        if tool_name == "execute_action":
            self.step_count += 1
            payload = {
                "session_id": arguments.get("session_id"),
                "state": {"game": {"stepId": f"step-{self.step_count}"}},
            }
            return {
                "is_error": False,
                "content": [{"type": "text", "text": json.dumps(payload)}],
            }

        raise AssertionError(f"Unexpected tool call: {tool_name}")


class FakeGameFlowErrorMcp(FakeGameFlowMcp):
    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        if tool_name == "execute_action":
            return {
                "is_error": True,
                "content": [{"type": "text", "text": "failed to advance game"}],
            }
        return await super().call_tool(server_url, tool_name, arguments, headers=headers)


class FakeGameFlowBifrost:
    def __init__(self):
        self._round = 0

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return None

    async def chat_completion(self, *args, **kwargs):
        await asyncio.sleep(0.01)
        on_delta = kwargs.get("on_delta")

        if self._round == 0:
            self._round += 1
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-create",
                        name="game-service_create_game",
                        arguments={"plugin_name": "marvel-champions"},
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
                        id="call-step",
                        name="game-service_execute_action",
                        arguments={
                            "session_id": "game-session-fake-001",
                            "action": {"type": "next_step"},
                        },
                    )
                ],
                raw={},
            )

        if on_delta is not None:
            from agent_orchestrator.integrations.bifrost import ChatDelta

            await on_delta(ChatDelta(content="Advanced fake game"))
        return ChatResponse(content="Advanced fake game", tool_calls=[], raw={})


class FakeGameFlowErrorRecoveryBifrost(FakeGameFlowBifrost):
    async def chat_completion(self, *args, **kwargs):
        response = await super().chat_completion(*args, **kwargs)
        if self._round == 2 and not response.tool_calls:
            on_delta = kwargs.get("on_delta")
            if on_delta is not None:
                from agent_orchestrator.integrations.bifrost import ChatDelta

                await on_delta(ChatDelta(content="Could not advance fake game"))
            return ChatResponse(
                content="Could not advance fake game", tool_calls=[], raw={}
            )
        return response


@pytest.fixture
async def fake_game_orchestrator_app(tmp_path: Path):
    database_path = tmp_path / "integration-game-flow.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    app = create_app(
        settings=Settings(database_url=f"sqlite+aiosqlite:///{database_path}"),
        repository=repository,
        bifrost_client=FakeGameFlowBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeGameFlowMcp(),
    )
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.fixture
async def fake_game_orchestrator_error_app(tmp_path: Path):
    database_path = tmp_path / "integration-game-flow-error.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    app = create_app(
        settings=Settings(database_url=f"sqlite+aiosqlite:///{database_path}"),
        repository=repository,
        bifrost_client=FakeGameFlowErrorRecoveryBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeGameFlowErrorMcp(),
    )
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_run_orchestrates_game_service_tools(fake_game_orchestrator_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake_game_orchestrator_app),
        base_url="http://test",
    ) as client:
        create_response = await client.post("/sessions", json={"name": "game-flow-demo"})
        session_id = create_response.json()["session"]["id"]

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        tools_response = await client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        tools = {tool["name"] for tool in tools_response.json()["tools"]}
        assert "game-service_create_game" in tools
        assert "game-service_execute_action" in tools

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "Create and advance a game"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(60):
            job_response = await client.get(f"/jobs/{job_id}")
            status = job_response.json()["job"]["status"]
            if status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.05)

        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "Advanced fake game"

        tool_call_events = [e for e in job["events"] if e["event_type"] == "tool_call"]
        tool_result_events = [e for e in job["events"] if e["event_type"] == "tool_result"]

        assert [event["payload"]["tool_name"] for event in tool_call_events] == [
            "create_game",
            "execute_action",
        ]
        assert {event["payload"]["assignment"] for event in tool_call_events} == {
            "game-service"
        }
        assert len(tool_result_events) == 2

        create_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "create_game"
        )
        execute_call = next(
            event
            for event in tool_call_events
            if event["payload"]["tool_name"] == "execute_action"
        )
        execute_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "execute_action"
        )

        created_payload = json.loads(create_result["payload"]["result"]["content"][0]["text"])
        created_session_id = created_payload["session"]["session_id"]
        assert (
            execute_call["payload"]["arguments"]["session_id"] == created_session_id
        )

        execute_payload = json.loads(execute_result["payload"]["result"]["content"][0]["text"])
        assert execute_payload["session_id"] == created_session_id


@pytest.mark.asyncio
async def test_prompt_run_records_mcp_tool_errors(fake_game_orchestrator_error_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake_game_orchestrator_error_app),
        base_url="http://test",
    ) as client:
        create_response = await client.post("/sessions", json={"name": "game-flow-error"})
        session_id = create_response.json()["session"]["id"]

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "Create and advance a game"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(60):
            job_response = await client.get(f"/jobs/{job_id}")
            status = job_response.json()["job"]["status"]
            if status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.05)

        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "Could not advance fake game"

        tool_result_events = [e for e in job["events"] if e["event_type"] == "tool_result"]
        assert len(tool_result_events) == 2

        create_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "create_game"
        )
        execute_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "execute_action"
        )

        assert create_result["payload"]["is_error"] is False
        assert execute_result["payload"]["is_error"] is True
        assert execute_result["payload"]["result"]["content"][0]["text"] == (
            "failed to advance game"
        )


@pytest.mark.asyncio
async def test_prompt_run_uses_real_game_service_mcp(
    real_mcp_app, live_game_service_available
):
    del live_game_service_available

    created_game_session_id = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=real_mcp_app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "live-mcp-demo"})
        session_id = create_response.json()["session"]["id"]

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": GAME_SERVICE_MCP_URL},
        )

        tools_response = await client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        tool_names = {tool["name"] for tool in tools_response.json()["tools"]}
        assert "game-service_create_game" in tool_names
        assert "game-service_execute_action" in tool_names

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "Create a game and advance it by one step"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(120):
            job_response = await client.get(f"/jobs/{job_id}")
            if job_response.json()["job"]["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.1)

        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "Advanced the game"

        tool_call_events = [
            event for event in job["events"] if event["event_type"] == "tool_call"
        ]
        tool_result_events = [
            event for event in job["events"] if event["event_type"] == "tool_result"
        ]
        assert len(tool_call_events) == 2
        assert len(tool_result_events) == 2
        assert {event["payload"]["tool_name"] for event in tool_call_events} == {
            "create_game",
            "execute_action",
        }
        assert all(
            event["payload"]["server_url"] == GAME_SERVICE_MCP_URL
            for event in tool_call_events
        )

        create_game_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "create_game"
        )
        create_game_payload = json.loads(
            create_game_result["payload"]["result"]["content"][0]["text"]
        )
        created_game_session_id = create_game_payload["session"]["session_id"]

        execute_action_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "execute_action"
        )
        execute_action_payload = json.loads(
            execute_action_result["payload"]["result"]["content"][0]["text"]
        )
        assert execute_action_payload["session_id"] == created_game_session_id
        assert "game" in execute_action_payload["state"]

    try:
        async with httpx.AsyncClient(timeout=5.0) as live_client:
            games_response = await live_client.get(f"{GAME_SERVICE_HTTP_URL}/games")
            assert games_response.status_code == 200
            ids = [item["session_id"] for item in games_response.json()["sessions"]]
            assert created_game_session_id in ids
    finally:
        if created_game_session_id is not None:
            async with httpx.AsyncClient(timeout=5.0) as live_client:
                await live_client.delete(
                    f"{GAME_SERVICE_HTTP_URL}/games/{created_game_session_id}"
                )
