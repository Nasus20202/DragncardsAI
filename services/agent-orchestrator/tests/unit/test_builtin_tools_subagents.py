from __future__ import annotations

import asyncio

import pytest

from agent_orchestrator.runtime.builtin_tools import (
    make_spawn_subagent_handler,
    make_wait_for_subagent_handler,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import (
    await_job_event,
    live_event_bus,
    make_job,
    repository,
)


@pytest.mark.asyncio
async def test_spawn_subagent_returns_immediately_with_child_job_id(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    scheduled: list[str] = []

    async def fake_schedule(child_job_id: str):
        scheduled.append(child_job_id)
        await live_event_bus.publish(child_job_id, "completion", {"text": "done"})

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        skill_registry=SkillRegistry(()),
        schedule_child_fn=fake_schedule,
    )

    result = await handler({"prompt": "do the thing"})

    assert result["is_error"] is False
    text = result["content"][0]["text"]
    assert "child_job_id" in text
    assert "name" in text
    assert "do the thing" in text

    events = await repository.list_events(parent_job.id)
    event_types = [e.event_type for e in events]
    assert "subagent_started" in event_types

    started = next(e for e in events if e.event_type == "subagent_started")
    assert started.payload_json["name"] == "do the thing"

    await await_job_event(repository, parent_job.id, "subagent_completed")
    assert scheduled


@pytest.mark.asyncio
async def test_spawn_subagent_child_failure_emitted_async(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    async def fake_schedule_fail(child_job_id: str):
        await live_event_bus.publish(child_job_id, "failure", {"error": "boom"})

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        skill_registry=SkillRegistry(()),
        schedule_child_fn=fake_schedule_fail,
    )

    result = await handler({"prompt": "fail please"})

    assert result["is_error"] is False
    assert "child_job_id" in result["content"][0]["text"]

    events = await repository.list_events(parent_job.id)
    assert "subagent_started" in [e.event_type for e in events]
    await await_job_event(repository, parent_job.id, "subagent_failed")


@pytest.mark.asyncio
async def test_spawn_subagent_blocked_for_child_job(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("s", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hi", metadata_json={}, max_attempts=1
    )
    assert job is not None

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        job=make_job(parent_job_id="some-parent-id", job_type="prompt"),
        skill_registry=SkillRegistry(()),
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
    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    async def fake_schedule(child_job_id: str):
        await live_event_bus.publish(child_job_id, "completion", {})

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        skill_registry=SkillRegistry(()),
        schedule_child_fn=fake_schedule,
    )

    prompt = "Analyse the game state and recommend the best card to play"
    result = await handler({"prompt": prompt})
    assert result["is_error"] is False

    started = await await_job_event(repository, parent_job.id, "subagent_started")
    child_session_id = started.payload_json["child_session_id"]
    child_session = await repository.get_session(child_session_id)
    assert child_session is not None
    assert child_session.name == prompt[:50]


@pytest.mark.asyncio
async def test_spawn_subagent_requires_prompt(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    parent_session = await repository.create_session("parent", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    handler = make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=parent_session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        skill_registry=SkillRegistry(()),
    )

    result = await handler({})

    assert result["is_error"] is True
    assert result["content"][0]["text"] == "prompt is required."


@pytest.mark.asyncio
async def test_wait_for_subagent_requires_child_job_id(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    handler = make_wait_for_subagent_handler(
        live_event_bus=live_event_bus,
        repository=repository,
    )

    result = await handler({})

    assert result["is_error"] is True
    assert result["content"][0]["text"] == "child_job_id is required."


@pytest.mark.asyncio
async def test_wait_for_subagent_returns_error_for_missing_job(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    handler = make_wait_for_subagent_handler(
        live_event_bus=live_event_bus,
        repository=repository,
    )

    result = await handler({"child_job_id": "missing-job"})

    assert result["is_error"] is True
    assert "No job found" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wait_for_subagent_returns_completed_result_without_subscribing(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("child", {})
    child_job = await repository.enqueue_prompt_job(
        session.id, prompt="done", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.claim_next_job()
    await repository.mark_job_completed(child_job.id, "child output")

    handler = make_wait_for_subagent_handler(
        live_event_bus=live_event_bus,
        repository=repository,
    )

    result = await handler({"child_job_id": child_job.id})

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "child output"


@pytest.mark.asyncio
async def test_wait_for_subagent_returns_error_for_terminal_failure_status(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("child", {})
    child_job = await repository.enqueue_prompt_job(
        session.id, prompt="fail", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.claim_next_job()
    await repository.mark_job_failed(
        child_job.id,
        error_code="runtime_error",
        error_message="boom",
        retryable=False,
    )

    handler = make_wait_for_subagent_handler(
        live_event_bus=live_event_bus,
        repository=repository,
    )

    result = await handler({"child_job_id": child_job.id})

    assert result["is_error"] is True
    assert result["content"][0]["text"] == (
        f"Subagent {child_job.id} failed — runtime_error: boom"
    )


@pytest.mark.asyncio
async def test_wait_for_subagent_waits_for_completion_event(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("child", {})
    child_job = await repository.enqueue_prompt_job(
        session.id, prompt="wait", metadata_json={}, max_attempts=1
    )
    assert child_job is not None

    handler = make_wait_for_subagent_handler(
        live_event_bus=live_event_bus,
        repository=repository,
    )

    async def publish_completion():
        await asyncio.sleep(0.01)
        await live_event_bus.publish(child_job.id, "completion", {"text": "done async"})

    publish_task = asyncio.create_task(publish_completion())
    try:
        result = await handler({"child_job_id": child_job.id})
    finally:
        await publish_task

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "done async"


@pytest.mark.asyncio
async def test_wait_for_subagent_returns_event_reason_on_failure(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await repository.create_session("child", {})
    child_job = await repository.enqueue_prompt_job(
        session.id, prompt="wait", metadata_json={}, max_attempts=1
    )
    assert child_job is not None

    handler = make_wait_for_subagent_handler(
        live_event_bus=live_event_bus,
        repository=repository,
    )

    async def publish_failure():
        await asyncio.sleep(0.01)
        await live_event_bus.publish(
            child_job.id,
            "failure",
            {"code": "execution_error", "message": "boom", "retryable": False},
        )

    publish_task = asyncio.create_task(publish_failure())
    try:
        result = await handler({"child_job_id": child_job.id})
    finally:
        await publish_task

    assert result["is_error"] is True
    assert result["content"][0]["text"] == (
        f"Subagent {child_job.id} failed — execution_error: boom"
    )
