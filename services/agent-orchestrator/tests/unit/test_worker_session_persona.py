"""What a persona does to the session's OWN agent, and what the allowlist tells it.

The subagent case is covered in `test_worker_personas.py`. This file is the
top-level job: a chat session that has adopted a persona of its own, and the
persona catalogue that same job is told about.

Two properties are asserted against a real prompt run rather than in isolation:

* A session persona contributes its instructions and its tool allowlist, and
  **nothing else** — not the provider, not the model, not the skills. Those have
  their own controls on the same session, and a persona overwriting them would
  make those controls misreport what the agent runs with.
* The catalogue a master job is shown lists the session's ALLOWLIST, never the
  deployment's whole persona table, so the model is not invited to name something
  the spawn guard would refuse.
"""

from __future__ import annotations

import pytest

from agent_orchestrator.integrations.bifrost import ChatResponse
from agent_orchestrator.runtime.personas import SESSION_PERSONA_KEY
from agent_orchestrator.storage.repository import Repository

from .test_worker_personas import EXPOSED_TOOL_NAME, RecordingBifrost, _tool_names
from .worker_test_support import (  # noqa: F401
    FakeBifrost,
    FakeMcp,
    make_worker,
    prepare_session,
    repository,
    skill_registry,
)


def _snapshot(**overrides) -> dict:
    """A session-level persona snapshot, as the API writes it.

    Narrower than a spawned child's: only the two fields a session applies are
    recorded, so nothing here can suggest that a provider or a skill list was
    captured and then quietly ignored.
    """
    snapshot = {
        "name": "table-talk",
        "display_name": "Table Talk",
        "system_prompt": "Narrate every decision as a play-by-play commentator.",
        "allowed_tools": None,
    }
    snapshot.update(overrides)
    return snapshot


async def _write_persona(repository: Repository, name: str, **overrides):
    fields = {
        "display_name": None,
        "description": None,
        "system_prompt": f"{name} instructions.",
        "provider_id": None,
        "model_name": None,
        "gateway_options": {},
        "provider_options": {},
        "skills": None,
        "allowed_tools": None,
    }
    fields.update(overrides)
    return await repository.upsert_persona(name, **fields)


async def _master_job(repository: Repository, *, persona_snapshot=None):
    """A claimed top-level job whose session optionally carries a persona."""
    session = await prepare_session(repository)
    if persona_snapshot is not None:
        await repository.update_session(
            session.id,
            session_persona=persona_snapshot["name"],
            metadata_json={SESSION_PERSONA_KEY: persona_snapshot},
        )
    job = await repository.enqueue_prompt_job(
        session.id, prompt="play the turn", metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repository.claim_next_job()
    assert claimed is not None
    return session, claimed


def _system_prompt(bifrost: RecordingBifrost) -> str:
    return bifrost.messages[0][0]["content"]


@pytest.mark.asyncio
async def test_a_session_persona_reaches_the_sessions_own_system_prompt(
    repository: Repository, skill_registry
):
    bifrost = RecordingBifrost(
        responses=[ChatResponse(content="ok", tool_calls=[], raw={})]
    )
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=FakeMcp(),
    )
    _, job = await _master_job(repository, persona_snapshot=_snapshot())

    await worker._run_job(job)

    prompt = _system_prompt(bifrost)
    assert "## Persona" in prompt
    assert "Narrate every decision as a play-by-play commentator." in prompt
    # The base rules are still there and still come first: a persona adds
    # instruction, it does not replace the constraints.
    assert prompt.index("## Persona") > 0


@pytest.mark.asyncio
async def test_a_session_without_a_persona_gets_no_persona_section(
    repository: Repository, skill_registry
):
    bifrost = RecordingBifrost(
        responses=[ChatResponse(content="ok", tool_calls=[], raw={})]
    )
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=FakeMcp(),
    )
    _, job = await _master_job(repository)

    await worker._run_job(job)

    assert "## Persona" not in _system_prompt(bifrost)


@pytest.mark.asyncio
async def test_a_session_personas_tool_allowlist_narrows_the_sessions_tools(
    repository: Repository, skill_registry
):
    bifrost = FakeBifrost(responses=[ChatResponse(content="ok", tool_calls=[], raw={})])
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=FakeMcp(),
    )
    _, job = await _master_job(
        repository, persona_snapshot=_snapshot(allowed_tools=["something_else"])
    )

    await worker._run_job(job)

    names = _tool_names(bifrost)
    assert EXPOSED_TOOL_NAME not in names
    # An allowlist naming a tool the session does not expose adds nothing: this is
    # a filter over what is already there, never a way to reach further.
    assert "something_else" not in names


@pytest.mark.asyncio
async def test_a_session_persona_does_not_touch_the_sessions_model(
    repository: Repository, skill_registry
):
    """The session's own provider/model win, because they are separately visible.

    A subagent materialises its persona's provider and model because nothing else
    on that child says what to run. A session has explicit pickers for both, so a
    persona silently overriding them would make the pickers lie.
    """
    bifrost = FakeBifrost(responses=[ChatResponse(content="ok", tool_calls=[], raw={})])
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=FakeMcp(),
    )
    _, job = await _master_job(repository, persona_snapshot=_snapshot())

    await worker._run_job(job)

    assert bifrost.calls[0]["model_name"] == "gpt-4o-mini"
    assert bifrost.calls[0]["provider_id"] == "openai"


@pytest.mark.asyncio
async def test_the_persona_catalogue_lists_only_the_sessions_allowlist(
    repository: Repository, skill_registry
):
    bifrost = RecordingBifrost(
        responses=[ChatResponse(content="ok", tool_calls=[], raw={})]
    )
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=FakeMcp(),
    )
    await _write_persona(repository, "scout", description="Reads the board.")
    await _write_persona(repository, "rules-lawyer", description="Reads the rules.")
    session, job = await _master_job(repository)
    await repository.set_subagent_allowed(session.id, "scout", True)

    await worker._run_job(job)

    prompt = _system_prompt(bifrost)
    assert "`scout`" in prompt
    assert "`rules-lawyer`" not in prompt


@pytest.mark.asyncio
async def test_an_empty_allowlist_offers_no_persona_catalogue_at_all(
    repository: Repository, skill_registry
):
    bifrost = RecordingBifrost(
        responses=[ChatResponse(content="ok", tool_calls=[], raw={})]
    )
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=bifrost,
        mcp_client=FakeMcp(),
    )
    await _write_persona(repository, "scout", description="Reads the board.")
    _, job = await _master_job(repository)

    await worker._run_job(job)

    prompt = _system_prompt(bifrost)
    assert "## Personas" not in prompt
    assert "`scout`" not in prompt
