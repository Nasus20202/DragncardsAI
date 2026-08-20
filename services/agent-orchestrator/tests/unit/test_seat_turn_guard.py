"""Turn and phase authority: the pure rule and its wiring in the dispatch path.

Two layers, mirroring how the seat guard is tested (`test_seat_guard.py` for the
pure rule, `test_prompt_run.py` for the wiring):

- `check_turn_authority` decides from the tool name and the neutral phase
  classification whether a seat's call is one no seat could make at that step.
  The phase label and step id are opaque reporting values only.
  The acting player within the player phase is not in game state (root
  `AGENTS.md`), so that slice is deliberately not judged here.
- The wiring tests run a seat's job through the real `PromptRunService` and
  assert that an out-of-turn call records a DRA-30 illegal-action finding — the
  row, the live `illegal_action_finding` event, and the `illegal_action`
  history emission — while the call still dispatches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import ChatResponse, ToolCall
from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.repositories.player_channel import (
    ILLEGAL_ACTION_STATUS_OPEN,
)
from agent_orchestrator.runtime.history_emitter import SESSION_GAME_ID_KEY
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.platforms import PLATFORM_MARVEL_LCG
from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
)
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
)
from agent_orchestrator.runtime.seat_turn_guard import (
    PHASE_ADVANCING_TOOLS,
    SEAT_ACTION_TOOLS,
    TurnAuthorityViolation,
    check_turn_authority,
)
from agent_orchestrator.runtime.session_modes import SESSION_MODE_ORCHESTRATED
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

# ---------------------------------------------------------------------------
# The pure rule
# ---------------------------------------------------------------------------


def _check(
    tool_name: str,
    phase: str | None,
    caller: str = "player1",
    *,
    step_id: Any = None,
    pending_seats: Any = None,
    platform: str = "dragncards",
):
    return check_turn_authority(
        caller_player_id=caller,
        tool_name=tool_name,
        step_id=step_id,
        phase=phase,
        pending_seats=pending_seats,
        platform=platform,
    )


@pytest.mark.parametrize(
    "tool_name",
    sorted(PHASE_ADVANCING_TOOLS),
)
def test_phase_tools_are_only_legal_during_the_player_phase(tool_name: str):
    assert _check(tool_name, "player") is None

    for phase in ("villain", "passive"):
        violation = _check(tool_name, phase)
        assert violation is not None
        assert violation.kind == "phase_advance"
        assert violation.tool_name == tool_name


@pytest.mark.parametrize(
    "tool_name",
    sorted(SEAT_ACTION_TOOLS),
)
def test_action_tools_are_only_legal_during_the_player_phase(tool_name: str):
    assert _check(tool_name, "player") is None

    violation = _check(tool_name, "villain")
    assert violation is not None
    assert violation.kind == "action"


# The three ticket scenarios, named as DRA-62 describes them.


def test_a_seat_calling_next_step_during_another_seats_turn_is_a_finding():
    """`next_step` while the villain phase resolves — no seat holds the turn."""
    violation = _check("next_step", "villain", caller="player1", step_id="opaque")
    assert violation is not None
    assert violation.kind == "phase_advance"
    assert violation.caller_player_id == "player1"
    assert violation.phase == "villain"
    assert violation.step_id == "opaque"
    assert "next_step" in violation.message
    assert "villain phase" in violation.message


def test_a_seat_calling_player_end_phase_out_of_turn_is_a_finding():
    violation = _check("player_end_phase", "villain", caller="player2")
    assert violation is not None
    assert violation.kind == "phase_advance"
    assert violation.caller_player_id == "player2"
    assert violation.required_undo  # the seat is told what to repair


def test_a_seat_calling_an_action_tool_during_the_villain_phase_is_a_finding():
    violation = _check("move_card", "villain", caller="player1")
    assert violation is not None
    assert violation.kind == "action"
    assert violation.phase == "villain"
    assert violation.required_undo


def test_a_seat_acting_during_its_own_turn_is_not_a_finding():
    assert _check("move_card", "player") is None
    assert _check("draw_card", "player") is None
    assert _check("next_step", "player") is None


def test_passive_phase_steps_belong_to_no_seat():
    assert _check("next_step", "passive") is not None
    assert _check("move_card", "passive") is not None


def test_read_only_lifecycle_and_setup_tools_never_fire():
    for tool_name in (
        "get_game_state",
        "list_actions",
        "get_session_actions",
        "search_cards_marvel_champions",
        "create_game",
        "attach_game",
        "delete_game",
        "load_prebuilt_deck",
        "load_cards",
        "unload_cards",
        "set_player_count_action",
        "mulligan_draw_hand",
    ):
        assert _check(tool_name, "villain") is None, tool_name
        assert _check(tool_name, "passive") is None, tool_name


def test_an_unknown_or_missing_phase_never_fires():
    for phase in (None, "unknown", "not-a-phase"):
        assert _check("next_step", phase) is None
        assert _check("move_card", phase) is None


def test_a_pending_seat_can_act_even_when_the_phase_is_not_player():
    assert (
        _check(
            "choose_game_option",
            "villain",
            pending_seats=["player1"],
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )
    assert (
        _check(
            "choose_game_option",
            "passive",
            pending_seats=["player1"],
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )


def test_a_seat_absent_from_pending_decisions_gets_a_finding():
    violation = _check(
        "choose_game_option",
        "player",
        caller="player1",
        pending_seats=["player2"],
        platform=PLATFORM_MARVEL_LCG,
    )
    assert violation is not None
    assert violation.kind == "action"


def test_the_violation_names_the_board_as_it_was():
    violation = _check("modify_tokens", "villain", step_id="opaque-step")
    assert isinstance(violation, TurnAuthorityViolation)
    assert violation.step_id == "opaque-step"
    assert violation.phase == "villain"
    assert "step opaque-step" in violation.message


# ---------------------------------------------------------------------------
# The wiring: detection in the dispatch path, finding in the DRA-30 store
# ---------------------------------------------------------------------------


class FakeBifrost:
    def __init__(self, responses=None):
        self.responses = responses or []

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
        return self.responses.pop(0)


class StatefulMcp:
    """A game-service fake that serves a scripted board to `get_game_state`."""

    def __init__(self, state: dict[str, Any] | None = None):
        self.state = state
        self.calls: list[dict[str, Any]] = []
        self._definitions = [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="player_end_phase",
                description="End the player phase",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolDefinition(
                name="move_card",
                description="Move a card",
                input_schema={
                    "type": "object",
                    "properties": {"instance_id": {"type": "string"}},
                },
            ),
            McpToolDefinition(
                name="get_game_state",
                description="Read the board",
                input_schema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            ),
        ]

    async def list_tools(self, server_url, transport, headers=None):
        return list(self._definitions)

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        self.calls.append(
            {"server_url": server_url, "tool_name": tool_name, "arguments": arguments}
        )
        if tool_name == "get_game_state":
            if self.state is None:
                return {"is_error": True, "content": []}
            return {
                "is_error": False,
                "content": [
                    {"session_id": arguments["session_id"], "state": self.state}
                ],
            }
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


async def _prepare_seat_session(
    repo: Repository,
    *,
    player_id: str = "player1",
    game_id: str | None = "game-1",
):
    """A seat's own session under an orchestrating session, with a game attached.

    `game_id` in the seat's metadata is what `prompt_player_agent` writes when
    it spawns the seat (it inherits the orchestrating session's game id), and it
    is the key the detection reads to know which game's state to consult.
    """
    orchestrator = await repo.create_session(
        "table", {}, session_mode=SESSION_MODE_ORCHESTRATED
    )
    seat_metadata = {
        SESSION_PLAYER_ID_KEY: player_id,
        SESSION_ORCHESTRATOR_ID_KEY: orchestrator.id,
    }
    if game_id is not None:
        seat_metadata[SESSION_GAME_ID_KEY] = game_id
    seat = await repo.create_session(
        f"seat-{player_id}", seat_metadata, multi_turn_memory=True
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
    return orchestrator, seat


def _make_prompt_run_service(
    repo: Repository,
    bifrost: FakeBifrost,
    mcp: StatefulMcp,
    skill_registry: SkillRegistry,
    live_event_bus: InMemoryLiveEventBus | None = None,
    history_emitter: Any | None = None,
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
            history_emitter=history_emitter,
        ),
        transcript_service=SessionTranscriptService(repo),
        schedule_child_job=lambda job_id: None,
    )


async def _run_seat_tool_call(
    repo: Repository,
    skill_registry: SkillRegistry,
    mcp: StatefulMcp,
    *,
    seat_id: str,
    tool_name: str,
    arguments: dict | None = None,
    history_emitter: Any | None = None,
) -> tuple[Any, InMemoryLiveEventBus]:
    """Run one seat job whose model asks for one tool call, then finishes."""
    job = await repo.enqueue_prompt_job(
        seat_id, prompt="take your turn", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None

    bus = InMemoryLiveEventBus()
    prompt_run = _make_prompt_run_service(
        repo,
        FakeBifrost(
            responses=[
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id="tool-1", name=tool_name, arguments=arguments or {})
                    ],
                    raw={},
                ),
                ChatResponse(content="finished", tool_calls=[], raw={}),
            ]
        ),
        mcp,
        skill_registry,
        live_event_bus=bus,
        history_emitter=history_emitter,
    )
    await prompt_run.run(claimed)
    return await repo.get_job(job.id), bus


@pytest.mark.asyncio
async def test_an_out_of_turn_phase_advance_records_a_finding(
    repository: Repository, skill_registry: SkillRegistry
):
    """Ticket scenario: a seat calling `next_step` out of turn, recorded.

    The board is in the neutral villain phase; the seat's call is not
    refused — the fake records the dispatch — but the finding store records it
    against the seat, open, on the orchestrating session.
    """
    orchestrator, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state={"stepId": "2.1", "phase": "villain", "playRound": 3})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_next_step",
    )
    assert stored_job is not None and stored_job.status == "completed"

    # The call still dispatched — detection is after the fact, never a refusal.
    assert [c["tool_name"] for c in mcp.calls] == ["get_game_state", "next_step"]

    findings = await repository.list_open_illegal_actions(orchestrator.id, "player1")
    assert len(findings) == 1
    finding = findings[0]
    assert finding.status == ILLEGAL_ACTION_STATUS_OPEN
    assert finding.round_number == 3
    assert "next_step" in finding.violation
    assert finding.required_undo


@pytest.mark.asyncio
async def test_an_out_of_turn_player_end_phase_records_a_finding(
    repository: Repository, skill_registry: SkillRegistry
):
    """Ticket scenario: `player_end_phase` called while the villain resolves."""
    orchestrator, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state={"stepId": "2.5", "phase": "villain", "playRound": 2})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_player_end_phase",
    )
    assert stored_job is not None and stored_job.status == "completed"

    findings = await repository.list_open_illegal_actions(orchestrator.id, "player1")
    assert len(findings) == 1
    assert findings[0].violation.startswith("Advanced the game")


@pytest.mark.asyncio
async def test_an_action_tool_during_the_villain_phase_records_a_finding(
    repository: Repository, skill_registry: SkillRegistry
):
    """Ticket scenario: a seat playing cards while the villain phase resolves."""
    orchestrator, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state={"stepId": "2.2", "phase": "villain", "playRound": 1})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_move_card",
        arguments={"instance_id": "card-1"},
    )
    assert stored_job is not None and stored_job.status == "completed"

    findings = await repository.list_open_illegal_actions(orchestrator.id, "player1")
    assert len(findings) == 1
    assert findings[0].violation.startswith("Acted out of turn")
    assert "move_card" in findings[0].violation


@pytest.mark.asyncio
async def test_the_finding_is_announced_live_and_durably(
    repository: Repository, skill_registry: SkillRegistry
):
    """The finding is a real DRA-30 announcement: live event under its durable id.

    The live copy carries the durable row's id (DRA-34) so the dashboard does
    not render it twice, and the payload is the same object persisted.
    """
    orchestrator, seat = await _prepare_seat_session(repository)
    # The seat job is enqueued first so the FIFO claim picks it up; the
    # orchestrating job only needs to exist as the finding's home.
    job = await repository.enqueue_prompt_job(
        seat.id, prompt="take your turn", metadata_json={}, max_attempts=1
    )
    assert job is not None
    orchestrating_job = await repository.enqueue_prompt_job(
        orchestrator.id, prompt="run the game", metadata_json={}, max_attempts=1
    )
    assert orchestrating_job is not None
    await repository.set_parent_job_id(job.id, orchestrating_job.id)
    mcp = StatefulMcp(state={"stepId": "2.1", "phase": "villain"})

    claimed = await repository.claim_next_job()
    assert claimed is not None and claimed.id == job.id

    bus = InMemoryLiveEventBus()
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
        live_event_bus=bus,
    )
    await prompt_run.run(claimed)

    subscriber = await bus.subscribe(orchestrating_job.id)
    try:
        durable = [
            event
            for event in await repository.list_events(orchestrating_job.id)
            if event.event_type == "illegal_action_finding"
        ]
        assert len(durable) == 1

        published = await subscriber.get(timeout_seconds=1.0)
        assert published is not None
        assert published.event_type == "illegal_action_finding"
        assert published.durable_event_id == str(durable[0].id)
        assert published.payload_json == durable[0].payload_json
        assert published.payload_json["status"] == ILLEGAL_ACTION_STATUS_OPEN
    finally:
        await subscriber.aclose()


@pytest.mark.asyncio
async def test_the_finding_emits_the_illegal_action_history_event(
    repository: Repository, skill_registry: SkillRegistry
):
    """The judge's evidence path is fed: an `illegal_action` history emission."""
    emitted: list[dict] = []

    class _Emitter:
        enabled = True

        async def emit_user_prompt(self, **kwargs):  # pragma: no cover
            return None

        async def emit_agent_move(self, **kwargs):  # pragma: no cover
            return None

        async def emit_illegal_action(self, **kwargs):
            emitted.append(kwargs)
            return kwargs

    _, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state={"stepId": "2.1", "phase": "villain", "playRound": 4})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_next_step",
        history_emitter=_Emitter(),
    )
    assert stored_job is not None and stored_job.status == "completed"

    assert len(emitted) == 1
    assert emitted[0]["game_id"] == "game-1"
    assert emitted[0]["player"] == "player1"
    assert emitted[0]["status"] == ILLEGAL_ACTION_STATUS_OPEN
    assert "next_step" in emitted[0]["violation"]
    assert emitted[0]["round_number"] == 4


@pytest.mark.asyncio
async def test_acting_during_the_player_phase_records_nothing(
    repository: Repository, skill_registry: SkillRegistry
):
    _, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state={"stepId": "1.1", "phase": "player", "playRound": 2})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_move_card",
        arguments={"instance_id": "card-1"},
    )
    assert stored_job is not None and stored_job.status == "completed"

    orchestrator_session = seat.metadata_json[SESSION_ORCHESTRATOR_ID_KEY]
    assert (
        await repository.list_open_illegal_actions(orchestrator_session, "player1")
        == []
    )
    # The board was read (the detection runs) but no finding followed.
    assert [c["tool_name"] for c in mcp.calls] == ["get_game_state", "move_card"]


@pytest.mark.asyncio
async def test_a_read_only_call_during_the_villain_phase_records_nothing(
    repository: Repository, skill_registry: SkillRegistry
):
    _, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state={"stepId": "2.2", "phase": "villain"})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_get_game_state",
        arguments={"session_id": "game-1"},
    )
    assert stored_job is not None and stored_job.status == "completed"

    # Reading is always safe: no nested read, no finding.
    assert [c["tool_name"] for c in mcp.calls] == ["get_game_state"]
    orchestrator_session = seat.metadata_json[SESSION_ORCHESTRATOR_ID_KEY]
    assert (
        await repository.list_open_illegal_actions(orchestrator_session, "player1")
        == []
    )


@pytest.mark.asyncio
async def test_a_seat_with_no_game_attached_records_nothing(
    repository: Repository, skill_registry: SkillRegistry
):
    _, seat = await _prepare_seat_session(repository, game_id=None)
    mcp = StatefulMcp(state={"stepId": "2.1", "phase": "villain"})

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_next_step",
    )
    assert stored_job is not None and stored_job.status == "completed"

    # No game id means nothing to read; the board was never consulted. The
    # seat's own call still dispatches.
    assert [c["tool_name"] for c in mcp.calls] == ["next_step"]
    orchestrator_session = seat.metadata_json[SESSION_ORCHESTRATOR_ID_KEY]
    assert (
        await repository.list_open_illegal_actions(orchestrator_session, "player1")
        == []
    )


@pytest.mark.asyncio
async def test_detection_degrades_when_the_state_read_fails(
    repository: Repository, skill_registry: SkillRegistry
):
    _, seat = await _prepare_seat_session(repository)
    mcp = StatefulMcp(state=None)  # `get_game_state` returns an error

    stored_job, _ = await _run_seat_tool_call(
        repository,
        skill_registry,
        mcp,
        seat_id=seat.id,
        tool_name="game-service_next_step",
    )
    assert stored_job is not None and stored_job.status == "completed"

    orchestrator_session = seat.metadata_json[SESSION_ORCHESTRATOR_ID_KEY]
    assert (
        await repository.list_open_illegal_actions(orchestrator_session, "player1")
        == []
    )


@pytest.mark.asyncio
async def test_the_orchestrating_job_is_not_turn_checked(
    repository: Repository, skill_registry: SkillRegistry
):
    """The orchestrator holds no seat and calls the phase tools legitimately."""
    orchestrator = await repository.create_session(
        "table", {}, session_mode=SESSION_MODE_ORCHESTRATED
    )
    await repository.set_model_config(
        orchestrator.id,
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
    await repository.enable_mcp_for_session(
        orchestrator.id, "game-service", enabled=True
    )
    mcp = StatefulMcp(state={"stepId": "2.1", "phase": "villain"})

    job = await repository.enqueue_prompt_job(
        orchestrator.id,
        prompt="run the villain phase",
        metadata_json={},
        max_attempts=1,
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
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

    stored_job = await repository.get_job(job.id)
    assert stored_job is not None and stored_job.status == "completed"
    # No state read, no finding: the orchestrating job holds no seat. Its own
    # call dispatches normally.
    assert [c["tool_name"] for c in mcp.calls] == ["next_step"]
    assert await repository.list_open_illegal_actions(orchestrator.id, "player1") == []
