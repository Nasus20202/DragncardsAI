from __future__ import annotations

import asyncio
import json
import os
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

GAME_SERVICE_HTTP_URL = os.environ.get("GAME_SERVICE_HTTP_URL", "http://localhost:4001")
GAME_SERVICE_MCP_URL = os.environ.get(
    "GAME_SERVICE_MCP_URL", f"{GAME_SERVICE_HTTP_URL}/mcp/"
)
DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")


class FakeBifrost:
    def __init__(self):
        self.healthy = True
        self.responses = [
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(id="call-1", name="game-service_next_step", arguments={})
                ],
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


class LiveGameServiceBifrost:
    def __init__(self):
        self.healthy = True
        self._round = 0

    async def health(self) -> bool:
        return self.healthy

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return None

    async def chat_completion(self, *args, **kwargs):
        await asyncio.sleep(0.02)
        messages = args[2] if len(args) > 2 else kwargs.get("messages") or []

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
            session_id = _extract_created_session_id(messages)
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-step",
                        name="game-service_execute_action",
                        arguments={
                            "session_id": session_id,
                            "action": {"type": "next_step"},
                        },
                    )
                ],
                raw={},
            )

        return ChatResponse(content="Advanced the game", tool_calls=[], raw={})


def _extract_created_session_id(messages: list[dict[str, object]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        tool_result = json.loads(content)
        parts = tool_result.get("content") or []
        if not parts:
            continue
        text = parts[0].get("text")
        if not isinstance(text, str):
            continue
        payload = json.loads(text)
        session = payload.get("session") or {}
        session_id = session.get("session_id")
        if isinstance(session_id, str):
            return session_id
    raise AssertionError("Could not extract created session_id from tool messages")


async def _require_live_game_service() -> None:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            game_service_resp = await client.get(f"{GAME_SERVICE_HTTP_URL}/health")
            dragncards_resp = await client.get(DRAGNCARDS_HTTP_URL)
    except httpx.HTTPError as exc:
        pytest.skip(f"Live game-service stack unavailable: {exc}")

    if game_service_resp.status_code != 200:
        pytest.skip(f"game-service not reachable at {GAME_SERVICE_HTTP_URL}")
    if dragncards_resp.status_code >= 500:
        pytest.skip(f"DragnCards backend not healthy at {DRAGNCARDS_HTTP_URL}")


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
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            SKILL_ROOTS=str(skill_root),
        ),
        repository=repository,
        bifrost_client=FakeBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeMcp(),
        skill_registry=SkillRegistry((skill_root,)),
    )
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.fixture
async def real_mcp_app(tmp_path: Path):
    database_path = tmp_path / "integration-real-mcp.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    app = create_app(
        settings=Settings(database_url=f"sqlite+aiosqlite:///{database_path}"),
        repository=repository,
        bifrost_client=LiveGameServiceBifrost(),
        live_event_bus=InMemoryLiveEventBus(),
    )
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_run_completes_background_job(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]

        sessions_response = await client.get(
            "/sessions", params={"limit": 10, "offset": 0}
        )
        assert sessions_response.status_code == 200
        assert sessions_response.json()["page"]["total"] >= 1

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"}
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        tools_response = await client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        tools = tools_response.json()["tools"]
        tool_names = [tool["name"] for tool in tools]
        assert "load_skill" in tool_names
        assert "load_skill_reference" in tool_names
        assert "spawn_subagent" in tool_names
        assert "wait_for_subagent" in tool_names
        game_service_tool = next(
            tool for tool in tools if tool["name"] == "game-service_next_step"
        )
        assert game_service_tool["server_url"] == "http://game-service/mcp/"

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
        available_tool_names = [tool["name"] for tool in job["available_tools"]]
        assert "load_skill" in available_tool_names
        assert "load_skill_reference" in available_tool_names
        assert "spawn_subagent" in available_tool_names
        assert "wait_for_subagent" in available_tool_names
        assert "game-service_next_step" in available_tool_names
        assert job["latest_event_type"] == "completion"
        assert any(event["event_type"] == "tool_result" for event in job["events"])
        assert not any(
            event["event_type"] == "model_output" and event["payload"].get("stream")
            for event in job["events"]
        )
        tool_call_event = next(
            event for event in job["events"] if event["event_type"] == "tool_call"
        )
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"}
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        job_id = (
            await client.post(f"/sessions/{session_id}/prompts", json={"prompt": "go"})
        ).json()["job"]["id"]

        async with client.stream("GET", f"/jobs/{job_id}/events/stream") as response:
            assert response.status_code == 200
            lines = [line async for line in response.aiter_lines() if line]

        ids = [line.removeprefix("id: ") for line in lines if line.startswith("id: ")]
        events = [
            json.loads(line.removeprefix("data: "))
            for line in lines
            if line.startswith("data: ")
        ]
        assert any(
            event["event_type"] == "model_output" and event["payload"].get("stream")
            for event in events
        )
        assert any(event["event_type"] == "tool_call" for event in events)
        assert events[-1]["event_type"] == "completion"

        resume_cursor = ids[0]
        async with client.stream(
            "GET",
            f"/jobs/{job_id}/events/stream",
            params={"after": resume_cursor},
        ) as resumed_response:
            assert resumed_response.status_code == 200
            resumed_lines = [
                line async for line in resumed_response.aiter_lines() if line
            ]

        resumed_ids = [
            line.removeprefix("id: ")
            for line in resumed_lines
            if line.startswith("id: ")
        ]
        resumed_events = [
            json.loads(line.removeprefix("data: "))
            for line in resumed_lines
            if line.startswith("data: ")
        ]
        assert resumed_ids
        assert all(event_id > resume_cursor for event_id in resumed_ids)
        assert any(event["event_type"] == "completion" for event in resumed_events)


@pytest.mark.asyncio
async def test_prompt_run_uses_real_game_service_mcp(real_mcp_app):
    await _require_live_game_service()

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


class LoadSkillBifrost(FakeBifrost):
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
    """Integration test: session with skill assigned, agent calls load_skill, skill_loaded event appears."""
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
            # This is the child job — complete immediately
            if on_delta:
                await on_delta(ChatDelta(content="child done"))
            return ChatResponse(content="child done", tool_calls=[], raw={})

        if self._call_count == 1:
            # Parent first round: call spawn_subagent
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

        # Parent second round: after spawn_subagent returns
        if on_delta:
            await on_delta(ChatDelta(content="parent done"))
        return ChatResponse(content="parent done", tool_calls=[], raw={})


@pytest.mark.asyncio
async def test_spawn_subagent_creates_child_and_emits_events(tmp_path: Path):
    """Integration: master job calls spawn_subagent; child created/terminated; events on parent job."""
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
                create_response = await client.post(
                    "/sessions", json={"name": "subagent-test"}
                )
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

                # Verify name is present in subagent_started
                started_event = next(
                    e for e in events if e["event_type"] == "subagent_started"
                )
                assert "name" in started_event["payload"]
                assert started_event["payload"]["name"] == "subagent-task"

                # subagent_completed may arrive slightly after parent job completes (background task)
                # Give it a short grace period
                for _ in range(20):
                    job_response = await client.get(f"/jobs/{job_id}")
                    events = job_response.json()["job"]["events"]
                    if any(e["event_type"] == "subagent_completed" for e in events):
                        break
                    await asyncio.sleep(0.05)

                event_types = [e["event_type"] for e in events]
                assert "subagent_completed" in event_types

                # Verify child session was terminated
                child_session_id = started_event["payload"]["child_session_id"]
                child_session = None
                for _ in range(20):
                    child_session_response = await client.get(
                        f"/sessions/{child_session_id}"
                    )
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
