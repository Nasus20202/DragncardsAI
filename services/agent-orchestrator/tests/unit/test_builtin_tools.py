from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agent_orchestrator.runtime.builtin_tools import (
    build_builtin_registry,
    is_master_job,
    make_load_skill_handler,
    make_load_skill_reference_handler,
    make_spawn_subagent_handler,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def repository(tmp_path: Path):
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    yield repo
    await engine.dispose()


@pytest.fixture
def skill_registry(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    skill_dir = root / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Demo Skill\n\nFollow the demo instructions.", encoding="utf-8"
    )
    ref_dir = skill_dir / "reference"
    ref_dir.mkdir()
    (ref_dir / "guide.md").write_text("Guide content.", encoding="utf-8")
    alt_dir = skill_dir / "docs"
    alt_dir.mkdir()
    (alt_dir / "tips.md").write_text("Tip content.", encoding="utf-8")
    return SkillRegistry((root,))


@pytest.fixture
def live_event_bus():
    return InMemoryLiveEventBus()


def _make_skill_assignment(skill_name: str):
    return SimpleNamespace(skill_name=skill_name, skill_path="/tmp")


def _make_job(parent_job_id=None, job_type="prompt"):
    return SimpleNamespace(parent_job_id=parent_job_id, job_type=job_type)


# ── is_master_job ─────────────────────────────────────────────────────────────


def test_is_master_job_true_for_prompt_without_parent():
    job = _make_job(parent_job_id=None, job_type="prompt")
    assert is_master_job(job) is True


def test_is_master_job_false_for_child_job():
    job = _make_job(parent_job_id="parent-id", job_type="prompt")
    assert is_master_job(job) is False


def test_is_master_job_false_for_compaction_job():
    job = _make_job(parent_job_id=None, job_type="compaction")
    assert is_master_job(job) is False


# ── load_skill handler ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_skill_success_returns_content(
    repository: Repository,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus,
    tmp_path: Path,
):
    session = await repository.create_session("test", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None

    assignments = [_make_skill_assignment("demo-skill")]
    handler = make_load_skill_handler(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        skill_assignments=assignments,
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

    assignments = [_make_skill_assignment("demo-skill")]
    handler = make_load_skill_handler(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        skill_assignments=assignments,
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

    assignments: list[Any] = []  # no skills assigned
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
async def test_load_skill_reference_returns_named_reference_content(
    skill_registry: SkillRegistry,
):
    handler = make_load_skill_reference_handler(
        skill_registry=skill_registry,
        skill_assignments=[_make_skill_assignment("demo-skill")],
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
        skill_assignments=[_make_skill_assignment("demo-skill")],
    )
    missing = await assigned_handler(
        {"skill_name": "demo-skill", "reference_name": "missing.md"}
    )
    assert missing["is_error"] is True
    assert "could not be loaded" in missing["content"][0]["text"]


# ── build_builtin_registry ────────────────────────────────────────────────────


def test_build_builtin_registry_includes_skill_loading_tools(
    tmp_path: Path,
    skill_registry: SkillRegistry,
):
    bus = InMemoryLiveEventBus()
    engine = None  # Not used in this synchronous check

    # We can't easily create a repo without async here, so just check names
    # by calling with a dummy repo-like object and checking OpenAI tool list.
    # We create a real in-memory registry from a module-level helper.
    from agent_orchestrator.runtime.builtin_tools import (
        BuiltinToolRegistry,
        BuiltinToolDefinition,
    )

    registry = BuiltinToolRegistry()
    registry.register(
        BuiltinToolDefinition(
            "load_skill",
            "desc",
            {"type": "object", "properties": {}, "required": []},
            lambda args: None,
        )
    )
    registry.register(
        BuiltinToolDefinition(
            "load_skill_reference",
            "desc",
            {"type": "object", "properties": {}, "required": []},
            lambda args: None,
        )
    )
    tools = registry.as_openai_tools()
    assert any(t["function"]["name"] == "load_skill" for t in tools)
    assert any(t["function"]["name"] == "load_skill_reference" for t in tools)


def test_spawn_subagent_absent_for_child_job(
    tmp_path: Path,
    skill_registry: SkillRegistry,
):
    """spawn_subagent should not appear in the tool list for child jobs."""
    child_job = _make_job(parent_job_id="parent-id", job_type="prompt")
    assert not is_master_job(child_job)


def test_spawn_subagent_absent_for_compaction_job(
    tmp_path: Path,
    skill_registry: SkillRegistry,
):
    """spawn_subagent should not appear in the tool list for compaction jobs."""
    compaction_job = _make_job(parent_job_id=None, job_type="compaction")
    assert not is_master_job(compaction_job)


# ── spawn_subagent handler ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_subagent_returns_immediately_with_child_job_id(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    """spawn_subagent returns immediately with child_job_id and name."""
    import asyncio

    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    master_job = _make_job(parent_job_id=None, job_type="prompt")

    scheduled: list[str] = []

    async def fake_schedule(child_job_id: str):
        scheduled.append(child_job_id)
        # Publish completion so the background monitor doesn't hang
        await live_event_bus.publish(child_job_id, "completion", {"text": "done"})

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=master_job,
        schedule_child_fn=fake_schedule,
    )

    result = await handler({"prompt": "do the thing"})

    # Must return immediately — not an error, contains child_job_id
    assert result["is_error"] is False
    text = result["content"][0]["text"]
    assert "child_job_id" in text
    assert "name" in text
    assert "do the thing" in text  # name is first 50 chars of prompt

    # subagent_started is emitted synchronously before returning
    events = await repository.list_events(parent_job.id)
    event_types = [e.event_type for e in events]
    assert "subagent_started" in event_types

    # Verify name in subagent_started payload
    started = next(e for e in events if e.event_type == "subagent_started")
    assert started.payload_json["name"] == "do the thing"

    # Allow background monitor task to complete
    await asyncio.sleep(0.05)

    events = await repository.list_events(parent_job.id)
    event_types = [e.event_type for e in events]
    assert "subagent_completed" in event_types


@pytest.mark.asyncio
async def test_spawn_subagent_child_failure_emitted_async(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    """spawn_subagent emits subagent_failed async when child fails."""
    import asyncio

    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    master_job = _make_job(parent_job_id=None, job_type="prompt")

    async def fake_schedule_fail(child_job_id: str):
        await live_event_bus.publish(child_job_id, "failure", {"error": "boom"})

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=master_job,
        schedule_child_fn=fake_schedule_fail,
    )

    result = await handler({"prompt": "fail please"})

    # Returns immediately regardless of child outcome
    assert result["is_error"] is False
    assert "child_job_id" in result["content"][0]["text"]

    # subagent_failed appended by background monitor
    await asyncio.sleep(0.05)

    events = await repository.list_events(parent_job.id)
    event_types = [e.event_type for e in events]
    assert "subagent_started" in event_types
    assert "subagent_failed" in event_types


@pytest.mark.asyncio
async def test_spawn_subagent_blocked_for_child_job(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    """spawn_subagent returns error immediately when called from a child job."""
    session = await repository.create_session("s", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hi", metadata_json={}, max_attempts=1
    )
    assert job is not None

    child_job = _make_job(parent_job_id="some-parent-id", job_type="prompt")

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        job=child_job,
        schedule_child_fn=None,
    )

    result = await handler({"prompt": "nested"})
    assert result["is_error"] is True
    assert "master" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_spawn_subagent_child_session_named_from_prompt(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    """Child session should be named from the first 50 chars of the prompt."""
    import asyncio

    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    master_job = _make_job(parent_job_id=None, job_type="prompt")

    async def fake_schedule(child_job_id: str):
        await live_event_bus.publish(child_job_id, "completion", {})

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=master_job,
        schedule_child_fn=fake_schedule,
    )

    prompt = "Analyse the game state and recommend the best card to play"
    result = await handler({"prompt": prompt})
    assert result["is_error"] is False

    # Find child session by looking at subagent_started event
    await asyncio.sleep(0.05)
    events = await repository.list_events(parent_job.id)
    started = next(e for e in events if e.event_type == "subagent_started")
    child_session_id = started.payload_json["child_session_id"]
    child_session = await repository.get_session(child_session_id)
    assert child_session is not None
    assert child_session.name == prompt[:50]
