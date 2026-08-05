"""Illegal-action findings: who may open one, who may close one, and when.

The asymmetry is the requirement. The orchestrating agent records a finding and
closes it after verifying the undo against game state; the seat reads it, undoes
the action with its own tools, and has no way to declare the matter settled. Every
test here exists to keep one half of that asymmetry from quietly acquiring the
other half's authority.
"""

from __future__ import annotations

import json

import pytest

from agent_orchestrator.repositories.player_channel import (
    ILLEGAL_ACTION_STATUS_OPEN,
    ILLEGAL_ACTION_STATUS_RESOLVED,
)
from agent_orchestrator.runtime.builtin_tools import (
    ILLEGAL_ACTION_FINDING_EVENT,
    build_builtin_registry,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.session_modes import SESSION_MODE_CHAT
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import (
    live_event_bus,
    make_job,
    repository,
    skill_registry,
)
from .player_channel_test_support import (
    invoke_seat,
    seat_identity_for,
    seat_session,
    table,
)

__all__ = ["live_event_bus", "repository", "skill_registry"]

VIOLATION = "Played a second Ricochet in the same phase."
REQUIRED_UNDO = "Return Ricochet to hand and refund the resource spent on it."


async def _orchestrator_registry(
    repo: Repository,
    bus: InMemoryLiveEventBus,
    skills: SkillRegistry,
    session_id: str,
    job_id: str,
    *,
    session_orchestrated: bool = True,
):
    configs = await repo.list_player_configs(session_id)
    return build_builtin_registry(
        skill_registry=skills,
        repository=repo,
        live_event_bus=bus,
        session_id=session_id,
        job_id=job_id,
        skill_assignments=[],
        job=make_job(),
        player_configs=configs,
        seat_identity=None,
        session_orchestrated=session_orchestrated,
    )


async def _seat_registry(
    repo: Repository,
    bus: InMemoryLiveEventBus,
    skills: SkillRegistry,
    session_id: str,
    player_id: str,
):
    identity = await seat_identity_for(repo, session_id, player_id)
    return build_builtin_registry(
        skill_registry=skills,
        repository=repo,
        live_event_bus=bus,
        session_id=identity.orchestrator_session_id,
        job_id="seat-job",
        skill_assignments=[],
        # A seat's job is a child of the orchestrating job, which is also why no
        # master-only tool can be reached from here.
        job=make_job(parent_job_id="orchestrating-job"),
        seat_identity=identity,
        session_orchestrated=False,
    )


async def _orchestrating_job_id(repo: Repository, session_id: str) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt="run the game", metadata_json={}, max_attempts=1
    )
    assert job is not None
    return job.id


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def _tool_names(registry) -> set[str]:
    return {tool["function"]["name"] for tool in registry.as_openai_tools()}


@pytest.mark.asyncio
async def test_the_orchestrator_opens_a_finding_and_it_is_stored_open(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    session = await table(repository)
    job_id = await _orchestrating_job_id(repository, session.id)
    registry = await _orchestrator_registry(
        repository, live_event_bus, skill_registry, session.id, job_id
    )

    result = await registry.get("report_illegal_action").handler(
        {
            "player_id": "player2",
            "violation": VIOLATION,
            "required_undo": REQUIRED_UNDO,
            "round_number": 3,
        }
    )

    assert result["is_error"] is False
    finding_id = _payload(result)["finding_id"]
    stored = await repository.get_illegal_action(finding_id)
    assert stored is not None
    assert stored.session_id == session.id
    assert stored.player_id == "player2"
    assert stored.status == ILLEGAL_ACTION_STATUS_OPEN
    assert stored.round_number == 3
    assert stored.resolved_at is None
    open_for_seat = await repository.list_open_illegal_actions(session.id, "player2")
    assert [item.id for item in open_for_seat] == [finding_id]


@pytest.mark.asyncio
async def test_opening_and_resolving_each_record_the_dashboard_payload(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    """One event type for both transitions, with `status` telling them apart.

    The keys are a fixed contract: the dashboard's ``parseIllegalActionFindingEvent``
    reads exactly these, so renaming one here silently empties a transcript row.
    """
    session = await table(repository)
    job_id = await _orchestrating_job_id(repository, session.id)
    registry = await _orchestrator_registry(
        repository, live_event_bus, skill_registry, session.id, job_id
    )
    subscriber = await live_event_bus.subscribe(job_id)

    opened = await registry.get("report_illegal_action").handler(
        {
            "player_id": "player2",
            "violation": VIOLATION,
            "required_undo": REQUIRED_UNDO,
        }
    )
    finding_id = _payload(opened)["finding_id"]
    await registry.get("resolve_illegal_action").handler(
        {
            "finding_id": finding_id,
            "resolution_note": "Read the board: Ricochet is in hand and the resource is back.",
        }
    )

    durable = [
        event.payload_json
        for event in await repository.list_events(job_id)
        if event.event_type == ILLEGAL_ACTION_FINDING_EVENT
    ]
    live: list[dict] = []
    while len(live) < 2:
        event = await subscriber.get(timeout_seconds=1.0)
        assert event is not None, "the finding was not published to the live bus"
        if event.event_type == ILLEGAL_ACTION_FINDING_EVENT:
            live.append(event.payload_json)
    await subscriber.aclose()

    for payloads in (durable, live):
        assert [payload["status"] for payload in payloads] == ["open", "resolved"]
        for payload in payloads:
            assert set(payload) == {
                "finding_id",
                "player_id",
                "violation",
                "required_undo",
                "status",
                "round_number",
                "resolution_note",
            }
            assert payload["finding_id"] == finding_id
            assert payload["player_id"] == "player2"
            assert payload["round_number"] is None
        assert payloads[0]["resolution_note"] is None
        assert "Ricochet is in hand" in payloads[1]["resolution_note"]


@pytest.mark.asyncio
async def test_a_finding_against_an_unconfigured_seat_is_refused(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    session = await table(repository, seats=("player1",))
    job_id = await _orchestrating_job_id(repository, session.id)
    registry = await _orchestrator_registry(
        repository, live_event_bus, skill_registry, session.id, job_id
    )

    result = await registry.get("report_illegal_action").handler(
        {
            "player_id": "player4",
            "violation": VIOLATION,
            "required_undo": REQUIRED_UNDO,
        }
    )

    assert result["is_error"] is True
    assert await repository.list_open_illegal_actions(session.id, "player4") == []


@pytest.mark.asyncio
async def test_an_open_finding_appears_in_two_consecutive_invocations(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await table(repository)
    seat = await seat_session(repository, session.id, "player1")
    finding = await repository.open_illegal_action(
        session.id,
        player_id="player1",
        violation=VIOLATION,
        required_undo=REQUIRED_UNDO,
        round_number=2,
    )
    assert finding is not None

    first = await invoke_seat(repository, skill_registry, seat, prompt="round two")
    second = await invoke_seat(repository, skill_registry, seat, prompt="round three")

    for messages in (first, second):
        carried = [
            message
            for message in messages
            if "illegal_action_finding" in message["content"]
        ]
        assert len(carried) == 1
        assert carried[0]["role"] == "user"
        content = carried[0]["content"]
        assert finding.id in content
        assert VIOLATION in content
        assert REQUIRED_UNDO in content
        # Never in the system prompt, where it would read as an instruction the
        # seat's own words could be confused with.
        system = next(message for message in messages if message["role"] == "system")
        assert VIOLATION not in system["content"]


@pytest.mark.asyncio
async def test_a_resolved_finding_stops_following_the_seat(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await table(repository)
    seat = await seat_session(repository, session.id, "player1")
    finding = await repository.open_illegal_action(
        session.id,
        player_id="player1",
        violation=VIOLATION,
        required_undo=REQUIRED_UNDO,
    )
    assert finding is not None

    before = await invoke_seat(repository, skill_registry, seat, prompt="round two")
    resolved = await repository.resolve_illegal_action(
        finding.id, resolution_note="Verified against game state."
    )
    assert resolved is not None
    assert resolved.status == ILLEGAL_ACTION_STATUS_RESOLVED
    after = await invoke_seat(repository, skill_registry, seat, prompt="round three")

    assert any("illegal_action_finding" in message["content"] for message in before)
    assert not any("illegal_action_finding" in message["content"] for message in after)


@pytest.mark.asyncio
async def test_a_seat_has_no_tool_that_can_resolve_a_finding(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    """Read-only for the seat, and nothing in its registry can close a finding."""
    session = await table(repository)
    await seat_session(repository, session.id, "player1")
    finding = await repository.open_illegal_action(
        session.id,
        player_id="player1",
        violation=VIOLATION,
        required_undo=REQUIRED_UNDO,
    )
    assert finding is not None
    registry = await _seat_registry(
        repository, live_event_bus, skill_registry, session.id, "player1"
    )

    names = _tool_names(registry)
    assert "resolve_illegal_action" not in names
    assert "report_illegal_action" not in names
    assert registry.get("resolve_illegal_action") is None
    assert registry.get("report_illegal_action") is None
    assert "list_my_illegal_actions" in names

    # The one finding tool a seat does hold reads and nothing else.
    result = await registry.get("list_my_illegal_actions").handler({})
    payload = _payload(result)
    assert payload["player_id"] == "player1"
    assert [entry["finding_id"] for entry in payload["open_findings"]] == [finding.id]
    reread = await repository.get_illegal_action(finding.id)
    assert reread is not None
    assert reread.status == ILLEGAL_ACTION_STATUS_OPEN


@pytest.mark.asyncio
async def test_a_seat_reads_only_its_own_findings(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    session = await table(repository)
    await seat_session(repository, session.id, "player1")
    await repository.open_illegal_action(
        session.id,
        player_id="player2",
        violation=VIOLATION,
        required_undo=REQUIRED_UNDO,
    )
    registry = await _seat_registry(
        repository, live_event_bus, skill_registry, session.id, "player1"
    )

    payload = _payload(await registry.get("list_my_illegal_actions").handler({}))

    assert payload["open_findings"] == []


@pytest.mark.asyncio
async def test_a_double_resolve_is_a_no_op(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    session = await table(repository)
    job_id = await _orchestrating_job_id(repository, session.id)
    registry = await _orchestrator_registry(
        repository, live_event_bus, skill_registry, session.id, job_id
    )
    opened = await registry.get("report_illegal_action").handler(
        {
            "player_id": "player2",
            "violation": VIOLATION,
            "required_undo": REQUIRED_UNDO,
        }
    )
    finding_id = _payload(opened)["finding_id"]
    handler = registry.get("resolve_illegal_action").handler

    first = await handler(
        {"finding_id": finding_id, "resolution_note": "Verified: card back in hand."}
    )
    second = await handler(
        {"finding_id": finding_id, "resolution_note": "Overwriting the first note."}
    )

    assert first["is_error"] is False
    assert second["is_error"] is True
    stored = await repository.get_illegal_action(finding_id)
    assert stored is not None
    assert stored.resolution_note == "Verified: card back in hand."
    # One resolution, not two: the second call recorded nothing at all.
    resolutions = [
        event
        for event in await repository.list_events(job_id)
        if event.event_type == ILLEGAL_ACTION_FINDING_EVENT
        and event.payload_json["status"] == ILLEGAL_ACTION_STATUS_RESOLVED
    ]
    assert len(resolutions) == 1
    assert await repository.resolve_illegal_action(finding_id, resolution_note="x") is (
        None
    )


@pytest.mark.asyncio
async def test_a_finding_from_another_table_cannot_be_resolved(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    ours = await table(repository)
    theirs = await table(repository)
    finding = await repository.open_illegal_action(
        theirs.id,
        player_id="player2",
        violation=VIOLATION,
        required_undo=REQUIRED_UNDO,
    )
    assert finding is not None
    job_id = await _orchestrating_job_id(repository, ours.id)
    registry = await _orchestrator_registry(
        repository, live_event_bus, skill_registry, ours.id, job_id
    )

    result = await registry.get("resolve_illegal_action").handler(
        {"finding_id": finding.id, "resolution_note": "not mine to close"}
    )

    assert result["is_error"] is True
    reread = await repository.get_illegal_action(finding.id)
    assert reread is not None
    assert reread.status == ILLEGAL_ACTION_STATUS_OPEN


@pytest.mark.asyncio
async def test_the_finding_tools_are_absent_in_chat_mode(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    """A chat session's top-level job is a master job, so mode is the real gate."""
    session = await table(repository, mode=SESSION_MODE_CHAT)
    job_id = await _orchestrating_job_id(repository, session.id)

    registry = await _orchestrator_registry(
        repository,
        live_event_bus,
        skill_registry,
        session.id,
        job_id,
        session_orchestrated=False,
    )

    names = _tool_names(registry)
    assert "report_illegal_action" not in names
    assert "resolve_illegal_action" not in names
    assert "list_my_illegal_actions" not in names


@pytest.mark.asyncio
async def test_a_finding_is_announced_once_live_under_its_durable_id(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    """The live copy must carry the durable row's id, or the row renders twice.

    The SSE stream has two sources for one event: it polls `list_events` for
    durable rows and it also forwards the live bus. The dashboard deduplicates on
    the event id, so a live copy published under an id of its own arrives as a
    second, undeduplicable event (DRA-34). The payloads must match for the same
    reason — a reload must not show less than the live stream did.
    """
    session = await table(repository)
    job_id = await _orchestrating_job_id(repository, session.id)
    registry = await _orchestrator_registry(
        repository, live_event_bus, skill_registry, session.id, job_id
    )

    subscriber = await live_event_bus.subscribe(job_id)
    try:
        await registry.get("report_illegal_action").handler(
            {
                "player_id": "player2",
                "violation": VIOLATION,
                "required_undo": REQUIRED_UNDO,
            }
        )

        stored = [
            event
            for event in await repository.list_events(job_id)
            if event.event_type == ILLEGAL_ACTION_FINDING_EVENT
        ]
        assert len(stored) == 1

        published = await subscriber.get(timeout_seconds=1.0)
        assert published is not None
        assert published.event_type == ILLEGAL_ACTION_FINDING_EVENT
        assert published.durable_event_id == str(stored[0].id)
        assert published.payload_json == stored[0].payload_json
    finally:
        await subscriber.aclose()


@pytest.mark.asyncio
async def test_a_finding_reaches_the_game_timeline_as_judge_evidence(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    """Opening and resolving a finding both emit an `illegal_action` history event.

    This is the producer eval-service's evidence path consumes. Without it the
    judge's finding-as-evidence handling is implemented and never fed, which is
    exactly the shape of a feature that looks present and is not.
    """
    session = await table(repository)
    await repository.update_session(session.id, metadata_json={"game_id": "game-1"})
    job_id = await _orchestrating_job_id(repository, session.id)

    emitted: list[dict] = []

    class _Emitter:
        async def emit_illegal_action(self, **kwargs):
            emitted.append(kwargs)
            return kwargs

    configs = await repository.list_player_configs(session.id)
    registry = build_builtin_registry(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job_id,
        skill_assignments=[],
        job=make_job(),
        player_configs=configs,
        seat_identity=None,
        session_orchestrated=True,
        history_emitter=_Emitter(),
        game_id="game-1",
    )

    opened = _payload(
        await registry.get("report_illegal_action").handler(
            {
                "player_id": "player2",
                "violation": VIOLATION,
                "required_undo": REQUIRED_UNDO,
            }
        )
    )
    await registry.get("resolve_illegal_action").handler(
        {
            "finding_id": opened["finding_id"],
            "resolution_note": "Ricochet is back in hand and the resource is refunded.",
        }
    )

    assert len(emitted) == 2
    assert emitted[0]["game_id"] == "game-1"
    assert emitted[0]["player"] == "player2"
    assert emitted[0]["violation"] == VIOLATION
    assert emitted[0]["required_undo"] == REQUIRED_UNDO
    assert emitted[0]["status"] == ILLEGAL_ACTION_STATUS_OPEN
    assert emitted[1]["status"] == ILLEGAL_ACTION_STATUS_RESOLVED
    assert emitted[1]["resolution_note"]


@pytest.mark.asyncio
async def test_a_finding_is_recorded_without_history_when_no_game_is_attached(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    """No game id means no timeline to write to, and that must not refuse the tool.

    A finding's first job is to reach the seat. History evidence is additional, so
    a session with no game attached still records and still carries the finding.
    """
    session = await table(repository)
    job_id = await _orchestrating_job_id(repository, session.id)

    class _Emitter:
        async def emit_illegal_action(self, **kwargs):  # pragma: no cover
            raise AssertionError("no game is attached, so nothing should be emitted")

    configs = await repository.list_player_configs(session.id)
    registry = build_builtin_registry(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job_id,
        skill_assignments=[],
        job=make_job(),
        player_configs=configs,
        seat_identity=None,
        session_orchestrated=True,
        history_emitter=_Emitter(),
        game_id=None,
    )

    result = await registry.get("report_illegal_action").handler(
        {
            "player_id": "player2",
            "violation": VIOLATION,
            "required_undo": REQUIRED_UNDO,
        }
    )

    assert not result["is_error"]
    assert await repository.list_open_illegal_actions(session.id, "player2")
