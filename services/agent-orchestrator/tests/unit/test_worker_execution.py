from __future__ import annotations

import pytest

from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.storage.repository import Repository

from .worker_test_support import (
    FakeBifrost,
    FakeMcp,
    StreamingFakeBifrost,
    make_worker,
    prepare_session,
    repository,
    skill_registry,
)


@pytest.mark.asyncio
async def test_worker_completes_prompt_with_tool(
    repository: Repository, skill_registry
):
    session = await prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(id="tool-1", name="game-service_next_step", arguments={})
                ],
                raw={},
            ),
            ChatResponse(content="finished", tool_calls=[], raw={}),
        ]
    )
    mcp = FakeMcp()
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=mcp,
    )

    await worker._run_job(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "finished"
    assert len(bifrost.calls) == 2
    assert mcp.calls[0]["tool_name"] == "next_step"
    events = await repository.list_events(job.id)
    assert [event.event_type for event in events][-1] == "completion"


@pytest.mark.asyncio
async def test_worker_emits_reasoning_events_when_reasoning_is_enabled(
    repository: Repository, skill_registry
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

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=StreamingFakeBifrost(
            responses=[ChatResponse(content="partial answer", tool_calls=[], raw={})]
        ),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    events = await repository.list_events(job.id)
    reasoning_events = [event for event in events if event.event_type == "reasoning"]
    model_output_events = [
        event for event in events if event.event_type == "model_output"
    ]
    assert len(reasoning_events) == 1
    assert reasoning_events[0].payload_json["text"] == "thinking..."
    assert len(model_output_events) == 1
    assert not any(
        event.payload_json.get("stream") is True for event in model_output_events
    )


@pytest.mark.asyncio
async def test_worker_live_stream_events_reference_snapshot_rows(
    repository: Repository, skill_registry
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
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=MultiChunkBifrost(),
        mcp_client=FakeMcp(),
        live_event_bus=live_event_bus,
    )

    await worker._run_job(claimed)

    stored_events = await repository.list_events(job.id)
    reasoning_event = next(
        event for event in stored_events if event.event_type == "reasoning"
    )
    model_output_event = next(
        event for event in stored_events if event.event_type == "model_output"
    )

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
