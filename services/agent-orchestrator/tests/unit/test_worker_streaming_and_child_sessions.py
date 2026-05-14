from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.worker import WorkerService
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.repository import Repository
from agent_orchestrator.runtime.skills import SkillRegistry

from .test_worker import FakeBifrost, FakeMcp, StreamingFakeBifrost, _prepare_session


@pytest.mark.asyncio
async def test_worker_emits_reasoning_events_when_reasoning_is_enabled(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await repository.create_session("demo", {})
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={"reasoning": {"effort": "high"}},
        provider_options={},
    )
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=StreamingFakeBifrost(
            responses=[ChatResponse(content="partial answer", tool_calls=[], raw={})]
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    events = await repository.list_events(job.id)
    reasoning_events = [e for e in events if e.event_type == "reasoning"]
    model_output_events = [e for e in events if e.event_type == "model_output"]
    assert len(reasoning_events) == 1
    assert reasoning_events[0].payload_json["text"] == "thinking..."
    assert len(model_output_events) == 1
    assert not any(e.payload_json.get("stream") is True for e in model_output_events)


@pytest.mark.asyncio
async def test_worker_live_stream_events_reference_snapshot_rows(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await repository.create_session("demo", {})
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={"reasoning": {"effort": "high"}},
        provider_options={},
    )
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None
    assert claimed is not None

    class MultiChunkBifrost(FakeBifrost):
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
            self.calls.append(
                {"provider_id": provider_id, "model_name": model_name, "tools": tools}
            )
            if on_delta is not None:
                from agent_orchestrator.integrations.bifrost import (
                    ChatDelta,
                    ReasoningDetail,
                )

                await on_delta(
                    ChatDelta(
                        reasoning="thinking",
                        reasoning_details=[
                            ReasoningDetail(index=0, type="text", text="thinking")
                        ],
                    )
                )
                await on_delta(ChatDelta(reasoning="...", reasoning_details=[]))
                await on_delta(ChatDelta(content="partial "))
                await on_delta(ChatDelta(content="answer"))
            return ChatResponse(content="partial answer", tool_calls=[], raw={})

    live_event_bus = InMemoryLiveEventBus()
    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=MultiChunkBifrost(),
        live_event_bus=live_event_bus,
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored_events = await repository.list_events(job.id)
    reasoning_event = next(e for e in stored_events if e.event_type == "reasoning")
    model_output_event = next(e for e in stored_events if e.event_type == "model_output")

    subscriber = await live_event_bus.subscribe(job.id)
    try:
        live_events = []
        while True:
            event = await subscriber.get(timeout_seconds=0.05)
            if event is None:
                break
            live_events.append(event)
    finally:
        await subscriber.aclose()

    reasoning_live = [event for event in live_events if event.event_type == "reasoning"]
    model_output_live = [
        event for event in live_events if event.event_type == "model_output"
    ]

    assert [event.payload_json["text"] for event in reasoning_live] == [
        "thinking",
        "thinking...",
    ]
    assert all(event.payload_json["stream"] is True for event in reasoning_live)
    assert all(
        event.payload_json["snapshot_event_id"] == str(reasoning_event.id)
        for event in reasoning_live
    )

    assert [event.payload_json["text"] for event in model_output_live] == [
        "partial ",
        "partial answer",
    ]
    assert all(event.payload_json["stream"] is True for event in model_output_live)
    assert all(
        event.payload_json["snapshot_event_id"] == str(model_output_event.id)
        for event in model_output_live
    )


@pytest.mark.asyncio
async def test_worker_terminates_child_session_on_completion(
    repository: Repository, skill_registry: SkillRegistry
):
    parent_session = await _prepare_session(repository)
    child_session = await repository.create_session("child", {})
    await repository.set_model_config(
        child_session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repository.add_skill_assignment(
        child_session.id, "demo-skill", str(skill_registry._roots[0] / "demo-skill")
    )

    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="child task", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    claimed = await repository.claim_next_job()
    if claimed is not None and claimed.id == parent_job.id:
        claimed = await repository.claim_next_job()
    assert claimed is not None and claimed.id == child_job.id

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[ChatResponse(content="child done", tool_calls=[], raw={})]
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored_child = await repository.get_job(child_job.id)
    assert stored_child is not None
    assert stored_child.status == "completed"

    child_sess = await repository.get_session(child_session.id)
    assert child_sess is not None
    assert child_sess.status == "terminated"


@pytest.mark.asyncio
async def test_worker_terminates_child_session_on_failure(
    repository: Repository, skill_registry: SkillRegistry
):
    parent_session = await _prepare_session(repository)
    child_session = await repository.create_session("child", {})
    await repository.set_model_config(
        child_session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="child task", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    claimed = await repository.claim_next_job()
    if claimed is not None and claimed.id == parent_job.id:
        claimed = await repository.claim_next_job()
    assert claimed is not None and claimed.id == child_job.id

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("gateway_error", "permanent failure", retryable=False)
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker._run_job(claimed)

    stored_child = await repository.get_job(child_job.id)
    assert stored_child is not None
    assert stored_child.status == "failed"

    child_sess = await repository.get_session(child_session.id)
    assert child_sess is not None
    assert child_sess.status == "terminated"


@pytest.mark.asyncio
async def test_run_child_job_ignores_non_queued_jobs(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="child", metadata_json={}, max_attempts=1
    )
    assert job is not None

    worker = WorkerService(
        settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[ChatResponse(content="done", tool_calls=[], raw={})]
        ),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_tool_catalog=McpToolCatalog(FakeMcp()),
        skill_registry=skill_registry,
    )

    await worker.run_child_job(job.id)
    await worker.run_child_job(job.id)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
