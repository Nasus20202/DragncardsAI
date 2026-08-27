"""A player seat is a durable agent in orchestrated mode, and only there.

The two cases that matter most are symmetrical: an orchestrated seat must reuse
its session (or it has no memory), and a chat session must not (or every existing
subagent silently becomes permanent).
"""

from __future__ import annotations

import json

import pytest

from agent_orchestrator.runtime.builtin_tools import make_prompt_player_agent_handler
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.personas import SESSION_PERSONA_KEY
from agent_orchestrator.runtime.platforms import PLATFORM_MARVEL_LCG
from agent_orchestrator.runtime.player_agents import session_player_id
from agent_orchestrator.runtime.session_modes import SESSION_MODE_ORCHESTRATED
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import live_event_bus, make_job, repository

__all__ = ["live_event_bus", "repository"]


async def _table(
    repo: Repository,
    *,
    mode: str = SESSION_MODE_ORCHESTRATED,
    persona: str | None = None,
    platform: str | None = None,
):
    """An orchestrating session with one configured seat."""
    session = await repo.create_session(
        "table",
        {"platform": platform} if platform is not None else {},
        session_mode=mode,
    )
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="parent-model",
        gateway_options={},
        provider_options={},
    )
    await repo.upsert_player_config(
        session.id,
        "player1",
        display_name="Spider-Man",
        provider_id="openai",
        model_name="seat-model",
        gateway_options={},
        provider_options={},
        skills=[],
        persona=persona,
    )
    return await repo.get_session(session.id)


def _handler(repo: Repository, bus: InMemoryLiveEventBus, session_id: str):
    scheduled: list[str] = []

    async def schedule(child_job_id: str) -> None:
        scheduled.append(child_job_id)

    return (
        make_prompt_player_agent_handler(
            repo,
            bus,
            session_id,
            "orchestrating-job",
            make_job(),
            schedule_child_fn=schedule,
        ),
        scheduled,
    )


def _child_job_id(result: dict) -> str:
    return json.loads(result["content"][0]["text"])["child_job_id"]


@pytest.mark.asyncio
async def test_first_prompt_creates_and_records_the_seats_session(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session = await _table(repository)
    handle, _ = _handler(repository, live_event_bus, session.id)

    result = await handle({"player_id": "player1", "prompt": "take your turn"})

    child_job = await repository.get_job(_child_job_id(result))
    assert child_job is not None
    assert child_job.parent_job_id == "orchestrating-job"
    seat = await repository.get_player_config(session.id, "player1")
    assert seat is not None
    assert seat.agent_session_id == child_job.session_id

    child_session = await repository.get_session(child_job.session_id)
    assert child_session is not None
    assert child_session.multi_turn_memory is True
    assert session_player_id(child_session) == "player1"


@pytest.mark.asyncio
async def test_later_prompt_reuses_the_seats_session(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session = await _table(repository)
    handle, _ = _handler(repository, live_event_bus, session.id)

    first = await handle({"player_id": "player1", "prompt": "round one"})
    second = await handle({"player_id": "player1", "prompt": "round two"})

    first_job = await repository.get_job(_child_job_id(first))
    second_job = await repository.get_job(_child_job_id(second))
    assert first_job is not None and second_job is not None
    assert first_job.id != second_job.id
    assert first_job.session_id == second_job.session_id
    assert first_job.parent_job_id == "orchestrating-job"
    assert second_job.parent_job_id == "orchestrating-job"


@pytest.mark.asyncio
async def test_a_marvel_lcg_platform_is_inherited_by_the_seat_session(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session = await _table(repository, platform=PLATFORM_MARVEL_LCG)
    handle, _ = _handler(repository, live_event_bus, session.id)

    result = await handle({"player_id": "player1", "prompt": "take your turn"})

    child_job = await repository.get_job(_child_job_id(result))
    assert child_job is not None
    child_session = await repository.get_session(child_job.session_id)
    assert child_session is not None
    assert (child_session.metadata_json or {}).get("platform") == PLATFORM_MARVEL_LCG


@pytest.mark.asyncio
async def test_a_chat_session_still_spawns_a_memoryless_child(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session = await _table(repository, mode="chat")
    handle, _ = _handler(repository, live_event_bus, session.id)

    first = await handle({"player_id": "player1", "prompt": "round one"})
    second = await handle({"player_id": "player1", "prompt": "round two"})

    first_job = await repository.get_job(_child_job_id(first))
    second_job = await repository.get_job(_child_job_id(second))
    assert first_job is not None and second_job is not None
    assert first_job.session_id != second_job.session_id

    child_session = await repository.get_session(first_job.session_id)
    assert child_session is not None
    assert child_session.multi_turn_memory is False
    seat = await repository.get_player_config(session.id, "player1")
    assert seat is not None
    assert seat.agent_session_id is None


@pytest.mark.asyncio
async def test_the_seats_persona_is_snapshotted_once(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    await repository.upsert_persona(
        name="rookie",
        display_name="Aggressive Rookie",
        description="Attacks first.",
        system_prompt="Attack whenever you can.",
        provider_id=None,
        model_name=None,
        gateway_options={},
        provider_options={},
        skills=None,
        allowed_tools=None,
    )
    session = await _table(repository, persona="rookie")
    handle, _ = _handler(repository, live_event_bus, session.id)

    await handle({"player_id": "player1", "prompt": "round one"})

    seat = await repository.get_player_config(session.id, "player1")
    assert seat is not None and seat.agent_session_id is not None
    child_session = await repository.get_session(seat.agent_session_id)
    assert child_session is not None
    snapshot = (child_session.metadata_json or {})[SESSION_PERSONA_KEY]
    assert snapshot["name"] == "rookie"
    assert snapshot["system_prompt"] == "Attack whenever you can."

    # Editing the persona afterwards must not reach the seat that is already playing.
    await repository.upsert_persona(
        name="rookie",
        display_name="Aggressive Rookie",
        description="Attacks first.",
        system_prompt="Completely different instructions.",
        provider_id=None,
        model_name=None,
        gateway_options={},
        provider_options={},
        skills=None,
        allowed_tools=None,
    )
    await handle({"player_id": "player1", "prompt": "round two"})
    reread = await repository.get_session(seat.agent_session_id)
    assert reread is not None
    assert (reread.metadata_json or {})[SESSION_PERSONA_KEY]["system_prompt"] == (
        "Attack whenever you can."
    )
