from __future__ import annotations

from pathlib import Path

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

from .app_test_support import FakeBifrostClient, FakeMcpClient


@pytest.mark.asyncio
async def test_startup_updates_default_game_service_mcp_url_from_settings(
    tmp_path: Path,
):
    database_path = tmp_path / "startup.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    await repository.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp/",
        headers_json=None,
        custom=True,
    )

    app = create_app(
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            bifrost_url="http://bifrost",
            bifrost_api_key="dummy",
            SKILL_ROOTS=str(skill_root),
            ENABLED_PROVIDER_IDS="openai",
            GAME_SERVICE_MCP_URL="http://game-service:8000/mcp",
        ),
        repository=repository,
        bifrost_client=FakeBifrostClient(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeMcpClient(),
        skill_registry=SkillRegistry((skill_root,)),
    )

    async with app.router.lifespan_context(app):
        updated = await repository.get_mcp_registry("game-service")
        assert updated is not None
        assert updated.transport == "streamable-http"
        assert updated.server_url == "http://game-service:8000/mcp/"
        assert updated.custom is False
        assert updated.headers_json == {}

    await engine.dispose()
