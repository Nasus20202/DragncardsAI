"""Unit tests for the auto-compaction trigger in the worker."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse
from agent_orchestrator.api.tool_catalog import resolve_session_request_tools
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.personas import (
    SESSION_PERSONA_KEY,
    session_persona_snapshot_for,
)
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.tokens import estimate_tokens_for_messages
from agent_orchestrator.runtime.worker import WorkerService
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

from .app_test_support import UNIT_ENABLED_PROVIDER_IDS


class FakeBifrost:
    def __init__(self, responses=None):
        self.responses = list(
            responses
            or [
                ChatResponse(
                    content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
                )
            ]
        )
        self.calls = []
        self.compact_calls = 0

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return None

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
        self.calls.append({"provider_id": provider_id, "messages_count": len(messages)})
        if on_delta is not None:
            # Check if this is the compaction call (no tools) — return compact response
            if not tools and len(self.responses) > 1:
                self.compact_calls += 1
                return ChatResponse(
                    content="summary text",
                    tool_calls=[],
                    raw={"usage": {"total_tokens": 25}},
                )
        response = (
            self.responses.pop(0)
            if self.responses
            else ChatResponse(content="done", tool_calls=[], raw={})
        )
        if on_delta is not None and response.content:
            await on_delta(
                SimpleNamespace(
                    content=response.content, reasoning="", reasoning_details=[]
                )
            )
        return response


class RejectsOversizedRequests(FakeBifrost):
    """A provider that refuses a request larger than the model's window.

    This is what a real provider does when compaction assembles more than the
    model can accept, and it is the failure the auto-compaction guard has to
    absorb: the summarizing call is made from inside the job, so an unguarded
    error reaches the job's failure handlers and fails the user's turn.

    The summarizing call is the one made without `on_delta` — the job's own
    calls always stream.
    """

    def __init__(self, *, window_tokens: int, responses=None):
        super().__init__(responses=responses)
        self.window_tokens = window_tokens
        self.rejected_requests = 0

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
        if on_delta is None:
            estimated = estimate_tokens_for_messages(messages)
            if estimated > self.window_tokens:
                self.rejected_requests += 1
                raise BifrostError(
                    "context_length_exceeded",
                    f"request of ~{estimated} tokens exceeds the "
                    f"{self.window_tokens}-token context window",
                )
        return await super().chat_completion(
            provider_id,
            model_name,
            messages,
            tools,
            gateway_options,
            provider_options,
            on_delta=on_delta,
        )


class FakeMcp:
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
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


@pytest.fixture
async def repository():
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
    (skill_dir / "SKILL.md").write_text("follow instructions", encoding="utf-8")
    return SkillRegistry((root,))


async def _prepare_session(repo: Repository, metadata: dict | None = None):
    session = await repo.create_session("demo", metadata or {})
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
    return session


async def _make_completed_job(
    repo: Repository, session_id: str, tokens: int = 100
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt="hi", metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": "ok"})
    await repo.update_job_tokens_used(job.id, tokens)
    await repo.mark_job_completed(job.id, "ok")
    return job.id


def _make_worker(
    repo: Repository,
    bifrost: FakeBifrost,
    skill_registry: SkillRegistry,
    settings: Settings | None = None,
    live_event_bus: InMemoryLiveEventBus | None = None,
    mcp_catalog: McpToolCatalog | None = None,
) -> WorkerService:
    mcp_catalog = mcp_catalog or McpToolCatalog(FakeMcp())  # type: ignore[arg-type]
    return WorkerService(
        settings=settings
        or Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
        ),
        repository=repo,
        bifrost_client=bifrost,  # type: ignore[arg-type]
        live_event_bus=live_event_bus or InMemoryLiveEventBus(),
        mcp_tool_catalog=mcp_catalog,
        skill_registry=skill_registry,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_compact_fires_above_threshold(
    repository: Repository, skill_registry: SkillRegistry
):
    """When replay token estimate exceeds threshold, compaction is triggered before history."""
    session = await _prepare_session(repository)
    # Use threshold=0.0 so any replay content triggers compaction regardless of size
    await _make_completed_job(repository, session.id, tokens=10)

    bifrost = FakeBifrost(
        responses=[
            # compaction LLM call
            ChatResponse(
                content="game summary here",
                tool_calls=[],
                raw={"usage": {"total_tokens": 30}},
            ),
            # actual job LLM call
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            ),
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            # These sessions carry almost no history, so the fixed-cost guard
            # would otherwise skip them: the point here is the trigger and the
            # compaction path, not the guard, which has its own tests.
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
        ),
    )

    # Enqueue and run the new job
    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )

    with patch(
        "agent_orchestrator.runtime.prompt_run.perform_compaction",
        wraps=__import__(
            "agent_orchestrator.runtime.compaction", fromlist=["perform_compaction"]
        ).perform_compaction,
    ):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    # After running, compaction record should exist
    records = await repository.count_compaction_records(session.id)
    assert records == 1


@pytest.mark.asyncio
async def test_auto_compact_publishes_live_compaction_event(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    await _make_completed_job(repository, session.id, tokens=10)

    live_event_bus = InMemoryLiveEventBus()
    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="game summary here",
                tool_calls=[],
                raw={"usage": {"total_tokens": 30}},
            ),
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            ),
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        live_event_bus=live_event_bus,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            # These sessions carry almost no history, so the fixed-cost guard
            # would otherwise skip them: the point here is the trigger and the
            # compaction path, not the guard, which has its own tests.
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
        ),
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    assert current_job is not None

    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    subscriber = await live_event_bus.subscribe(current_job.id)
    try:
        seen_compaction = False
        while True:
            event = await subscriber.get(0.01)
            if event is None:
                break
            if event.event_type == "compaction":
                seen_compaction = True
                assert event.payload_json["summary_text"] == "game summary here"
                assert event.payload_json["tokens_used"] == 30
                assert isinstance(event.payload_json.get("compaction_job_id"), str)
        assert seen_compaction is True
    finally:
        await subscriber.aclose()


@pytest.mark.asyncio
async def test_auto_compact_does_not_fire_below_threshold(
    repository: Repository, skill_registry: SkillRegistry
):
    """When replay token estimate is below threshold, no compaction happens."""
    session = await _prepare_session(repository)
    # Token usage on the job is irrelevant; the threshold check now uses actual replay
    # message estimation. With a default threshold of 0.8 and tiny replay content,
    # compaction should not fire.
    await _make_completed_job(repository, session.id, tokens=500)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(repository, bifrost, skill_registry)

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    records = await repository.count_compaction_records(session.id)
    assert records == 0


@pytest.mark.asyncio
async def test_compaction_that_exceeds_the_window_degrades_the_turn(
    repository: Repository, skill_registry: SkillRegistry
):
    """The failure auto-compaction exists to prevent must not fail the turn.

    The provider rejects the summarization request because it is larger than
    the window. The job is expected to finish on the history it already has,
    with a `compaction_failed` event and no `failure` event.
    """
    session = await _prepare_session(repository)
    await _make_completed_job(repository, session.id, tokens=10)

    live_event_bus = InMemoryLiveEventBus()
    bifrost = RejectsOversizedRequests(
        window_tokens=200,
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ],
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        live_event_bus=live_event_bus,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
            # Wide enough that the request's fixed cost fits inside it, so the
            # trigger reaches the summarizing call; the provider still refuses
            # anything over 200 tokens, which is the failure under test.
            CONTEXT_WINDOW_SIZE=20_000,
        ),
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    assert current_job is not None

    subscriber = await live_event_bus.subscribe(current_job.id)
    try:
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]
        streamed = []
        while True:
            event = await subscriber.get(0.01)
            if event is None:
                break
            streamed.append(event)
    finally:
        await subscriber.aclose()

    assert bifrost.rejected_requests == 1

    stored = await repository.get_job(current_job.id)
    assert stored is not None
    assert stored.status == "completed"

    event_types = [event.event_type for event in stored.events]
    assert "failure" not in event_types
    assert "compaction_failed" in event_types
    assert await repository.count_compaction_records(session.id) == 0

    failed = next(
        event for event in stored.events if event.event_type == "compaction_failed"
    )
    assert "context window" in failed.payload_json["message"]
    assert failed.payload_json["code"] == "context_length_exceeded"
    assert failed.payload_json["usage_ratio"] > 0.0

    assert [event.event_type for event in streamed].count("compaction_failed") == 1


@pytest.mark.asyncio
async def test_nothing_to_compact_is_not_a_failure(
    repository: Repository, skill_registry: SkillRegistry
):
    """A session with no eligible job records no failure event and still runs."""
    session = await _prepare_session(repository)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            # These sessions carry almost no history, so the fixed-cost guard
            # would otherwise skip them: the point here is the trigger and the
            # compaction path, not the guard, which has its own tests.
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
        ),
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="first turn", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    stored = await repository.get_job(current_job.id)
    assert stored is not None
    assert stored.status == "completed"
    event_types = [event.event_type for event in stored.events]
    assert "compaction_failed" not in event_types
    assert "failure" not in event_types
    assert await repository.count_compaction_records(session.id) == 0


@pytest.mark.asyncio
async def test_auto_compact_skipped_when_memory_disabled(
    repository: Repository, skill_registry: SkillRegistry
):
    """When multi_turn_memory is False, _maybe_auto_compact is never called."""
    session = await _prepare_session(repository)
    await repository.update_multi_turn_memory(session.id, multi_turn_memory=False)
    # Even with very high token usage, no compaction should occur
    await _make_completed_job(repository, session.id, tokens=200000)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(repository, bifrost, skill_registry)

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    records = await repository.count_compaction_records(session.id)
    assert records == 0


# ---------------------------------------------------------------------------
# The trigger measures the whole request, not the replay alone (DRA-33)
# ---------------------------------------------------------------------------


def _inline_skill(skill_registry: SkillRegistry, name: str, approx_chars: int) -> str:
    """Write a skill whose SKILL.md is large enough to dominate a small window."""
    root = skill_registry._roots[0]  # type: ignore[attr-defined]
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = ("alpha bravo charlie delta echo foxtrot golf hotel " * 4000)[:approx_chars]
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return name


async def _make_wordy_completed_job(
    repo: Repository, session_id: str, *, words: int
) -> str:
    text = "alpha bravo charlie delta echo " * words
    job = await repo.enqueue_prompt_job(
        session_id, prompt="hi", metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": text})
    await repo.mark_job_completed(job.id, text)
    return job.id


@pytest.mark.asyncio
async def test_auto_compact_counts_the_whole_request_not_only_the_replay(
    repository: Repository, skill_registry: SkillRegistry
):
    """The trigger fires on a request the replay alone would not have triggered.

    The session's replayed history sits well below the threshold, but the
    system prompt, the tool definitions and the skill the prompt inlined into
    its own turn push the request the worker is about to send over it. A
    trigger that measures only the replay never sees that request and lets it
    through; a trigger that measures the request compacts.
    """
    session = await _prepare_session(repository)
    await _make_wordy_completed_job(repository, session.id, words=600)
    skill_name = _inline_skill(skill_registry, "fat-skill", approx_chars=40_000)

    window = 20_000
    settings = Settings(
        SKILL_ROOTS="/tmp",
        ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
        CONTEXT_WINDOW_SIZE=window,
        CONTEXT_COMPACTION_THRESHOLD=0.8,
        CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=1000,
    )

    # Precondition, asserted rather than assumed: the replay on its own is
    # nowhere near the threshold, so a replay-only trigger cannot fire here.
    from agent_orchestrator.runtime.session_transcript import SessionTranscriptService

    replay = await SessionTranscriptService(repository).build_message_history(
        session.id, current_job_id=""
    )
    replay_tokens = estimate_tokens_for_messages(replay)
    assert 1000 < replay_tokens < window * 0.8

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="game summary here",
                tool_calls=[],
                raw={"usage": {"total_tokens": 30}},
            ),
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            ),
        ]
    )
    worker = _make_worker(repository, bifrost, skill_registry, settings=settings)

    await repository.enqueue_prompt_job(
        session.id,
        prompt="next turn",
        metadata_json={"inline_skills": [skill_name]},
        max_attempts=1,
    )
    await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    assert await repository.count_compaction_records(session.id) == 1


@pytest.mark.asyncio
async def test_fixed_request_cost_alone_does_not_call_the_summarizer(
    repository: Repository, skill_registry: SkillRegistry, caplog
):
    """The trap that counting fixed cost introduces, and the guard for it.

    A session can sit above the threshold with almost no history: a large tool
    catalogue plus an inlined skill is enough on its own. Compaction rewrites
    the replay and nothing else, so summarizing here would block the turn on a
    model call that leaves the ratio exactly where it was — once per turn,
    forever. The trigger must skip, and must say why.
    """
    session = await _prepare_session(repository)
    # Over the 16,000-token threshold on fixed cost, but still inside the
    # 20,000-token window — so the request is not hopeless, there is simply no
    # history worth summarizing.
    skill_name = _inline_skill(skill_registry, "fat-skill", approx_chars=60_000)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_WINDOW_SIZE=20_000,
            CONTEXT_COMPACTION_THRESHOLD=0.8,
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=1000,
        ),
    )

    await repository.enqueue_prompt_job(
        session.id,
        prompt="next turn",
        metadata_json={"inline_skills": [skill_name]},
        max_attempts=1,
    )
    with caplog.at_level(logging.INFO, logger="agent_orchestrator.runtime.prompt_run"):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    assert await repository.count_compaction_records(session.id) == 0
    skips = [
        record.getMessage()
        for record in caplog.records
        if "fixed request cost" in record.getMessage()
    ]
    assert len(skips) == 1
    assert "not history" in skips[0]


@pytest.mark.asyncio
async def test_trigger_and_context_endpoint_report_the_same_components(
    repository: Repository, skill_registry: SkillRegistry, caplog
):
    """The parity this change exists to establish.

    The trigger reports the components it fired on; the context metadata the
    dashboard's widget renders reports its own. For one session, with no job in
    between, the system prompt, the replay and the tool definitions have to
    match — they are the same request, measured by the same function.

    The user message is the one component that cannot match: the widget
    describes a session at rest, where the next prompt has not been typed.
    """
    session = await _prepare_session(repository)
    await _make_wordy_completed_job(repository, session.id, words=300)

    mcp_catalog = McpToolCatalog(FakeMcp())  # type: ignore[arg-type]
    live_event_bus = InMemoryLiveEventBus()

    # Taken before the job runs, so both sides see the same replay: at job
    # start the current job is not yet a completed job of the session.
    reloaded = await repository.get_session(session.id)
    assert reloaded is not None
    metadata = await repository.get_context_metadata(
        session.id,
        20_000,
        skill_registry=skill_registry,
        request_tools=await resolve_session_request_tools(
            mcp_tool_catalog=mcp_catalog,
            skill_registry=skill_registry,
            repository=repository,
            live_event_bus=live_event_bus,
            session=reloaded,
        ),
    )

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="game summary here",
                tool_calls=[],
                raw={"usage": {"total_tokens": 30}},
            ),
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            ),
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        live_event_bus=live_event_bus,
        mcp_catalog=mcp_catalog,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_WINDOW_SIZE=20_000,
            # Forced low so the trigger reports its components; the numbers
            # being compared do not depend on whether it decided to compact.
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
        ),
    )

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    with caplog.at_level(logging.INFO, logger="agent_orchestrator.runtime.prompt_run"):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    # Read from the structured field rather than the message text, so this
    # correctness test does not break when a log line is reworded.
    reported = next(
        record.context_estimate
        for record in caplog.records
        if hasattr(record, "context_estimate")
    )

    assert reported["system_prompt"] == metadata["token_breakdown"]["system_prompt"]
    assert reported["tools"] == metadata["token_breakdown"]["tools"]
    assert reported["replay"] == metadata["token_breakdown"]["replay"]
    assert reported["context_window_size"] == metadata["context_window_size"]
    # The widget's total is the trigger's total minus the turn it cannot know
    # about, and nothing else.
    assert reported["total"] - reported["user_message"] == metadata["tokens_used"]


@pytest.mark.asyncio
async def test_parity_survives_a_session_persona_and_a_subagent_allowlist(
    repository: Repository, skill_registry: SkillRegistry, caplog
):
    """Parity must hold for a session that has a persona and an allowlist.

    The worker builds a top-level system prompt from the session's *allowlist*
    -- not every persona on record -- and appends the session's own persona
    prompt. An estimate that read the whole persona table would over-report,
    and one that dropped the persona prompt would under-report. Because those
    errors point in opposite directions they can partly cancel, so a session
    with neither feature is not evidence of anything: this test gives the two
    sides different-sized catalogues on purpose.
    """
    for name in ("alpha", "beta", "gamma"):
        await repository.upsert_persona(
            name,
            display_name=f"{name.title()} Agent",
            description=f"The {name} specialist who handles {name} work. " * 12,
            system_prompt=f"You are {name} and you always act like {name}. " * 25,
            provider_id=None,
            model_name=None,
            gateway_options=None,
            provider_options=None,
            skills=None,
            allowed_tools=None,
        )

    adopted = await repository.get_persona("gamma")
    assert adopted is not None
    session = await _prepare_session(
        repository,
        {SESSION_PERSONA_KEY: session_persona_snapshot_for(adopted)},
    )
    # Strictly narrower than the catalogue, so reading `list_personas()`
    # instead of the allowlist changes the number.
    assert await repository.replace_session_allowed_subagents(session.id, ["alpha"])
    await _make_wordy_completed_job(repository, session.id, words=300)

    mcp_catalog = McpToolCatalog(FakeMcp())  # type: ignore[arg-type]
    live_event_bus = InMemoryLiveEventBus()

    reloaded = await repository.get_session(session.id)
    assert reloaded is not None
    metadata = await repository.get_context_metadata(
        session.id,
        20_000,
        skill_registry=skill_registry,
        request_tools=await resolve_session_request_tools(
            mcp_tool_catalog=mcp_catalog,
            skill_registry=skill_registry,
            repository=repository,
            live_event_bus=live_event_bus,
            session=reloaded,
        ),
    )

    worker = _make_worker(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
                )
            ]
        ),
        skill_registry,
        live_event_bus=live_event_bus,
        mcp_catalog=mcp_catalog,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_WINDOW_SIZE=20_000,
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
        ),
    )

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    with caplog.at_level(logging.INFO, logger="agent_orchestrator.runtime.prompt_run"):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    reported = next(
        record.context_estimate
        for record in caplog.records
        if hasattr(record, "context_estimate")
    )

    assert reported["system_prompt"] == metadata["token_breakdown"]["system_prompt"]
    assert reported["tools"] == metadata["token_breakdown"]["tools"]
    assert reported["total"] - reported["user_message"] == metadata["tokens_used"]


@pytest.mark.asyncio
async def test_the_guard_still_holds_after_a_session_has_compacted_once(
    repository: Repository, skill_registry: SkillRegistry, caplog
):
    """The carried-forward summary is part of the replay and must not count.

    `build_message_history` prepends the previous summary as a system message
    and the replay windows never drop it, so a session that has compacted once
    always replays at least its own summary. Comparing the *whole* replay
    against the floor would therefore make this guard unreachable for exactly
    the sessions that keep hitting it, and a session over the threshold on
    fixed cost would buy a summarizing call on every turn thereafter. Only the
    span since the checkpoint is compactable.
    """
    session = await _prepare_session(repository)
    checkpoint_job = await _make_completed_job(repository, session.id, tokens=10)
    await repository.create_compaction_record(
        session.id,
        summary_text="Hero HP 12/15. Villain HP 30/60, stage 1. " * 200,
        covers_up_to_job_id=checkpoint_job,
        tokens_used=9_000,
    )
    skill_name = _inline_skill(skill_registry, "fat-skill", approx_chars=120_000)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_WINDOW_SIZE=20_000,
            CONTEXT_COMPACTION_THRESHOLD=0.8,
        ),
    )

    await repository.enqueue_prompt_job(
        session.id,
        prompt="next turn",
        metadata_json={"inline_skills": [skill_name]},
        max_attempts=1,
    )
    with caplog.at_level(logging.INFO, logger="agent_orchestrator.runtime.prompt_run"):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    # No second record: nothing new since the checkpoint is worth summarizing.
    assert await repository.count_compaction_records(session.id) == 1
    skips = [
        record.getMessage()
        for record in caplog.records
        if "fixed request cost" in record.getMessage()
    ]
    assert len(skips) == 1
    assert "compactable_replay=0" in skips[0]


@pytest.mark.asyncio
async def test_a_request_whose_fixed_cost_fills_the_window_is_not_summarized(
    repository: Repository, skill_registry: SkillRegistry, caplog
):
    """No summary can rescue a request whose unshrinkable parts already overflow.

    Distinct from the floor case: here there *is* history worth summarizing,
    but the system prompt, tools and inlined skill exceed the window on their
    own, so compacting the history cannot produce a request that fits. Spending
    a blocking model call before the provider refuses the turn anyway helps
    nobody.
    """
    session = await _prepare_session(repository)
    await _make_wordy_completed_job(repository, session.id, words=600)
    skill_name = _inline_skill(skill_registry, "fat-skill", approx_chars=120_000)

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_WINDOW_SIZE=20_000,
            CONTEXT_COMPACTION_THRESHOLD=0.8,
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=1000,
        ),
    )

    await repository.enqueue_prompt_job(
        session.id,
        prompt="next turn",
        metadata_json={"inline_skills": [skill_name]},
        max_attempts=1,
    )
    with caplog.at_level(logging.INFO, logger="agent_orchestrator.runtime.prompt_run"):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    assert await repository.count_compaction_records(session.id) == 0
    skips = [
        record.getMessage()
        for record in caplog.records
        if "fixed request cost" in record.getMessage()
    ]
    assert len(skips) == 1
    assert "fixed cost alone fills the window" in skips[0]


@pytest.mark.asyncio
async def test_a_restored_conversation_counts_toward_the_estimate(
    repository: Repository, skill_registry: SkillRegistry, caplog
):
    """A restored conversation is prepended to every request and never compacted.

    It is caller-supplied and unbounded, so leaving it out of the estimate is
    the same class of blind spot as leaving out the tool definitions.
    """
    session = await _prepare_session(repository)
    restored = [
        {"role": "user", "content": "alpha bravo charlie delta echo " * 400},
        {"role": "assistant", "content": "foxtrot golf hotel india " * 400},
    ]
    await repository.update_session(
        session.id,
        metadata_json={"restored_conversation_context": restored},
    )

    bifrost = FakeBifrost(
        responses=[
            ChatResponse(
                content="done", tool_calls=[], raw={"usage": {"total_tokens": 10}}
            )
        ]
    )
    worker = _make_worker(
        repository,
        bifrost,
        skill_registry,
        settings=Settings(
            SKILL_ROOTS="/tmp",
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
            CONTEXT_WINDOW_SIZE=20_000,
            CONTEXT_COMPACTION_THRESHOLD=0.0,
            CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0,
        ),
    )

    await repository.enqueue_prompt_job(
        session.id, prompt="next turn", metadata_json={}, max_attempts=1
    )
    with caplog.at_level(logging.INFO, logger="agent_orchestrator.runtime.prompt_run"):
        await worker._run_job(await repository.claim_next_job())  # type: ignore[arg-type]

    reported = next(
        record.context_estimate
        for record in caplog.records
        if hasattr(record, "context_estimate")
    )
    # The session has no completed job, so every replay token reported here is
    # the restored conversation.
    assert reported["replay"] > 1000
