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
from agent_orchestrator.runtime.skills import SkillRegistry
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
            session_id = extract_created_session_id(messages)
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


def extract_created_session_id(messages: list[dict[str, object]]) -> str:
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


async def require_live_game_service() -> None:
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


@pytest.fixture
async def live_game_service_available():
    await require_live_game_service()
