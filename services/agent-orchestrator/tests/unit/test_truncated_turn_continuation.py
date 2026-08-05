"""A turn the provider cut off at its output cap is resumed, not reported as done.

Every test here drives the real `PromptRunService.run` against a fake gateway,
because the bug being fixed lives in one branch of that loop: a response with no
tool calls used to end the job whatever the reason the model stopped.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
)
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrost:
    """Returns canned responses in order, and records the messages it was sent."""

    def __init__(
        self, responses: list[ChatResponse], context_length: int | None = None
    ):
        self.responses = list(responses)
        self.context_length = context_length
        self.requests: list[list[dict[str, Any]]] = []
        self.on_response = None

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return self.context_length

    async def chat_completion(
        self,
        provider_id,
        model_name,
        messages,
        tools,
        gateway_options,
        provider_options,
        on_delta=None,
    ) -> ChatResponse:
        self.requests.append([dict(message) for message in messages])
        response = self.responses.pop(0)
        if on_delta is not None and response.content:
            await on_delta(
                SimpleNamespace(
                    content=response.content, reasoning="", reasoning_details=[]
                )
            )
        if self.on_response is not None:
            await self.on_response()
        return response


class FakeMcp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def list_tools(self, server_url, transport, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        self.calls.append({"tool_name": tool_name, "arguments": arguments})
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


@pytest.fixture
async def repository():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


@pytest.fixture
def skill_registry(tmp_path: Path) -> SkillRegistry:
    root = tmp_path / "skills"
    root.mkdir()
    skill_dir = root / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("follow instructions", encoding="utf-8")
    return SkillRegistry((root,))


async def _claimed_job(repo: Repository):
    session = await repo.create_session("demo", {})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repo.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repo.enable_mcp_for_session(session.id, "game-service", enabled=True)
    job = await repo.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None
    return job, claimed


def _service(
    repo: Repository,
    bifrost: FakeBifrost,
    skill_registry: SkillRegistry,
    *,
    bus: InMemoryLiveEventBus | None = None,
    **settings_overrides: Any,
) -> PromptRunService:
    settings = Settings(SKILL_ROOTS=str(skill_registry._roots[0]), **settings_overrides)
    return PromptRunService(
        dependencies=PromptRunDependencies(
            settings=settings,
            repository=repo,
            bifrost_client=bifrost,
            live_event_bus=bus or InMemoryLiveEventBus(),
            mcp_tool_catalog=McpToolCatalog(FakeMcp()),
            skill_registry=skill_registry,
        ),
        transcript_service=SessionTranscriptService(repo),
        schedule_child_job=lambda job_id: None,
    )


async def _event_types(repo: Repository, job_id: str) -> list[str]:
    return [event.event_type for event in await repo.list_events(job_id)]


@pytest.mark.asyncio
async def test_a_turn_truncated_at_the_output_cap_is_continued(
    repository: Repository, skill_registry: SkillRegistry
):
    """The reported bug: the agent stops mid-thought and needs a manual "continue".

    The first response is what a provider returns when it hits the output cap —
    partial text, no tool calls, `finish_reason` of "length". Without the fix the
    worker completes the job on it and the second response is never requested.
    """
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="I will start by ",
                tool_calls=[],
                raw={},
                finish_reason="length",
            ),
            ChatResponse(
                content="checking the board.",
                tool_calls=[],
                raw={},
                finish_reason="stop",
            ),
        ]
    )

    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "I will start by checking the board."
    assert bifrost.responses == [], "the continuation call was never made"


@pytest.mark.asyncio
async def test_the_continuation_is_recorded_between_the_two_output_segments(
    repository: Repository, skill_registry: SkillRegistry
):
    job, claimed = await _claimed_job(repository)
    bus = InMemoryLiveEventBus()
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="partial", tool_calls=[], raw={}, finish_reason="length"
            ),
            ChatResponse(
                content=" and the rest", tool_calls=[], raw={}, finish_reason="stop"
            ),
        ]
    )

    await _service(repository, bifrost, skill_registry, bus=bus).run(claimed)

    types = await _event_types(repository, job.id)
    assert types.count("turn_continued") == 1
    marker = types.index("turn_continued")
    assert "model_output" in types[:marker], "the partial output must survive"
    assert "model_output" in types[marker + 1 :], "the continued output must follow"

    stored = next(
        event
        for event in await repository.list_events(job.id)
        if event.event_type == "turn_continued"
    )
    assert stored.payload_json["finish_reason"] == "length"
    assert stored.payload_json["continuation"] == 1
    assert stored.payload_json["max_continuations"] == 3

    published = [
        event for event in bus._replay[job.id] if event.event_type == "turn_continued"
    ]
    assert len(published) == 1
    assert published[0].durable_event_id == str(stored.id)


@pytest.mark.asyncio
async def test_a_model_that_chose_to_stop_is_not_forced_onward(
    repository: Repository, skill_registry: SkillRegistry
):
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [ChatResponse(content="done", tool_calls=[], raw={}, finish_reason="stop")]
    )

    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "done"
    assert "turn_continued" not in await _event_types(repository, job.id)


@pytest.mark.asyncio
async def test_an_unknown_stop_reason_is_not_treated_as_truncation(
    repository: Repository, skill_registry: SkillRegistry
):
    """The safe asymmetry: only a known truncation vocabulary continues a turn."""
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="done", tool_calls=[], raw={}, finish_reason="something_new"
            )
        ]
    )

    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert "turn_continued" not in await _event_types(repository, job.id)


@pytest.mark.asyncio
async def test_a_model_that_truncates_every_time_still_terminates(
    repository: Repository, skill_registry: SkillRegistry
):
    """The bound. Without it this is an unbounded loop against a paid provider."""
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content=f"chunk{index} ", tool_calls=[], raw={}, finish_reason="length"
            )
            for index in range(10)
        ]
    )

    await _service(
        repository, bifrost, skill_registry, AUTO_CONTINUE_MAX_CONTINUATIONS=2
    ).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    # One original call plus exactly two continuations.
    assert len(bifrost.requests) == 3
    assert (await _event_types(repository, job.id)).count("turn_continued") == 2
    assert stored.result_text == "chunk0 chunk1 chunk2 "


@pytest.mark.asyncio
async def test_the_behaviour_can_be_switched_off(
    repository: Repository, skill_registry: SkillRegistry
):
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="partial", tool_calls=[], raw={}, finish_reason="length"
            ),
            ChatResponse(content="unreached", tool_calls=[], raw={}),
        ]
    )

    await _service(
        repository, bifrost, skill_registry, AUTO_CONTINUE_TRUNCATED_TURNS=False
    ).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "partial"
    assert len(bifrost.requests) == 1
    assert "turn_continued" not in await _event_types(repository, job.id)


@pytest.mark.asyncio
async def test_a_cancel_during_a_continuation_chain_stops_it(
    repository: Repository, skill_registry: SkillRegistry
):
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content=f"chunk{index} ", tool_calls=[], raw={}, finish_reason="length"
            )
            for index in range(5)
        ]
    )

    async def cancel_once_the_chain_has_started() -> None:
        if len(bifrost.requests) == 2:
            await repository.request_cancel(job.id)

    bifrost.on_response = cancel_once_the_chain_has_started

    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "cancelled"
    # The chain stopped promptly rather than running out its continuation budget.
    assert len(bifrost.requests) == 2


@pytest.mark.asyncio
async def test_a_request_at_the_context_budget_is_not_continued(
    repository: Repository, skill_registry: SkillRegistry
):
    """No truncate-continue-truncate spiral: a full request is never grown."""
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="partial", tool_calls=[], raw={}, finish_reason="length"
            ),
            ChatResponse(content="unreached", tool_calls=[], raw={}),
        ],
        # A window so small that the system prompt alone is over the budget.
        context_length=16,
    )

    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "partial"
    assert len(bifrost.requests) == 1
    assert "turn_continued" not in await _event_types(repository, job.id)


@pytest.mark.asyncio
async def test_the_continuation_budget_resets_when_work_happens(
    repository: Repository, skill_registry: SkillRegistry
):
    """The cap counts consecutive truncations, not a whole turn's unrelated ones."""
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="thinking ", tool_calls=[], raw={}, finish_reason="length"
            ),
            ChatResponse(
                content="now acting ",
                tool_calls=[
                    ToolCall(id="tool-1", name="game-service_next_step", arguments={})
                ],
                raw={},
                finish_reason="tool_calls",
            ),
            ChatResponse(
                content="cut off again ", tool_calls=[], raw={}, finish_reason="length"
            ),
            ChatResponse(content="finished", tool_calls=[], raw={}),
        ]
    )

    await _service(
        repository, bifrost, skill_registry, AUTO_CONTINUE_MAX_CONTINUATIONS=1
    ).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert (await _event_types(repository, job.id)).count("turn_continued") == 2
    assert stored.result_text == "cut off again finished"


@pytest.mark.asyncio
async def test_an_empty_truncated_response_sends_no_empty_assistant_message(
    repository: Repository, skill_registry: SkillRegistry
):
    """A reasoning model can spend its whole output budget thinking and return no text."""
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(content="", tool_calls=[], raw={}, finish_reason="max_tokens"),
            ChatResponse(content="the answer", tool_calls=[], raw={}),
        ]
    )

    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.result_text == "the answer"
    assert len(bifrost.requests) == 2
    assert not [
        message
        for message in bifrost.requests[1]
        if message.get("role") == "assistant" and not message.get("content")
    ]


@pytest.mark.asyncio
async def test_a_replayed_continuation_tells_the_next_turn_what_happened(
    repository: Repository, skill_registry: SkillRegistry
):
    """Replay skips event types it does not know, so the note needs its own branch."""
    job, claimed = await _claimed_job(repository)
    bifrost = FakeBifrost(
        [
            ChatResponse(
                content="partial", tool_calls=[], raw={}, finish_reason="length"
            ),
            ChatResponse(content=" and the rest", tool_calls=[], raw={}),
        ]
    )
    await _service(repository, bifrost, skill_registry).run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"

    replayed = await SessionTranscriptService(repository).build_message_history(
        stored.session.id, current_job_id=None
    )
    assert any(
        "continued" in str(message.get("content", "")).lower() for message in replayed
    ), replayed
