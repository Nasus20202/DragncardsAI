from __future__ import annotations

import asyncio
import json

import pytest

from agent_orchestrator.runtime.builtin_tools import (
    build_builtin_registry,
    make_list_player_agents_handler,
    make_prompt_player_agent_handler,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import (
    await_job_event,
    live_event_bus,
    make_job,
    make_skill_assignment,
    repository,
    skill_registry,
)

__all__ = ["live_event_bus", "repository", "skill_registry"]


async def _orchestrator_session(repo: Repository, *, game_id: str | None = None):
    metadata = {"game_id": game_id} if game_id else {}
    session = await repo.create_session("orchestrator", metadata)
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="parent-model",
        gateway_options={"temperature": 0.1},
        provider_options={},
    )
    await repo.add_skill_registry(
        name="parent-skill",
        skill_path="/tmp/parent",
        description=None,
        metadata_json={},
    )
    await repo.add_skill_registry(
        name="seat-skill", skill_path="/tmp/seat", description=None, metadata_json={}
    )
    await repo.enable_skill_for_session(session.id, "parent-skill", True)
    return await repo.get_session(session.id)


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


@pytest.mark.asyncio
async def test_list_player_agents_reports_resolved_configuration(
    repository: Repository,
):
    session = await _orchestrator_session(repository)
    await repository.upsert_player_config(
        session.id,
        "player2",
        display_name="Captain Marvel",
        provider_id=None,
        model_name="seat-model",
        gateway_options={"reasoning": {"effort": "high"}},
        provider_options={},
        skills=["seat-skill"],
    )
    await repository.upsert_player_config(
        session.id,
        "player1",
        display_name=None,
        provider_id=None,
        model_name=None,
        gateway_options={},
        provider_options={},
        skills=None,
    )

    handler = make_list_player_agents_handler(
        repository=repository, session_id=session.id
    )
    result = await handler({})

    assert result["is_error"] is False
    players = _payload(result)["players"]
    assert [p["player_id"] for p in players] == ["player1", "player2"]

    # Seat 1 inherits everything from the orchestrator session.
    assert players[0]["model_name"] == "parent-model"
    assert players[0]["skills"] == ["parent-skill"]
    assert players[0]["reasoning"] is None

    # Seat 2 differs on model, reasoning, and skills.
    assert players[1]["display_name"] == "Captain Marvel"
    assert players[1]["model_name"] == "seat-model"
    assert players[1]["reasoning"] == {"effort": "high"}
    assert players[1]["skills"] == ["seat-skill"]


@pytest.mark.asyncio
async def test_list_player_agents_errors_when_no_roster(repository: Repository):
    session = await _orchestrator_session(repository)

    handler = make_list_player_agents_handler(
        repository=repository, session_id=session.id
    )
    result = await handler({})

    assert result["is_error"] is True
    assert "No player agents are configured" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_prompt_player_agent_configures_the_child_from_the_seat(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await _orchestrator_session(repository, game_id="game-7")
    await repository.upsert_player_config(
        session.id,
        "player2",
        display_name="Captain Marvel",
        provider_id="gemini",
        model_name="seat-model",
        gateway_options={"reasoning": {"effort": "low"}},
        provider_options={"top_k": 5},
        skills=["seat-skill"],
    )
    parent_job = await repository.enqueue_prompt_job(
        session.id, prompt="run the game", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    scheduled: list[str] = []

    async def fake_schedule(child_job_id: str):
        scheduled.append(child_job_id)
        await live_event_bus.publish(
            child_job_id, "completion", {"text": "TURN COMPLETE"}
        )

    handler = make_prompt_player_agent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        schedule_child_fn=fake_schedule,
    )

    result = await handler({"player_id": "player2", "prompt": "Take your turn."})

    assert result["is_error"] is False
    payload = _payload(result)
    assert payload["player_id"] == "player2"
    child_job = await repository.get_job(payload["child_job_id"])
    assert child_job is not None

    child_session = await repository.get_session(child_job.session_id)
    assert child_session is not None
    assert child_session.model_config.provider_id == "gemini"
    assert child_session.model_config.model_name == "seat-model"
    assert child_session.model_config.gateway_options == {
        "temperature": 0.1,
        "reasoning": {"effort": "low"},
    }
    assert child_session.model_config.provider_options == {"top_k": 5}
    assert [s.skill_name for s in child_session.enabled_skills if s.enabled] == [
        "seat-skill"
    ]

    # The seat and the game are stamped on the child so its moves are
    # attributable without inference.
    assert child_session.metadata_json["player_id"] == "player2"
    assert child_session.metadata_json["game_id"] == "game-7"
    assert child_session.metadata_json["orchestrator_session_id"] == session.id

    events = await repository.list_events(parent_job.id)
    started = next(e for e in events if e.event_type == "subagent_started")
    assert started.payload_json["player_id"] == "player2"
    assert started.payload_json["name"] == "Captain Marvel"

    completed = await await_job_event(repository, parent_job.id, "subagent_completed")
    assert completed.payload_json["player_id"] == "player2"
    assert scheduled


@pytest.mark.asyncio
async def test_prompt_player_agent_inherits_when_the_seat_sets_nothing(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await _orchestrator_session(repository)
    await repository.upsert_player_config(
        session.id,
        "player1",
        display_name=None,
        provider_id=None,
        model_name=None,
        gateway_options={},
        provider_options={},
        skills=None,
    )
    parent_job = await repository.enqueue_prompt_job(
        session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    handler = make_prompt_player_agent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        schedule_child_fn=None,
    )

    result = await handler({"player_id": "player1", "prompt": "Take your turn."})

    child_job = await repository.get_job(_payload(result)["child_job_id"])
    child_session = await repository.get_session(child_job.session_id)
    assert child_session.model_config.provider_id == "openai"
    assert child_session.model_config.model_name == "parent-model"
    assert [s.skill_name for s in child_session.enabled_skills if s.enabled] == [
        "parent-skill"
    ]
    assert "game_id" not in child_session.metadata_json


@pytest.mark.asyncio
async def test_child_is_left_unconfigured_when_there_is_nothing_to_inherit(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    # Neither the session nor the seat names a provider/model. The child must be
    # left without a model config so it fails with the normal missing-config
    # error rather than being handed empty provider and model strings.
    session = await repository.create_session("orchestrator", {})
    await repository.upsert_player_config(
        session.id,
        "player1",
        display_name=None,
        provider_id=None,
        model_name=None,
        gateway_options={},
        provider_options={},
        skills=None,
    )
    parent_job = await repository.enqueue_prompt_job(
        session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    handler = make_prompt_player_agent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        schedule_child_fn=None,
    )

    result = await handler({"player_id": "player1", "prompt": "Take your turn."})

    child_job = await repository.get_job(_payload(result)["child_job_id"])
    child_session = await repository.get_session(child_job.session_id)
    assert child_session.model_config is None


@pytest.mark.asyncio
async def test_prompt_player_agent_rejects_unconfigured_seat(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await _orchestrator_session(repository)
    await repository.upsert_player_config(
        session.id,
        "player1",
        display_name=None,
        provider_id=None,
        model_name=None,
        gateway_options={},
        provider_options={},
        skills=None,
    )
    parent_job = await repository.enqueue_prompt_job(
        session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    handler = make_prompt_player_agent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        schedule_child_fn=None,
    )

    result = await handler({"player_id": "player3", "prompt": "Take your turn."})

    assert result["is_error"] is True
    assert "player1" in result["content"][0]["text"]
    events = await repository.list_events(parent_job.id)
    assert not [e for e in events if e.event_type == "subagent_started"]


@pytest.mark.asyncio
async def test_prompt_player_agent_requires_both_arguments(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await _orchestrator_session(repository)
    parent_job = await repository.enqueue_prompt_job(
        session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    handler = make_prompt_player_agent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=parent_job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        schedule_child_fn=None,
    )

    missing_player = await handler({"prompt": "go"})
    missing_prompt = await handler({"player_id": "player1"})

    assert missing_player["is_error"] is True
    assert "player_id is required" in missing_player["content"][0]["text"]
    assert missing_prompt["is_error"] is True
    assert "prompt is required" in missing_prompt["content"][0]["text"]


@pytest.mark.asyncio
async def test_prompt_player_agent_is_master_job_only(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
):
    session = await _orchestrator_session(repository)

    handler = make_prompt_player_agent_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id="job",
        job=make_job(parent_job_id="parent", job_type="prompt"),
        schedule_child_fn=None,
    )

    result = await handler({"player_id": "player1", "prompt": "go"})

    assert result["is_error"] is True
    assert "top-level" in result["content"][0]["text"]


def _tool_names(registry) -> list[str]:
    return [tool.name for tool in registry.list_definitions()]


@pytest.mark.asyncio
async def test_player_tools_are_registered_only_with_a_roster(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    common = dict(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id="session",
        job_id="job",
        skill_assignments=[make_skill_assignment("demo-skill")],
    )

    without_roster = build_builtin_registry(
        **common, job=make_job(parent_job_id=None, job_type="prompt")
    )
    with_roster = build_builtin_registry(
        **common,
        job=make_job(parent_job_id=None, job_type="prompt"),
        player_configs=[object()],
    )
    child_with_roster = build_builtin_registry(
        **common,
        job=make_job(parent_job_id="parent", job_type="prompt"),
        player_configs=[object()],
    )
    compaction_with_roster = build_builtin_registry(
        **common,
        job=make_job(parent_job_id=None, job_type="compaction"),
        player_configs=[object()],
    )

    assert "prompt_player_agent" not in _tool_names(without_roster)
    assert "list_player_agents" not in _tool_names(without_roster)

    assert "prompt_player_agent" in _tool_names(with_roster)
    assert "list_player_agents" in _tool_names(with_roster)
    # The orchestrator still has the generic delegation tools.
    assert "spawn_subagent" in _tool_names(with_roster)
    assert "wait_for_subagent" in _tool_names(with_roster)
    assert "ask_user" in _tool_names(with_roster)

    # A player agent is itself a subagent and must not run the table or spawn.
    for tool_name in (
        "prompt_player_agent",
        "list_player_agents",
        "spawn_subagent",
        "wait_for_subagent",
        "ask_user",
    ):
        assert tool_name not in _tool_names(child_with_roster)
        assert tool_name not in _tool_names(compaction_with_roster)

    # Child-safe tools remain available.
    assert "load_skill" in _tool_names(child_with_roster)
    assert "load_skill_reference" in _tool_names(child_with_roster)
