from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

from .api_test_support import (
    INTEGRATION_ENABLED_PROVIDER_IDS,
    INTEGRATION_MODEL_CONFIG,
    FakeMcp,
    LoadSkillBifrost,
)


@pytest.mark.asyncio
async def test_load_skill_emits_skill_loaded_event(tmp_path: Path):
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
                    "/sessions", json={"name": "skill-test"}
                )
                session_id = create_response.json()["session"]["id"]
                await client.put(
                    f"/sessions/{session_id}/model-config",
                    json=INTEGRATION_MODEL_CONFIG,
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


@pytest.mark.asyncio
async def test_skill_assignment_list_and_remove_lifecycle(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post(
            "/sessions", json={"name": "skill-lifecycle"}
        )
        session_id = create_response.json()["session"]["id"]

        assign_response = await client.post(
            f"/sessions/{session_id}/skills",
            json={"skill_name": "test-skill"},
        )
        list_response = await client.get(f"/sessions/{session_id}/skills")
        remove_response = await client.delete(
            f"/sessions/{session_id}/skills/test-skill"
        )
        list_after_remove_response = await client.get(f"/sessions/{session_id}/skills")
        remove_again_response = await client.delete(
            f"/sessions/{session_id}/skills/test-skill"
        )

    assert assign_response.status_code == 201
    assert list_response.status_code == 200
    assert [skill["skill_name"] for skill in list_response.json()["skills"]] == [
        "test-skill"
    ]
    assert remove_response.status_code == 204
    assert list_after_remove_response.status_code == 200
    assert list_after_remove_response.json() == {"skills": []}
    # Disabling an already-disabled skill is a no-op, not an error.
    assert remove_again_response.status_code == 204
