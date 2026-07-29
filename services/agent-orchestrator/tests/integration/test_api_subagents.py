from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.display_names import generate_agent_name
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

from .api_test_support import (
    INTEGRATION_ENABLED_PROVIDER_IDS,
    INTEGRATION_MODEL_CONFIG,
    FakeMcp,
    SpawnSubagentBifrost,
)


@pytest.mark.asyncio
async def test_spawn_subagent_creates_child_and_emits_events(tmp_path: Path):
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
            ENABLED_PROVIDER_IDS=INTEGRATION_ENABLED_PROVIDER_IDS,
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
                    json=INTEGRATION_MODEL_CONFIG,
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
                # A generated display name, seeded on the child session's own id —
                # not a slice of the spawn's prompt.
                assert started_event["payload"]["name"] == generate_agent_name(
                    started_event["payload"]["child_session_id"], "subagent-task"
                )
                assert started_event["payload"]["name"] != "subagent-task"

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

                child_job_id = started_event["payload"]["child_job_id"]
                child_job_response = await client.get(f"/jobs/{child_job_id}")
                assert child_job_response.status_code == 200
                child_tool_names = {
                    tool["name"]
                    for tool in child_job_response.json()["job"]["available_tools"]
                }
                assert "wait_for_subagent" not in child_tool_names
                assert "spawn_subagent" not in child_tool_names

                sessions_response = await client.get("/sessions")
                assert sessions_response.status_code == 200
                listed_session_ids = [
                    session["id"] for session in sessions_response.json()["sessions"]
                ]
                assert session_id in listed_session_ids
                assert child_session_id not in listed_session_ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_spawn_subagent_inherits_enabled_mcps(tmp_path: Path):
    """Test that child sessions inherit enabled MCPs from parent session."""
    database_path = tmp_path / "subagent-mcp-inherit.sqlite3"
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
            ENABLED_PROVIDER_IDS=INTEGRATION_ENABLED_PROVIDER_IDS,
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
                # Create parent session
                parent_response = await client.post(
                    "/sessions", json={"name": "parent-mcp-test"}
                )
                parent_session_id = parent_response.json()["session"]["id"]
                await client.put(
                    f"/sessions/{parent_session_id}/model-config",
                    json=INTEGRATION_MODEL_CONFIG,
                )

                # Add a custom MCP to registry
                await client.post(
                    "/mcps",
                    json={
                        "name": "custom-mcp",
                        "transport": "streamable-http",
                        "server_url": "http://custom/mcp",
                    },
                )

                # Enable the custom MCP for parent session
                await client.patch(
                    f"/sessions/{parent_session_id}/mcps/custom-mcp",
                    json={"enabled": True},
                )

                # Verify parent has the MCP enabled
                parent_mcps = await client.get(f"/sessions/{parent_session_id}/mcps")
                parent_mcp_list = parent_mcps.json()["mcps"]
                custom_mcp = next(
                    m for m in parent_mcp_list if m["name"] == "custom-mcp"
                )
                assert custom_mcp["enabled"] is True

                # Submit prompt to spawn a subagent
                prompt_response = await client.post(
                    f"/sessions/{parent_session_id}/prompts",
                    json={"prompt": "run a subagent task"},
                )
                assert prompt_response.status_code == 202
                job_id = prompt_response.json()["job"]["id"]

                # Wait for completion
                for _ in range(120):
                    job_response = await client.get(f"/jobs/{job_id}")
                    status = job_response.json()["job"]["status"]
                    if status in ("completed", "failed"):
                        break
                    await asyncio.sleep(0.1)

                # Get child session from events
                job = job_response.json()["job"]
                started_event = next(
                    e for e in job["events"] if e["event_type"] == "subagent_started"
                )
                child_session_id = started_event["payload"]["child_session_id"]

                # Wait for child to complete
                for _ in range(20):
                    child_response = await client.get(f"/sessions/{child_session_id}")
                    child_session = child_response.json()["session"]
                    if child_session["status"] == "terminated":
                        break
                    await asyncio.sleep(0.05)

                # Verify child session inherited the enabled MCP
                child_mcps = await client.get(f"/sessions/{child_session_id}/mcps")
                child_mcp_list = child_mcps.json()["mcps"]
                child_custom_mcp = next(
                    (m for m in child_mcp_list if m["name"] == "custom-mcp"), None
                )
                assert child_custom_mcp is not None
                assert child_custom_mcp["enabled"] is True
    finally:
        await engine.dispose()
