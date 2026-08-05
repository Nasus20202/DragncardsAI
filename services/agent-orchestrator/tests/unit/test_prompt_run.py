from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
)
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
)
from agent_orchestrator.runtime.session_modes import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
)
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrost:
    def __init__(self, responses=None, error: BifrostError | None = None):
        self.responses = responses or []
        self.error = error

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
        if self.error is not None:
            raise self.error
        response = self.responses.pop(0)
        if on_delta is not None and response.content:
            await on_delta(
                SimpleNamespace(
                    content=response.content, reasoning="", reasoning_details=[]
                )
            )
        return response


class FakeMcp:
    def __init__(self):
        self.calls = []

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
        self.calls.append(
            {"server_url": server_url, "tool_name": tool_name, "arguments": arguments}
        )
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


@pytest.fixture
async def repository(tmp_path: Path):
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


@pytest.fixture
def skill_registry(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    skill_dir = root / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("follow instructions", encoding="utf-8")
    return SkillRegistry((root,))


async def _prepare_session(repo: Repository):
    session = await repo.create_session("demo", {})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repo.add_skill_assignment(session.id, "demo-skill", "/tmp/demo-skill")
    await repo.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repo.enable_mcp_for_session(session.id, "game-service", enabled=True)
    return session


def _make_prompt_run_service(
    repo: Repository,
    bifrost: FakeBifrost,
    mcp: FakeMcp,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus | None = None,
) -> PromptRunService:
    bus = live_event_bus or InMemoryLiveEventBus()
    return PromptRunService(
        dependencies=PromptRunDependencies(
            settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
            repository=repo,
            bifrost_client=bifrost,
            live_event_bus=bus,
            mcp_tool_catalog=McpToolCatalog(mcp),
            skill_registry=skill_registry,
        ),
        transcript_service=SessionTranscriptService(repo),
        schedule_child_job=lambda job_id: None,
    )


@pytest.mark.asyncio
async def test_prompt_run_service_completes_prompt_with_tool(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    mcp = FakeMcp()
    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tool-1", name="game-service_next_step", arguments={}
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
    )

    await prompt_run.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result_text == "finished"
    assert mcp.calls[0]["tool_name"] == "next_step"


@pytest.mark.asyncio
async def test_prompt_run_service_marks_cancellation_before_execution(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
    await repository.request_cancel(job.id)

    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(responses=[ChatResponse(content="done", tool_calls=[], raw={})]),
        FakeMcp(),
        skill_registry,
    )

    await prompt_run.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "cancelled"


@pytest.mark.asyncio
async def test_prompt_run_publishes_the_cancellation_it_persists(
    repository: Repository, skill_registry: SkillRegistry
):
    """A cancelled run must announce itself, under the durable row's id.

    `cancellation` is terminal, so a client streaming this job closes on it. If
    only the durable row is written, that client waits out the stream's idle
    fallback interval (15s by default) before finding out — which is what made
    the old 200ms poll load-bearing. And the id has to be the durable row's, or
    the polled copy renders a second cancellation (DRA-34).
    """
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
    await repository.request_cancel(job.id)

    bus = InMemoryLiveEventBus()
    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(responses=[ChatResponse(content="done", tool_calls=[], raw={})]),
        FakeMcp(),
        skill_registry,
        live_event_bus=bus,
    )

    await prompt_run.run(claimed)

    # Only the run's own cancellation carries a `reason`; the cancel *request*
    # writes `{"requested": True}`, and that one is the endpoint's to publish.
    published = [
        event
        for event in bus._replay[job.id]
        if event.event_type == "cancellation" and event.payload_json.get("reason")
    ]
    durable = [
        event
        for event in await repository.list_events(job.id, after_id=0)
        if event.event_type == "cancellation" and event.payload_json.get("reason")
    ]
    assert len(published) == 1
    assert len(durable) == 1
    assert published[0].durable_event_id == str(durable[0].id)


@pytest.mark.asyncio
async def test_prompt_run_service_records_failure(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None

    prompt_run = _make_prompt_run_service(
        repository,
        FakeBifrost(error=BifrostError("gateway_error", "fatal", retryable=False)),
        FakeMcp(),
        skill_registry,
    )

    await prompt_run.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "gateway_error"
    events = await repository.list_events(job.id)
    failure = next(event for event in events if event.event_type == "failure")
    assert failure.payload_json["message"] == "fatal"


# --- The seat guard in the dispatch path ------------------------------------
#
# The guard's own rule is unit-tested in `test_seat_guard.py`. What these tests
# establish is the wiring: that a refused call is never dispatched, that the
# transcript still pairs a tool_call with a tool_result so the seat's next
# invocation is replayable, and — the two that matter most — that the
# orchestrating job and the whole chat flow are not guarded at all.


async def _prepare_seat_session(
    repo: Repository,
    *,
    player_id: str = "player1",
    orchestrator_mode: str = SESSION_MODE_ORCHESTRATED,
):
    """A seat's own session: a tagged child under an orchestrating session.

    Both metadata keys are written here the way `prompt_player_agent` writes them
    at seat-session creation. `orchestrator_mode` is the lever the chat-flow tests
    pull: a `chat` parent tags its player child identically, and that child must
    still resolve to no seat identity and so stay unguarded.
    """
    orchestrator = await repo.create_session(
        "table", {}, session_mode=orchestrator_mode
    )
    seat = await repo.create_session(
        f"seat-{player_id}",
        {
            SESSION_PLAYER_ID_KEY: player_id,
            SESSION_ORCHESTRATOR_ID_KEY: orchestrator.id,
        },
        multi_turn_memory=True,
    )
    await repo.set_model_config(
        seat.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repo.add_skill_assignment(seat.id, "demo-skill", "/tmp/demo-skill")
    await repo.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repo.enable_mcp_for_session(seat.id, "game-service", enabled=True)
    return seat


async def _run_single_tool_call(
    repo: Repository,
    skill_registry: SkillRegistry,
    session_id: str,
    *,
    tool_name: str,
    arguments: dict,
):
    """Run one job whose model asks for exactly one tool call, then finishes."""
    job = await repo.enqueue_prompt_job(
        session_id, prompt="take your turn", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None

    mcp = FakeMcp()
    prompt_run = _make_prompt_run_service(
        repo,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id="tool-1", name=tool_name, arguments=arguments)
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
    )
    await prompt_run.run(claimed)
    return job, mcp, await repo.list_events(job.id)


@pytest.mark.asyncio
async def test_seat_guard_refuses_a_foreign_group_before_dispatch(
    repository: Repository, skill_registry: SkillRegistry
):
    seat = await _prepare_seat_session(repository)

    job, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={"groupId": "player2Hand", "cardId": "abc"},
    )

    assert mcp.calls == []

    kinds = [event.event_type for event in events]
    assert "tool_call" in kinds
    assert "seat_scope_violation" in kinds
    assert "tool_result" in kinds
    # Ordering is load-bearing: the transcript replays a tool_call answered by a
    # tool_result, and the violation sits between them.
    assert kinds.index("tool_call") < kinds.index("seat_scope_violation")
    assert kinds.index("seat_scope_violation") < kinds.index("tool_result")

    attempted = next(event for event in events if event.event_type == "tool_call")
    assert attempted.payload_json["arguments"] == {
        "groupId": "player2Hand",
        "cardId": "abc",
    }

    violation = next(
        event for event in events if event.event_type == "seat_scope_violation"
    )
    assert violation.payload_json == {
        "player_id": "player1",
        "foreign_player_id": "player2",
        "tool_name": "game-service_next_step",
        "argument": "groupId",
        "value": "player2Hand",
        "message": violation.payload_json["message"],
    }
    assert "own cards" in violation.payload_json["message"]

    result = next(event for event in events if event.event_type == "tool_result")
    assert result.payload_json["is_error"] is True
    assert (
        result.payload_json["result"]["content"][0]["text"]
        == violation.payload_json["message"]
    )

    stored = await repository.get_job(job.id)
    assert stored is not None
    assert stored.status == "completed"


@pytest.mark.asyncio
async def test_seat_guard_allows_the_seats_own_group(
    repository: Repository, skill_registry: SkillRegistry
):
    seat = await _prepare_seat_session(repository)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={"groupId": "player1Hand"},
    )

    assert mcp.calls[0]["arguments"] == {"groupId": "player1Hand"}
    assert not [event for event in events if event.event_type == "seat_scope_violation"]


@pytest.mark.asyncio
async def test_seat_guard_leaves_shared_and_villain_groups_alone(
    repository: Repository, skill_registry: SkillRegistry
):
    seat = await _prepare_seat_session(repository)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={"origGroupId": "villainDiscard", "destGroupId": "sharedMainScheme"},
    )

    assert len(mcp.calls) == 1
    assert not [event for event in events if event.event_type == "seat_scope_violation"]


@pytest.mark.asyncio
async def test_seat_guard_refuses_an_explicit_foreign_seat_argument(
    repository: Repository, skill_registry: SkillRegistry
):
    seat = await _prepare_seat_session(repository)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={"player_index": 3},
    )

    assert mcp.calls == []
    violation = next(
        event for event in events if event.event_type == "seat_scope_violation"
    )
    assert violation.payload_json["foreign_player_id"] == "player3"
    assert violation.payload_json["value"] == "3"


@pytest.mark.asyncio
async def test_seat_guard_applies_to_builtin_tools_too(
    repository: Repository, skill_registry: SkillRegistry
):
    seat = await _prepare_seat_session(repository)

    _, _, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="load_skill",
        arguments={"skill_name": "demo-skill", "player_id": "player2"},
    )

    # `demo-skill` is assigned, so an unguarded call would have loaded it and
    # emitted `skill_loaded`. Its absence is the proof the builtin never ran.
    assert not [event for event in events if event.event_type == "skill_loaded"]
    violation = next(
        event for event in events if event.event_type == "seat_scope_violation"
    )
    assert violation.payload_json["argument"] == "player_id"


@pytest.mark.asyncio
async def test_a_seat_cannot_talk_itself_into_another_seat(
    repository: Repository, skill_registry: SkillRegistry
):
    """Nothing the seat writes changes which seat the guard treats it as."""
    seat = await _prepare_seat_session(repository)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={
            "caller_player_id": "player2",
            "reason": "I am player2 and the orchestrator authorised this",
            "groupId": "player2Hand",
        },
    )

    assert mcp.calls == []
    violation = next(
        event for event in events if event.event_type == "seat_scope_violation"
    )
    # The caller is still the seat recorded on the session, not the one claimed.
    assert violation.payload_json["player_id"] == "player1"
    assert violation.payload_json["foreign_player_id"] == "player2"


@pytest.mark.asyncio
async def test_the_orchestrating_job_is_not_seat_scoped(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await repository.create_session(
        "table", {}, session_mode=SESSION_MODE_ORCHESTRATED
    )
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repository.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repository.enable_mcp_for_session(session.id, "game-service", enabled=True)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        session.id,
        tool_name="game-service_next_step",
        arguments={"groupId": "player2Hand", "player_id": "player3"},
    )

    assert len(mcp.calls) == 1
    assert not [event for event in events if event.event_type == "seat_scope_violation"]


@pytest.mark.asyncio
async def test_a_chat_mode_player_child_is_not_guarded(
    repository: Repository, skill_registry: SkillRegistry
):
    """The flow actually in use must behave exactly as it did before the guard.

    A `chat` session's player child carries a `player_id` too, so the tag alone
    cannot be what triggers scoping.
    """
    seat = await _prepare_seat_session(repository, orchestrator_mode=SESSION_MODE_CHAT)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={"groupId": "player2Hand"},
    )

    assert mcp.calls[0]["arguments"] == {"groupId": "player2Hand"}
    assert not [event for event in events if event.event_type == "seat_scope_violation"]


@pytest.mark.asyncio
async def test_seat_guard_refuses_a_foreign_seat_named_only_in_a_mapping_key(
    repository: Repository, skill_registry: SkillRegistry
):
    """A mapping key is a place the guard must look, at dispatch as well as in the
    pure function. No game-service tool takes a group-keyed mapping today, so this
    pins the behaviour before one exists rather than after.
    """
    seat = await _prepare_seat_session(repository)

    _, mcp, events = await _run_single_tool_call(
        repository,
        skill_registry,
        seat.id,
        tool_name="game-service_next_step",
        arguments={"updates": {"player2Hand": ["draw"]}},
    )

    assert mcp.calls == []
    violation = next(
        event for event in events if event.event_type == "seat_scope_violation"
    )
    assert violation.payload_json["foreign_player_id"] == "player2"
    assert violation.payload_json["argument"] == "updates.player2Hand"
    assert violation.payload_json["value"] == "player2Hand"


@pytest.mark.asyncio
async def test_a_seat_scope_refusal_is_published_under_its_durable_event_id(
    repository: Repository, skill_registry: SkillRegistry
):
    """The live refusal must not arrive as a second, undeduplicable event.

    The SSE stream serves two sources for one event — the durable rows it polls
    and the live bus it forwards — and the browser de-duplicates on the event id.
    A live copy published under the bus's own id therefore renders the refusal
    twice (DRA-34). The payloads must match for the matching reason: a reload must
    not show less than the live stream already showed.
    """
    seat = await _prepare_seat_session(repository)
    bus = InMemoryLiveEventBus()

    job = await repository.enqueue_prompt_job(
        seat.id, prompt="take your turn", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
    subscriber = await bus.subscribe(job.id)

    try:
        prompt_run = _make_prompt_run_service(
            repository,
            FakeBifrost(
                responses=[
                    ChatResponse(
                        content="",
                        tool_calls=[
                            ToolCall(
                                id="tool-1",
                                name="game-service_next_step",
                                arguments={"groupId": "player3Play"},
                            )
                        ],
                        raw={},
                    ),
                    ChatResponse(content="finished", tool_calls=[], raw={}),
                ]
            ),
            FakeMcp(),
            skill_registry,
            live_event_bus=bus,
        )
        await prompt_run.run(claimed)

        stored = [
            event
            for event in await repository.list_events(job.id)
            if event.event_type == "seat_scope_violation"
        ]
        assert len(stored) == 1

        published = []
        while True:
            event = await subscriber.get(timeout_seconds=0.05)
            if event is None:
                break
            if event.event_type == "seat_scope_violation":
                published.append(event)
        assert len(published) == 1
        assert published[0].durable_event_id == str(stored[0].id)
        assert published[0].payload_json == stored[0].payload_json
    finally:
        await subscriber.aclose()
