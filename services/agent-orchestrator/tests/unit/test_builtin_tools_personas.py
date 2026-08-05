"""Starting a subagent from a persona.

The property these tests exist for is CAPTURE: a persona is read once, at the
moment the child is started, and materialised onto the child. Editing or deleting
the persona afterwards must be invisible to that child, because a subagent that
silently changes behaviour mid-game is worse than one that is wrong from the
start.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlalchemy import func, select

from agent_orchestrator.runtime.builtin_tools import make_spawn_subagent_handler
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.personas import SESSION_PERSONA_KEY
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.models import AgentSession
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import (
    live_event_bus,  # noqa: F401
    make_job,
    repository,  # noqa: F401
)


@pytest.fixture
def skill_roots(tmp_path: Path) -> Path:
    """A skill root holding `demo-skill` and `retired-skill`."""
    root = tmp_path / "skills"
    root.mkdir()
    for name in ("demo-skill", "retired-skill"):
        skill_dir = root / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"# {name}", encoding="utf-8")
    return root


async def _parent(repository: Repository, **session_kwargs):
    session = await repository.create_session("parent", {}, **session_kwargs)
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="parent-model",
        gateway_options={"top_p": 0.9},
        provider_options={},
    )
    await repository.add_skill_registry(
        name="parent-skill",
        skill_path="/tmp/parent-skill",
        description=None,
        metadata_json={},
    )
    await repository.enable_skill_for_session(session.id, "parent-skill", True)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert job is not None
    return session, job


async def _write_persona(repository: Repository, name: str, **overrides):
    fields = {
        "display_name": None,
        "description": None,
        "system_prompt": "Answer only from the printed rules.",
        "provider_id": None,
        "model_name": None,
        "gateway_options": {},
        "provider_options": {},
        "skills": None,
        "allowed_tools": None,
    }
    fields.update(overrides)
    return await repository.upsert_persona(name, **fields)


async def _allow(repository: Repository, session, *names: str) -> None:
    """Put the named personas on the session's subagent allowlist.

    Every spawn that names a persona needs this now. An empty allowlist means NO
    persona may be spawned — never "all of them" — so a session that has not opted
    a persona in refuses it, which is what
    `test_a_persona_off_the_allowlist_is_refused` asserts directly.
    """
    for name in names:
        assert await repository.set_subagent_allowed(session.id, name, True) is not None


def _handler(repository, bus, session, job, skill_roots, schedule=None):
    return make_spawn_subagent_handler(
        repository=repository,
        live_event_bus=bus,
        session_id=session.id,
        job_id=job.id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        skill_registry=SkillRegistry((skill_roots,)),
        schedule_child_fn=schedule,
    )


async def _session_count(repository: Repository) -> int:
    """Every session row, including child sessions.

    ``list_sessions`` deliberately hides subagent-child sessions, so it cannot
    prove that a failed spawn created none.
    """
    async with repository._session_factory() as session:
        return int(
            await session.scalar(select(func.count()).select_from(AgentSession)) or 0
        )


async def _child_session_of(repository: Repository, parent_job_id: str):
    events = await repository.list_events(parent_job_id)
    started = next(e for e in events if e.event_type == "subagent_started")
    child = await repository.get_session(started.payload_json["child_session_id"])
    assert child is not None
    return child, started


@pytest.mark.asyncio
async def test_named_persona_configures_the_child(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    session, job = await _parent(repository)
    await repository.add_skill_registry(
        name="demo-skill",
        skill_path=str(skill_roots / "demo-skill"),
        description=None,
        metadata_json={},
    )
    await _write_persona(
        repository,
        "rules-lawyer",
        model_name="persona-model",
        gateway_options={"temperature": 0.1},
        skills=["demo-skill"],
        allowed_tools=["game_service_next_step"],
    )
    await _allow(repository, session, "rules-lawyer")

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "check a rule", "persona": "rules-lawyer"}
    )
    assert result["is_error"] is False
    assert "rules-lawyer" in result["content"][0]["text"]

    child, started = await _child_session_of(repository, job.id)
    assert started.payload_json["persona"] == "rules-lawyer"

    # Provider inherited, model overridden, options overlaid.
    assert child.model_config is not None
    assert child.model_config.provider_id == "openai"
    assert child.model_config.model_name == "persona-model"
    assert child.model_config.gateway_options == {"top_p": 0.9, "temperature": 0.1}

    # The persona's skills replaced the parent's.
    assert sorted(item.skill_name for item in child.enabled_skills) == ["demo-skill"]

    snapshot = (child.metadata_json or {})[SESSION_PERSONA_KEY]
    assert snapshot["name"] == "rules-lawyer"
    assert snapshot["system_prompt"] == "Answer only from the printed rules."
    assert snapshot["skills"] == ["demo-skill"]
    assert snapshot["allowed_tools"] == ["game_service_next_step"]


@pytest.mark.asyncio
async def test_no_persona_leaves_the_old_inheritance_behaviour_intact(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    session, job = await _parent(repository)

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "just do it"}
    )
    assert result["is_error"] is False

    child, started = await _child_session_of(repository, job.id)
    assert "persona" not in started.payload_json
    assert SESSION_PERSONA_KEY not in (child.metadata_json or {})
    assert child.model_config is not None
    assert child.model_config.model_name == "parent-model"
    assert [item.skill_name for item in child.enabled_skills] == ["parent-skill"]


@pytest.mark.asyncio
async def test_session_default_persona_applies_when_none_is_named(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    await _write_persona(repository, "house-style", model_name="default-model")
    session, job = await _parent(repository, default_subagent_persona="house-style")
    await _allow(repository, session, "house-style")

    await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go"}
    )

    child, started = await _child_session_of(repository, job.id)
    assert started.payload_json["persona"] == "house-style"
    assert child.model_config is not None
    assert child.model_config.model_name == "default-model"


@pytest.mark.asyncio
async def test_a_named_persona_beats_the_session_default(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    await _write_persona(repository, "house-style", model_name="default-model")
    await _write_persona(repository, "rules-lawyer", model_name="named-model")
    session, job = await _parent(repository, default_subagent_persona="house-style")
    await _allow(repository, session, "house-style", "rules-lawyer")

    await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "rules-lawyer"}
    )

    child, started = await _child_session_of(repository, job.id)
    assert started.payload_json["persona"] == "rules-lawyer"
    assert child.model_config is not None
    assert child.model_config.model_name == "named-model"


@pytest.mark.asyncio
async def test_an_unknown_persona_fails_the_spawn_and_creates_nothing(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    await _write_persona(repository, "rules-lawyer")
    session, job = await _parent(repository)
    await _allow(repository, session, "rules-lawyer")

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "no-such-persona"}
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "no-such-persona" in text
    assert "rules-lawyer" in text

    events = await repository.list_events(job.id)
    assert [e for e in events if e.event_type == "subagent_started"] == []
    assert await _session_count(repository) == 1


@pytest.mark.asyncio
async def test_a_persona_off_the_allowlist_is_refused(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    """The allowlist is enforcement, not a picker filter.

    This is the test the server-side refusal exists for. Nothing here goes through
    the dashboard: a caller drives `spawn_subagent` directly with a persona the
    session does not allow, exactly as a model or a scripted HTTP client would, and
    the spawn is refused before any child row is written. Without the check in
    `_resolve_spawn_persona` this test fails on `is_error`, on the message, and on
    the session count — the child gets created and runs as the persona.
    """
    await _write_persona(repository, "rules-lawyer", model_name="persona-model")
    await _write_persona(repository, "house-style", model_name="other-model")
    session, job = await _parent(repository)
    await _allow(repository, session, "house-style")

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "rules-lawyer"}
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "rules-lawyer" in text
    # The refusal names what IS permitted, so the model can correct itself.
    assert "house-style" in text

    events = await repository.list_events(job.id)
    assert [e for e in events if e.event_type == "subagent_started"] == []
    assert await _session_count(repository) == 1


@pytest.mark.asyncio
async def test_an_empty_allowlist_permits_no_persona_at_all(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    """Empty means none. It is never read as "every persona"."""
    await _write_persona(repository, "rules-lawyer")
    session, job = await _parent(repository)

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "rules-lawyer"}
    )

    assert result["is_error"] is True
    assert "does not permit" in result["content"][0]["text"]
    assert await _session_count(repository) == 1


@pytest.mark.asyncio
async def test_a_disallowed_session_default_is_refused_too(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    """A configuration field must not be a way around the allowlist.

    The default is what a bare `spawn_subagent` becomes, so if the guard only
    covered the argument the model types, revoking a persona would leave every
    plain spawn still running as it.
    """
    await _write_persona(repository, "house-style", model_name="default-model")
    session, job = await _parent(repository, default_subagent_persona="house-style")

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go"}
    )

    assert result["is_error"] is True
    assert "house-style" in result["content"][0]["text"]
    assert await _session_count(repository) == 1


@pytest.mark.asyncio
async def test_an_allowance_switched_off_stops_permitting_the_persona(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    """`enabled` is a soft toggle, so every consumer has to read the flag.

    A row left behind with `enabled=False` must not keep permitting the persona;
    that is the same trap `enabled_skill_assignments` exists to close for skills.
    """
    await _write_persona(repository, "rules-lawyer")
    session, job = await _parent(repository)
    await _allow(repository, session, "rules-lawyer")
    await repository.set_subagent_allowed(session.id, "rules-lawyer", False)

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "rules-lawyer"}
    )

    assert result["is_error"] is True
    assert await _session_count(repository) == 1


@pytest.mark.asyncio
async def test_a_persona_naming_a_vanished_skill_fails_the_spawn(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    """The catalogue mirrors the filesystem, so a skill can disappear after the
    persona was written. Failing loudly beats silently dropping it."""
    session, job = await _parent(repository)
    await repository.add_skill_registry(
        name="retired-skill",
        skill_path=str(skill_roots / "retired-skill"),
        description=None,
        metadata_json={},
    )
    await _write_persona(repository, "nostalgic", skills=["retired-skill"])
    await _allow(repository, session, "nostalgic")

    # The skill is removed from disk after the persona was written and accepted.
    for path in sorted((skill_roots / "retired-skill").iterdir()):
        path.unlink()
    (skill_roots / "retired-skill").rmdir()

    result = await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "nostalgic"}
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "nostalgic" in text
    assert "retired-skill" in text

    events = await repository.list_events(job.id)
    assert [e for e in events if e.event_type == "subagent_started"] == []
    assert await _session_count(repository) == 1


@pytest.mark.asyncio
async def test_editing_a_persona_does_not_change_an_already_started_child(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    session, job = await _parent(repository)
    await repository.add_skill_registry(
        name="demo-skill",
        skill_path=str(skill_roots / "demo-skill"),
        description=None,
        metadata_json={},
    )
    await _write_persona(
        repository,
        "rules-lawyer",
        system_prompt="original instructions",
        model_name="original-model",
        skills=["demo-skill"],
        allowed_tools=["game_service_next_step"],
    )
    await _allow(repository, session, "rules-lawyer")

    await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "rules-lawyer"}
    )
    child_before, _ = await _child_session_of(repository, job.id)

    # Everything about the persona changes after the child was started.
    await _write_persona(
        repository,
        "rules-lawyer",
        system_prompt="completely different instructions",
        model_name="different-model",
        skills=[],
        allowed_tools=[],
    )

    child_after = await repository.get_session(child_before.id)
    assert child_after is not None
    snapshot = (child_after.metadata_json or {})[SESSION_PERSONA_KEY]
    assert snapshot["system_prompt"] == "original instructions"
    assert snapshot["skills"] == ["demo-skill"]
    assert snapshot["allowed_tools"] == ["game_service_next_step"]
    assert child_after.model_config is not None
    assert child_after.model_config.model_name == "original-model"
    assert [item.skill_name for item in child_after.enabled_skills] == ["demo-skill"]


@pytest.mark.asyncio
async def test_deleting_a_persona_does_not_change_a_queued_child(
    repository: Repository, live_event_bus: InMemoryLiveEventBus, skill_roots: Path
):
    session, job = await _parent(repository)
    await _write_persona(
        repository,
        "rules-lawyer",
        system_prompt="captured",
        model_name="captured-model",
    )
    await _allow(repository, session, "rules-lawyer")

    await _handler(repository, live_event_bus, session, job, skill_roots)(
        {"prompt": "go", "persona": "rules-lawyer"}
    )
    child_before, _ = await _child_session_of(repository, job.id)
    child_jobs, _ = await repository.list_session_jobs(child_before.id)
    assert [item.status for item in child_jobs] == ["queued"]

    assert await repository.delete_persona("rules-lawyer") is True

    child_after = await repository.get_session(child_before.id)
    assert child_after is not None
    snapshot = (child_after.metadata_json or {})[SESSION_PERSONA_KEY]
    # The record of what this child runs — and what it ran with, for a reader of
    # a finished game — survives the persona it came from.
    assert snapshot["name"] == "rules-lawyer"
    assert snapshot["system_prompt"] == "captured"
    assert child_after.model_config is not None
    assert child_after.model_config.model_name == "captured-model"
