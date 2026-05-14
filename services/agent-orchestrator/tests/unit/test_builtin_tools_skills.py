from __future__ import annotations

from typing import Any

import pytest

from agent_orchestrator.runtime.builtin_tools import (
    make_load_skill_handler,
    make_load_skill_reference_handler,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import (
    live_event_bus,
    make_skill_assignment,
    repository,
    skill_registry,
)


@pytest.mark.asyncio
async def test_load_skill_success_returns_content(
    repository: Repository,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("test", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None

    handler = make_load_skill_handler(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        skill_assignments=[make_skill_assignment("demo-skill")],
    )

    result = await handler({"skill_name": "demo-skill"})

    assert result["is_error"] is False
    content_text = result["content"][0]["text"]
    assert "Follow the demo instructions." in content_text
    assert "## Available references" in content_text
    assert "- docs/tips.md" in content_text
    assert "- reference/guide.md" in content_text
    assert "Guide content." not in content_text


@pytest.mark.asyncio
async def test_load_skill_emits_skill_loaded_event_with_reference_count(
    repository: Repository,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("test", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None

    handler = make_load_skill_handler(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        skill_assignments=[make_skill_assignment("demo-skill")],
    )

    await handler({"skill_name": "demo-skill"})

    events = await repository.list_events(job.id)
    skill_loaded_events = [e for e in events if e.event_type == "skill_loaded"]
    assert len(skill_loaded_events) == 1
    payload = skill_loaded_events[0].payload_json
    assert payload["skill_name"] == "demo-skill"
    assert payload["reference_file_count"] == 2


@pytest.mark.asyncio
async def test_load_skill_unassigned_returns_error_without_event(
    repository: Repository,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("test", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None

    assignments: list[Any] = []
    handler = make_load_skill_handler(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        skill_assignments=assignments,
    )

    result = await handler({"skill_name": "demo-skill"})

    assert result["is_error"] is True
    assert "not assigned" in result["content"][0]["text"]

    events = await repository.list_events(job.id)
    skill_loaded_events = [e for e in events if e.event_type == "skill_loaded"]
    assert len(skill_loaded_events) == 0


@pytest.mark.asyncio
async def test_load_skill_returns_error_when_content_is_missing(
    repository: Repository,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("test", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None

    handler = make_load_skill_handler(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        skill_assignments=[make_skill_assignment("missing-skill")],
    )

    result = await handler({"skill_name": "missing-skill"})

    assert result["is_error"] is True
    assert "could not be loaded" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_load_skill_reference_returns_named_reference_content(
    skill_registry: SkillRegistry,
):
    handler = make_load_skill_reference_handler(
        skill_registry=skill_registry,
        skill_assignments=[make_skill_assignment("demo-skill")],
    )

    result = await handler(
        {"skill_name": "demo-skill", "reference_name": "reference/guide.md"}
    )

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "Guide content."


@pytest.mark.asyncio
async def test_load_skill_reference_rejects_missing_or_unassigned_reference(
    skill_registry: SkillRegistry,
):
    handler = make_load_skill_reference_handler(
        skill_registry=skill_registry,
        skill_assignments=[],
    )

    unassigned = await handler(
        {"skill_name": "demo-skill", "reference_name": "reference/guide.md"}
    )
    assert unassigned["is_error"] is True
    assert "not assigned" in unassigned["content"][0]["text"]

    assigned_handler = make_load_skill_reference_handler(
        skill_registry=skill_registry,
        skill_assignments=[make_skill_assignment("demo-skill")],
    )
    missing = await assigned_handler(
        {"skill_name": "demo-skill", "reference_name": "missing.md"}
    )
    assert missing["is_error"] is True
    assert "could not be loaded" in missing["content"][0]["text"]


@pytest.mark.asyncio
async def test_load_skill_reference_requires_reference_name(
    skill_registry: SkillRegistry,
):
    handler = make_load_skill_reference_handler(
        skill_registry=skill_registry,
        skill_assignments=[make_skill_assignment("demo-skill")],
    )

    result = await handler({"skill_name": "demo-skill"})

    assert result["is_error"] is True
    assert result["content"][0]["text"] == "reference_name is required."
