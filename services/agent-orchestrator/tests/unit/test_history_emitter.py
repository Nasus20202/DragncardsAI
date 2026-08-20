from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.history_emitter import (
    MARVEL_LCG_OPTION_PAYLOAD_KEY,
    HistoryEventEmitter,
    InMemoryHistoryEventBus,
    build_idempotency_key,
    extract_game_id,
    extract_game_platform,
    is_game_mutating_tool,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
    extract_marvel_lcg_option_identity,
)
from agent_orchestrator.runtime.platforms import DEFAULT_PLATFORM, PLATFORM_MARVEL_LCG
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

GAME_ID = "11111111-1111-1111-1111-111111111111"
OTHER_GAME_ID = "22222222-2222-2222-2222-222222222222"


class GameServiceFakeMcp:
    """Fake game-service MCP: create_game returns a session id, mutating tools echo it."""

    def __init__(
        self,
        error_tools: frozenset[str] | None = None,
        create_platform: str | None = None,
        state_platform: str | None = None,
        state_pending_seats: bool = False,
    ) -> None:
        self.calls: list[dict] = []
        self._error_tools = error_tools or frozenset()
        self._create_platform = create_platform
        self._state_platform = state_platform
        self._state_pending_seats = state_pending_seats

    async def list_tools(self, server_url, transport, headers=None):
        return [
            McpToolDefinition(
                name="create_game",
                description="Create a game",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="get_game_state",
                description="Read the current game state",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="list_game_options",
                description="List the current options",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="list_marvel_lcg_scenarios",
                description="List Marvel LCG scenarios",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="list_marvel_lcg_decks",
                description="List Marvel LCG decks",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="choose_game_option",
                description="Choose an option",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        self.calls.append({"tool_name": tool_name, "arguments": arguments})
        if tool_name == "create_game":
            body = {"session": {"session_id": GAME_ID}}
            if self._create_platform is not None:
                body["session"]["platform"] = self._create_platform
        elif tool_name == "get_game_state":
            state = {"roundNumber": 1, "mode": "in progress"}
            if self._state_platform is not None:
                state["platform"] = self._state_platform
            if self._state_pending_seats:
                state["pendingSeats"] = ["player1"]
            body = {"session_id": GAME_ID, "state": state}
        elif tool_name == "list_game_options":
            body = {
                "options": [
                    {
                        "id": "option-7",
                        "name": "Play",
                        "event": "player_turn",
                    }
                ]
            }
        elif tool_name == "list_marvel_lcg_scenarios":
            body = {"scenarios": []}
        elif tool_name == "list_marvel_lcg_decks":
            body = {"decks": []}
        else:
            body = {"session_id": GAME_ID, "ok": True}
        return {
            "is_error": tool_name in self._error_tools,
            "content": [{"type": "text", "text": json.dumps(body)}],
        }


class ExplodingHistoryBus:
    async def next_producer_offset(self, game_id: str) -> int:
        raise RuntimeError("valkey down")

    async def publish(self, envelope) -> None:
        raise RuntimeError("valkey down")

    async def aclose(self) -> None:
        return None


class FakeBifrost:
    def __init__(self, responses):
        self.responses = responses

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name):
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
        return self.responses.pop(0)


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
    await repo.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    await repo.enable_mcp_for_session(session.id, "game-service", enabled=True)
    return session


def _make_service(repo, bifrost, mcp, skill_registry, history_emitter):
    return PromptRunService(
        dependencies=PromptRunDependencies(
            settings=Settings(SKILL_ROOTS=str(skill_registry._roots[0])),
            repository=repo,
            bifrost_client=bifrost,
            live_event_bus=InMemoryLiveEventBus(),
            mcp_tool_catalog=McpToolCatalog(mcp),
            skill_registry=skill_registry,
            history_emitter=history_emitter,
        ),
        transcript_service=SessionTranscriptService(repo),
        schedule_child_job=lambda job_id: None,
    )


# --- Pure helper tests ----------------------------------------------------


def test_is_game_mutating_tool_distinguishes_reads_and_writes():
    assert is_game_mutating_tool("game-service", "next_step") is True
    assert is_game_mutating_tool("game-service", "get_game_state") is False
    assert is_game_mutating_tool("game-service", "list_game_options") is False
    assert is_game_mutating_tool("game-service", "list_marvel_lcg_scenarios") is False
    assert is_game_mutating_tool("game-service", "list_marvel_lcg_decks") is False
    assert is_game_mutating_tool("game-service", "create_game") is False
    assert is_game_mutating_tool("other-mcp", "next_step") is False


def test_extract_game_id_from_create_game_result():
    result = {
        "content": [
            {"type": "text", "text": json.dumps({"session": {"session_id": GAME_ID}})}
        ]
    }
    assert (
        extract_game_id(
            assignment="game-service",
            tool_name="create_game",
            arguments={},
            result=result,
        )
        == GAME_ID
    )


@pytest.mark.parametrize(
    "result",
    [
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "session": {
                                "session_id": GAME_ID,
                                "platform": PLATFORM_MARVEL_LCG,
                            }
                        }
                    ),
                }
            ]
        },
        {
            "content": [
                {
                    "type": "json",
                    "data": {
                        "session_id": GAME_ID,
                        "platform": PLATFORM_MARVEL_LCG,
                    },
                }
            ]
        },
        {"session_id": GAME_ID, "platform": PLATFORM_MARVEL_LCG},
    ],
)
def test_extract_game_platform_accepts_equivalent_lifecycle_result_shapes(result):
    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="create_game",
            result=result,
        )
        == PLATFORM_MARVEL_LCG
    )


def test_extract_game_platform_preserves_legacy_no_platform_default():
    result = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"session": {"session_id": GAME_ID}}),
            }
        ]
    }
    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="attach_game",
            result=result,
        )
        is None
    )


@pytest.mark.parametrize(
    "tool_name,result",
    [
        (
            "get_game_state",
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "session_id": GAME_ID,
                                "state": {"platform": PLATFORM_MARVEL_LCG},
                            }
                        ),
                    }
                ]
            },
        ),
        (
            "lookup_session_by_slug",
            {
                "content": [
                    {
                        "type": "json",
                        "data": {
                            "session": {
                                "session_id": GAME_ID,
                                "platform": PLATFORM_MARVEL_LCG,
                            }
                        },
                    }
                ]
            },
        ),
    ],
)
def test_extract_game_platform_discovers_marvel_from_read_only_results(
    tool_name, result
):
    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name=tool_name,
            arguments={"session_id": GAME_ID},
            result=result,
            expected_game_id=GAME_ID,
        )
        == PLATFORM_MARVEL_LCG
    )


def test_extract_game_platform_recognises_legacy_marvel_state_marker():
    result = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "session_id": GAME_ID,
                        "state": {"pendingSeats": ["player1"]},
                    }
                ),
            }
        ]
    }

    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="get_game_state",
            arguments={"session_id": GAME_ID},
            result=result,
            expected_game_id=GAME_ID,
        )
        == PLATFORM_MARVEL_LCG
    )


def test_extract_game_platform_rejects_an_argument_id_conflicting_with_expected_id():
    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="list_game_options",
            arguments={"session_id": OTHER_GAME_ID},
            result={"content": [{"type": "text", "text": '{"options": []}'}]},
            expected_game_id=GAME_ID,
        )
        is None
    )


def test_extract_game_platform_rejects_a_result_id_conflicting_with_expected_id():
    result = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "session_id": OTHER_GAME_ID,
                        "platform": PLATFORM_MARVEL_LCG,
                    }
                ),
            }
        ]
    }

    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="list_game_options",
            arguments={"session_id": GAME_ID},
            result=result,
            expected_game_id=GAME_ID,
        )
        is None
    )


def _list_games_result(sessions: list[dict]) -> dict:
    return {
        "content": [
            {
                "type": "json",
                "data": {"sessions": sessions},
            }
        ]
    }


def test_list_games_does_not_bind_platform_from_another_game_row():
    result = _list_games_result(
        [{"session_id": OTHER_GAME_ID, "platform": PLATFORM_MARVEL_LCG}]
    )

    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="list_games",
            result=result,
            expected_game_id=GAME_ID,
        )
        is None
    )


def test_list_games_binds_platform_from_the_matching_row_in_mixed_results():
    result = _list_games_result(
        [
            {"session_id": OTHER_GAME_ID, "platform": DEFAULT_PLATFORM},
            {"session_id": GAME_ID, "platform": PLATFORM_MARVEL_LCG},
        ]
    )

    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="list_games",
            result=result,
            expected_game_id=GAME_ID,
        )
        == PLATFORM_MARVEL_LCG
    )


def test_list_games_matching_row_without_platform_keeps_legacy_default():
    result = _list_games_result(
        [
            {"session_id": OTHER_GAME_ID, "platform": PLATFORM_MARVEL_LCG},
            {"session_id": GAME_ID},
        ]
    )

    assert (
        extract_game_platform(
            assignment="game-service",
            tool_name="list_games",
            result=result,
            expected_game_id=GAME_ID,
        )
        is None
    )


def _source_result(game_id: str, platform: str | None = None) -> dict:
    session = {"session_id": game_id}
    if platform is not None:
        session["platform"] = platform
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"session": session}),
            }
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["attach_game", "lookup_session_by_slug"])
async def test_source_tool_initial_binding_keeps_platform_discovery(
    repository, skill_registry, tool_name
):
    session = await _prepare_session(repository)
    service = _make_service(
        repository,
        FakeBifrost([]),
        GameServiceFakeMcp(),
        skill_registry,
        HistoryEventEmitter(bus=InMemoryHistoryEventBus()),
    )

    await service._capture_game_id(
        session=session,
        assignment="game-service",
        tool_name=tool_name,
        arguments={},
        result=_source_result(GAME_ID, PLATFORM_MARVEL_LCG),
    )

    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json == {
        "game_id": GAME_ID,
        "platform": PLATFORM_MARVEL_LCG,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["attach_game", "lookup_session_by_slug"])
async def test_bound_session_rejects_conflicting_source_tool_result(
    repository, skill_registry, tool_name
):
    session = await _prepare_session(repository)
    await repository.update_session(
        session.id,
        metadata_json={"game_id": GAME_ID, "platform": DEFAULT_PLATFORM},
    )
    session = await repository.get_session(session.id)
    service = _make_service(
        repository,
        FakeBifrost([]),
        GameServiceFakeMcp(),
        skill_registry,
        HistoryEventEmitter(bus=InMemoryHistoryEventBus()),
    )

    assert (
        await service._capture_game_id(
            session=session,
            assignment="game-service",
            tool_name=tool_name,
            arguments={},
            result=_source_result(OTHER_GAME_ID, PLATFORM_MARVEL_LCG),
        )
        is None
    )

    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json == {
        "game_id": GAME_ID,
        "platform": DEFAULT_PLATFORM,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["attach_game", "lookup_session_by_slug"])
async def test_same_game_source_result_without_platform_keeps_legacy_default(
    repository, skill_registry, tool_name
):
    session = await _prepare_session(repository)
    await repository.update_session(
        session.id,
        metadata_json={"game_id": GAME_ID, "platform": DEFAULT_PLATFORM},
    )
    session = await repository.get_session(session.id)
    service = _make_service(
        repository,
        FakeBifrost([]),
        GameServiceFakeMcp(),
        skill_registry,
        HistoryEventEmitter(bus=InMemoryHistoryEventBus()),
    )

    await service._capture_game_id(
        session=session,
        assignment="game-service",
        tool_name=tool_name,
        arguments={},
        result=_source_result(GAME_ID),
    )

    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json == {
        "game_id": GAME_ID,
        "platform": DEFAULT_PLATFORM,
    }


def test_extract_game_id_from_arguments():
    assert (
        extract_game_id(
            assignment="game-service",
            tool_name="next_step",
            arguments={"session_id": GAME_ID},
            result={"content": []},
        )
        == GAME_ID
    )


def test_extract_game_id_ignores_nested_id_in_non_lifecycle_result():
    """A mutating tool's result body is NOT trusted to name the session id.

    Only the call's own ``session_id`` argument is used; a nested id in an
    unrelated result payload must not be captured (finding #9).
    """
    result = {
        "content": [
            {"type": "text", "text": json.dumps({"session": {"session_id": "other"}})}
        ]
    }
    # No session_id argument -> no game_id, despite the nested id in the result.
    assert (
        extract_game_id(
            assignment="game-service",
            tool_name="next_step",
            arguments={},
            result=result,
        )
        is None
    )
    # When an argument names the session, the argument wins over the nested id.
    assert (
        extract_game_id(
            assignment="game-service",
            tool_name="next_step",
            arguments={"session_id": GAME_ID},
            result=result,
        )
        == GAME_ID
    )


def _option_result_messages(
    options: list[dict], *, is_error: bool = False
) -> list[dict]:
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "list-call",
                    "function": {"name": "game-service_list_game_options"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "list-call",
            "content": json.dumps(
                {
                    "is_error": is_error,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"options": options}),
                        }
                    ],
                }
            ),
        },
    ]


def test_extract_marvel_option_identity_uses_the_successful_list_result():
    identity = extract_marvel_lcg_option_identity(
        tool_name="choose_game_option",
        arguments={"option_id": "option-7", "targets": [], "resources": {}},
        messages=_option_result_messages(
            [
                {
                    "id": "option-7",
                    "name": "Play",
                    "event": "player_turn",
                }
            ]
        ),
    )

    assert identity == {
        "id": "option-7",
        "name": "Play",
        "event": "player_turn",
    }


def test_extract_marvel_option_identity_does_not_invent_missing_producer_fields():
    identity = extract_marvel_lcg_option_identity(
        tool_name="choose_game_option",
        arguments={
            "option_id": "option-7",
            "name": "Play",
            "event": "player_turn",
        },
        messages=_option_result_messages([{"id": "option-7", "name": "Play"}]),
    )

    assert identity is None


def test_extract_marvel_option_identity_ignores_failed_list_results():
    identity = extract_marvel_lcg_option_identity(
        tool_name="choose_game_option",
        arguments={"option_id": "option-7"},
        messages=_option_result_messages(
            [
                {
                    "id": "option-7",
                    "name": "Play",
                    "event": "player_turn",
                }
            ],
            is_error=True,
        ),
    )

    assert identity is None


def test_extract_marvel_option_identity_ignores_options_from_other_tools():
    identity = extract_marvel_lcg_option_identity(
        tool_name="choose_game_option",
        arguments={"option_id": "option-7"},
        messages=[
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "state-call",
                        "function": {"name": "game-service_get_game_state"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "state-call",
                "content": json.dumps(
                    {"options": [{"id": "option-7", "name": "Play", "event": "turn"}]}
                ),
            },
        ],
    )

    assert identity is None


def test_agent_move_matches_the_marvel_evaluator_option_contract():
    envelope = HistoryEventEmitter.build_envelope(
        game_id=GAME_ID,
        intended_action="choose_game_option",
        reasoning="choose the legal play",
        arguments={"option_id": "option-7"},
        conversation_context=[],
        producer_offset=1,
        platform=PLATFORM_MARVEL_LCG,
        marvel_lcg_option={
            "id": "option-7",
            "name": "Play",
            "event": "player_turn",
        },
    )

    assert envelope["platform"] == PLATFORM_MARVEL_LCG
    assert envelope["payload"][MARVEL_LCG_OPTION_PAYLOAD_KEY] == {
        "id": "option-7",
        "name": "Play",
        "event": "player_turn",
    }
    assert "option_identity" not in envelope["payload"]
    assert set(envelope["payload"][MARVEL_LCG_OPTION_PAYLOAD_KEY]) == {
        "id",
        "name",
        "event",
    }


def test_idempotency_key_is_stable_and_offset_dependent():
    a = build_idempotency_key(GAME_ID, "agent", 1)
    assert a == build_idempotency_key(GAME_ID, "agent", 1)
    assert a != build_idempotency_key(GAME_ID, "agent", 2)


class OrderRecordingBus:
    """Bus that yields between offset-assign and publish and makes lower offsets
    publish slower, so an unserialized emitter would publish out of offset order.
    """

    def __init__(self) -> None:
        self._counter = 0
        self.published_offsets: list[int] = []

    async def next_producer_offset(self, game_id: str) -> int:
        await asyncio.sleep(0)  # let other pending emissions interleave
        self._counter += 1
        return self._counter

    async def publish(self, envelope) -> None:
        offset = envelope["producer_offset"]
        # Invert the natural order: without a lock, a later (higher) offset would
        # win the race to the stream because it sleeps for less time.
        await asyncio.sleep((10 - offset) * 0.005)
        self.published_offsets.append(offset)

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_concurrent_emissions_publish_in_offset_order():
    """Fire-and-forget emissions for one game must reach the stream in the same
    order their producer offsets were assigned (the history-service assigns seq
    by arrival order, so out-of-order publish would reorder the timeline)."""
    bus = OrderRecordingBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=True)

    tasks = [
        asyncio.create_task(
            emitter.emit_agent_move(
                game_id=GAME_ID,
                intended_action=f"move-{i}",
                reasoning="",
                arguments={},
                conversation_context=[],
            )
        )
        for i in range(5)
    ]
    envelopes = await asyncio.gather(*tasks)

    # Publish order matches offset-assignment order (1..5), not the inverted
    # order the per-offset sleeps would otherwise force.
    assert bus.published_offsets == [1, 2, 3, 4, 5]
    assert [e["producer_offset"] for e in envelopes] == [1, 2, 3, 4, 5]


# --- Emission integration through prompt_run ------------------------------


@pytest.mark.asyncio
async def test_emits_agent_event_per_mutating_tool_call(repository, skill_registry):
    session = await _prepare_session(repository)
    await repository.update_session(
        session.id,
        metadata_json={"platform": PLATFORM_MARVEL_LCG},
    )
    await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()

    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=True)
    mcp = GameServiceFakeMcp()
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                # Round 1: create the game (captures game_id, not a move).
                ChatResponse(
                    content="Let me start a game.",
                    tool_calls=[
                        ToolCall(id="t1", name="game-service_create_game", arguments={})
                    ],
                    raw={},
                ),
                # Round 2: a game-mutating move.
                ChatResponse(
                    content="I will advance the step now.",
                    tool_calls=[
                        ToolCall(id="t2", name="game-service_next_step", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
        emitter,
    )

    await service.run(claimed)

    # Exactly one agent move event for the single game-mutating tool call.
    assert len(bus.events) == 1
    envelope = bus.events[0]
    assert envelope["envelope_version"] == 1
    assert envelope["actor"] == "agent"
    assert envelope["game_id"] == GAME_ID
    assert envelope["platform"] == PLATFORM_MARVEL_LCG
    assert envelope["producer_offset"] == 1
    assert "event_id" in envelope and "occurred_at" in envelope
    assert envelope["idempotency_key"] == build_idempotency_key(GAME_ID, "agent", 1)

    payload = envelope["payload"]
    assert payload["intended_action"] == "next_step"
    assert payload["reasoning"] == "I will advance the step now."
    assert payload["arguments"] == {}

    # Full conversation context must be present and include the move + result.
    context = payload["conversation_context"]
    roles = [m.get("role") for m in context]
    assert roles[0] == "system"
    assert "assistant" in roles and "tool" in roles
    tool_messages = [m for m in context if m.get("role") == "tool"]
    assert tool_messages, "expected at least one tool result in the context"

    # game_id captured and persisted on the session for reuse across moves.
    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json["game_id"] == GAME_ID


@pytest.mark.asyncio
async def test_option_listing_is_not_a_move_and_choice_records_its_identity(
    repository, skill_registry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None and claimed is not None

    bus = InMemoryHistoryEventBus()
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="create",
                    tool_calls=[
                        ToolCall(id="t1", name="game-service_create_game", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(
                    content="inspect options",
                    tool_calls=[
                        ToolCall(
                            id="t2",
                            name="game-service_list_game_options",
                            arguments={},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(
                    content="choose option-7",
                    tool_calls=[
                        ToolCall(
                            id="t3",
                            name="game-service_choose_game_option",
                            arguments={"option_id": "option-7"},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        GameServiceFakeMcp(create_platform=PLATFORM_MARVEL_LCG),
        skill_registry,
        HistoryEventEmitter(bus=bus),
    )

    await service.run(claimed)

    assert len(bus.events) == 1
    event = bus.events[0]
    assert event["platform"] == PLATFORM_MARVEL_LCG
    assert event["payload"]["intended_action"] == "choose_game_option"
    assert event["payload"][MARVEL_LCG_OPTION_PAYLOAD_KEY] == {
        "id": "option-7",
        "name": "Play",
        "event": "player_turn",
    }
    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json["game_id"] == GAME_ID
    assert refreshed.metadata_json["platform"] == PLATFORM_MARVEL_LCG


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    ["list_marvel_lcg_scenarios", "list_marvel_lcg_decks"],
)
async def test_marvel_catalog_reads_do_not_emit_agent_moves(
    repository, skill_registry, tool_name
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="inspect catalog", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None and claimed is not None

    bus = InMemoryHistoryEventBus()
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="inspect the catalog",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name=f"game-service_{tool_name}",
                            arguments={"session_id": GAME_ID},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        GameServiceFakeMcp(),
        skill_registry,
        HistoryEventEmitter(bus=bus),
    )

    await service.run(claimed)

    assert bus.events == []
    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json == {"game_id": GAME_ID}


@pytest.mark.asyncio
async def test_read_only_state_binds_marvel_before_a_subsequent_option_choice(
    repository, skill_registry
):
    session = await _prepare_session(repository)
    await repository.update_session(session.id, metadata_json={"game_id": GAME_ID})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="continue this game", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None and claimed is not None

    bus = InMemoryHistoryEventBus()
    mcp = GameServiceFakeMcp(state_pending_seats=True)
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="inspect the existing game",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="game-service_get_game_state",
                            arguments={"session_id": GAME_ID},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(
                    content="inspect options",
                    tool_calls=[
                        ToolCall(
                            id="t2",
                            name="game-service_list_game_options",
                            arguments={"session_id": GAME_ID},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(
                    content="choose option-7",
                    tool_calls=[
                        ToolCall(
                            id="t3",
                            name="game-service_choose_game_option",
                            arguments={"session_id": GAME_ID, "option_id": "option-7"},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
        HistoryEventEmitter(bus=bus),
    )

    await service.run(claimed)

    assert [call["tool_name"] for call in mcp.calls] == [
        "get_game_state",
        "list_game_options",
        "choose_game_option",
    ]
    move_events = [event for event in bus.events if event["event_type"] == "agent_move"]
    assert len(move_events) == 1
    move = move_events[0]
    assert move["platform"] == PLATFORM_MARVEL_LCG
    assert move["payload"]["intended_action"] == "choose_game_option"
    assert move["payload"][MARVEL_LCG_OPTION_PAYLOAD_KEY] == {
        "id": "option-7",
        "name": "Play",
        "event": "player_turn",
    }
    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json == {
        "game_id": GAME_ID,
        "platform": PLATFORM_MARVEL_LCG,
    }


@pytest.mark.asyncio
async def test_read_only_other_game_cannot_rebind_bound_session_platform(
    repository, skill_registry
):
    session = await _prepare_session(repository)
    await repository.update_session(
        session.id,
        metadata_json={"game_id": GAME_ID, "platform": DEFAULT_PLATFORM},
    )
    job = await repository.enqueue_prompt_job(
        session.id, prompt="inspect another game", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None and claimed is not None

    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="inspect options",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="game-service_list_game_options",
                            arguments={"session_id": OTHER_GAME_ID},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        GameServiceFakeMcp(),
        skill_registry,
        HistoryEventEmitter(bus=InMemoryHistoryEventBus()),
    )

    await service.run(claimed)

    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json == {
        "game_id": GAME_ID,
        "platform": DEFAULT_PLATFORM,
    }


@pytest.mark.asyncio
async def test_legacy_lifecycle_result_keeps_dragncards_default(
    repository, skill_registry
):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    assert job is not None and claimed is not None

    bus = InMemoryHistoryEventBus()
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="create",
                    tool_calls=[
                        ToolCall(id="t1", name="game-service_create_game", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(
                    content="advance",
                    tool_calls=[
                        ToolCall(id="t2", name="game-service_next_step", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        GameServiceFakeMcp(),
        skill_registry,
        HistoryEventEmitter(bus=bus),
    )

    await service.run(claimed)

    assert len(bus.events) == 1
    assert bus.events[0]["platform"] == DEFAULT_PLATFORM
    refreshed = await repository.get_session(session.id)
    assert refreshed.metadata_json["game_id"] == GAME_ID
    assert "platform" not in refreshed.metadata_json


@pytest.mark.asyncio
async def test_no_emission_when_mutating_tool_call_errors(repository, skill_registry):
    """A game-mutating tool call that returns is_error is not an agent move."""
    session = await _prepare_session(repository)
    await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()

    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=True)
    mcp = GameServiceFakeMcp(error_tools=frozenset({"next_step"}))
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="Let me start a game.",
                    tool_calls=[
                        ToolCall(id="t1", name="game-service_create_game", arguments={})
                    ],
                    raw={},
                ),
                # This mutating call fails in-game (is_error True).
                ChatResponse(
                    content="advance",
                    tool_calls=[
                        ToolCall(id="t2", name="game-service_next_step", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
        emitter,
    )

    await service.run(claimed)

    # The failed move produced no agent event.
    assert bus.events == []


@pytest.mark.asyncio
async def test_emission_failure_does_not_break_job(repository, skill_registry):
    session = await _prepare_session(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()

    emitter = HistoryEventEmitter(bus=ExplodingHistoryBus(), enabled=True)
    mcp = GameServiceFakeMcp()
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="advance",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="game-service_next_step",
                            arguments={"session_id": GAME_ID},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
        emitter,
    )

    await service.run(claimed)

    stored = await repository.get_job(job.id)
    assert stored.status == "completed"
    assert stored.result_text == "finished"


@pytest.mark.asyncio
async def test_emits_user_prompt_event_when_session_has_game_id(
    repository, skill_registry
):
    """A prompt on a session that already has a game emits a user_prompt event."""
    session = await _prepare_session(repository)
    # Simulate a follow-up turn: the session already carries the game_id from a
    # prior turn (no game-creating tool call this turn).
    await repository.update_session(session.id, metadata_json={"game_id": GAME_ID})
    await repository.enqueue_prompt_job(
        session.id, prompt="attack the villain", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()

    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=True)
    service = _make_service(
        repository,
        FakeBifrost(responses=[ChatResponse(content="ok", tool_calls=[], raw={})]),
        GameServiceFakeMcp(),
        skill_registry,
        emitter,
    )

    await service.run(claimed)

    user_events = [e for e in bus.events if e["actor"] == "user"]
    assert len(user_events) == 1
    envelope = user_events[0]
    assert envelope["event_type"] == "user_prompt"
    assert envelope["game_id"] == GAME_ID
    assert envelope["payload"] == {"prompt": "attack the villain"}
    # The system prompt is NOT carried on the timeline event.
    assert "system_prompt" not in envelope["payload"]
    assert envelope["idempotency_key"] == build_idempotency_key(GAME_ID, "user", 1)


@pytest.mark.asyncio
async def test_no_user_prompt_event_without_game_id(repository, skill_registry):
    """The very first prompt (no game yet) emits no user_prompt event."""
    session = await _prepare_session(repository)
    await repository.enqueue_prompt_job(
        session.id, prompt="let's play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()

    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=True)
    service = _make_service(
        repository,
        FakeBifrost(responses=[ChatResponse(content="ok", tool_calls=[], raw={})]),
        GameServiceFakeMcp(),
        skill_registry,
        emitter,
    )

    await service.run(claimed)

    assert [e for e in bus.events if e["actor"] == "user"] == []


@pytest.mark.asyncio
async def test_no_emission_when_emitter_disabled(repository, skill_registry):
    session = await _prepare_session(repository)
    await repository.enqueue_prompt_job(
        session.id, prompt="play", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()

    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=False)
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="advance",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="game-service_next_step",
                            arguments={"session_id": GAME_ID},
                        )
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        GameServiceFakeMcp(),
        skill_registry,
        emitter,
    )

    await service.run(claimed)
    assert bus.events == []


# --- Session mode threaded through prompt_run ------------------------------


async def _prepare_orchestrated_session(repo: Repository):
    """A session in orchestrated mode, otherwise identical to ``_prepare_session``."""
    session = await repo.create_session("demo", {}, session_mode="orchestrated")
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


async def _run_one_move(repository, skill_registry, session, emitter):
    """Drive one prompt that plays a single game-mutating move."""
    await repository.enqueue_prompt_job(
        session.id, prompt="advance the step", metadata_json={}, max_attempts=1
    )
    claimed = await repository.claim_next_job()
    service = _make_service(
        repository,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="Advancing.",
                    tool_calls=[
                        ToolCall(id="t1", name="game-service_next_step", arguments={})
                    ],
                    raw={},
                ),
                ChatResponse(content="done", tool_calls=[], raw={}),
            ]
        ),
        GameServiceFakeMcp(),
        skill_registry,
        emitter,
    )
    await service.run(claimed)


@pytest.mark.asyncio
async def test_an_orchestrated_sessions_events_state_the_mode(
    repository, skill_registry
):
    """The mode reaches the wire, not just the envelope builder.

    Both events a turn produces are checked: the ``user_prompt`` that triggered it
    and the ``agent_move`` it produced. A prompt given to an orchestrated session
    is as much part of that timeline as the move it caused.
    """
    session = await _prepare_orchestrated_session(repository)
    await repository.update_session(session.id, metadata_json={"game_id": GAME_ID})
    bus = InMemoryHistoryEventBus()

    await _run_one_move(
        repository, skill_registry, session, HistoryEventEmitter(bus=bus, enabled=True)
    )

    by_type = {e["event_type"]: e for e in bus.events}
    assert by_type["user_prompt"]["payload"]["session_mode"] == "orchestrated"
    assert by_type["agent_move"]["payload"]["session_mode"] == "orchestrated"
    # The orchestrating session holds no seat of its own, so its move names none —
    # and the mode is still readable without that seat.
    assert "player" not in by_type["agent_move"]["payload"]


@pytest.mark.asyncio
async def test_a_chat_sessions_events_carry_no_mode_key(repository, skill_registry):
    """The default path is byte-for-byte what it was before the mode existed."""
    session = await _prepare_session(repository)
    await repository.update_session(session.id, metadata_json={"game_id": GAME_ID})
    bus = InMemoryHistoryEventBus()

    await _run_one_move(
        repository, skill_registry, session, HistoryEventEmitter(bus=bus, enabled=True)
    )

    assert {e["event_type"] for e in bus.events} == {"user_prompt", "agent_move"}
    for envelope in bus.events:
        assert "session_mode" not in envelope["payload"]
