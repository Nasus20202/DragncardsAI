"""Persona resolution and the narrow-never-widen tool rule.

Resolution is pure, so the inheritance rules and the narrowing rule are testable
without a database or a worker.
"""

from __future__ import annotations

from types import SimpleNamespace

from agent_orchestrator.runtime.personas import (
    is_valid_persona_name,
    narrow_tool_definitions,
    persona_allowed_tools_from_snapshot,
    persona_prompt_from_snapshot,
    resolve_persona,
    session_persona_snapshot,
    SESSION_PERSONA_KEY,
)
from agent_orchestrator.runtime.system_prompts import (
    build_subagent_system_prompt,
    build_system_prompt,
)
from agent_orchestrator.runtime.skills import SkillRegistry


def _persona(**overrides):
    fields = {
        "name": "rules-lawyer",
        "display_name": "Rules Lawyer",
        "description": "Checks rule interactions.",
        "system_prompt": "Answer only from the printed rules.",
        "provider_id": None,
        "model_name": None,
        "gateway_options": {},
        "provider_options": {},
        "skills_json": None,
        "allowed_tools_json": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _session(*, provider="openai", model="gpt-4o-mini", gateway=None, skills=()):
    return SimpleNamespace(
        model_config=SimpleNamespace(
            provider_id=provider,
            model_name=model,
            gateway_options=dict(gateway or {}),
            provider_options={"seed": 7},
        ),
        enabled_skills=[
            SimpleNamespace(skill_name=name, enabled=True) for name in skills
        ],
    )


def _tool(exposed_name: str):
    return SimpleNamespace(exposed_name=exposed_name)


def test_persona_name_must_be_a_lowercase_slug():
    assert is_valid_persona_name("rules-lawyer")
    assert is_valid_persona_name("a")
    assert not is_valid_persona_name("Rules-Lawyer")
    assert not is_valid_persona_name("-leading-hyphen")
    assert not is_valid_persona_name("has space")
    assert not is_valid_persona_name("has/slash")
    assert not is_valid_persona_name("")
    assert not is_valid_persona_name("x" * 65)


def test_unset_provider_and_model_inherit_the_session():
    resolved = resolve_persona(_session(), _persona())

    assert resolved.provider_id == "openai"
    assert resolved.model_name == "gpt-4o-mini"


def test_set_provider_and_model_override_the_session():
    resolved = resolve_persona(
        _session(), _persona(provider_id="gemini", model_name="gemini-2.0-flash")
    )

    assert resolved.provider_id == "gemini"
    assert resolved.model_name == "gemini-2.0-flash"


def test_options_are_overlaid_not_replaced():
    resolved = resolve_persona(
        _session(gateway={"temperature": 0.1, "top_p": 0.9}),
        _persona(gateway_options={"temperature": 0.9}),
    )

    # The persona changed one knob without restating the rest.
    assert resolved.gateway_options == {"temperature": 0.9, "top_p": 0.9}
    assert resolved.provider_options == {"seed": 7}


def test_unset_skills_inherit_the_sessions_enabled_skills():
    resolved = resolve_persona(_session(skills=("demo-skill",)), _persona())

    assert resolved.skills == ["demo-skill"]


def test_an_empty_skill_list_means_no_skills():
    resolved = resolve_persona(
        _session(skills=("demo-skill",)), _persona(skills_json=[])
    )

    assert resolved.skills == []


def test_a_set_skill_list_replaces_the_inherited_one():
    resolved = resolve_persona(
        _session(skills=("demo-skill",)), _persona(skills_json=["rules"])
    )

    assert resolved.skills == ["rules"]


def test_snapshot_carries_everything_the_child_needs_and_a_reader_wants():
    resolved = resolve_persona(
        _session(skills=("demo-skill",)),
        _persona(allowed_tools_json=["game_service_next_step"]),
    )

    snapshot = resolved.as_snapshot()

    assert snapshot["name"] == "rules-lawyer"
    assert snapshot["system_prompt"] == "Answer only from the printed rules."
    assert snapshot["skills"] == ["demo-skill"]
    assert snapshot["allowed_tools"] == ["game_service_next_step"]
    assert snapshot["provider_id"] == "openai"
    assert snapshot["model_name"] == "gpt-4o-mini"


def test_snapshot_is_read_off_session_metadata():
    resolved = resolve_persona(_session(), _persona())
    session = SimpleNamespace(
        metadata_json={SESSION_PERSONA_KEY: resolved.as_snapshot()}
    )

    assert session_persona_snapshot(session) == resolved.as_snapshot()
    assert session_persona_snapshot(SimpleNamespace(metadata_json={})) is None
    assert session_persona_snapshot(SimpleNamespace(metadata_json=None)) is None


def test_prompt_and_allowlist_readers_tolerate_a_missing_snapshot():
    assert persona_prompt_from_snapshot(None) is None
    assert persona_prompt_from_snapshot({"system_prompt": "   "}) is None
    assert persona_prompt_from_snapshot({"system_prompt": "be terse"}) == "be terse"
    assert persona_allowed_tools_from_snapshot(None) is None
    assert persona_allowed_tools_from_snapshot({"allowed_tools": None}) is None
    assert persona_allowed_tools_from_snapshot({"allowed_tools": ["a", 3]}) == ["a"]


# --- Narrow, never widen -------------------------------------------------------


def test_an_allowlist_removes_every_tool_it_does_not_name():
    definitions = [_tool("game_service_next_step"), _tool("game_service_draw_card")]

    narrowed = narrow_tool_definitions(definitions, ["game_service_next_step"])

    assert [item.exposed_name for item in narrowed] == ["game_service_next_step"]


def test_an_allowlist_cannot_add_a_tool_the_session_does_not_expose():
    definitions = [_tool("game_service_next_step")]

    narrowed = narrow_tool_definitions(
        definitions, ["game_service_next_step", "delete_everything"]
    )

    assert [item.exposed_name for item in narrowed] == ["game_service_next_step"]


def test_an_empty_allowlist_removes_every_mcp_tool():
    definitions = [_tool("game_service_next_step")]

    assert narrow_tool_definitions(definitions, []) == []


def test_no_allowlist_narrows_nothing():
    definitions = [_tool("game_service_next_step")]

    assert narrow_tool_definitions(definitions, None) is definitions


# --- Prompt assembly ----------------------------------------------------------


def test_persona_prompt_is_its_own_section_of_a_subagent_prompt():
    prompt = build_subagent_system_prompt(
        SkillRegistry(()), [], persona_prompt="Speak only in card names."
    )

    assert "## Persona" in prompt
    assert "Speak only in card names." in prompt
    # The persona is additional instruction, not a replacement for the rules that
    # keep a subagent from delegating further.
    assert "You are running as a subagent." in prompt


def test_a_subagent_without_a_persona_gets_no_persona_section():
    prompt = build_subagent_system_prompt(SkillRegistry(()), [])

    assert "## Persona" not in prompt


def test_master_prompt_lists_the_persona_catalogue_by_name_only():
    prompt = build_system_prompt(
        SkillRegistry(()),
        [],
        personas=[
            _persona(),
            _persona(
                name="deck-builder",
                display_name=None,
                description="Builds decklists.",
                system_prompt="SECRET CHILD INSTRUCTIONS",
            ),
        ],
    )

    assert "## Personas" in prompt
    assert "`rules-lawyer`" in prompt
    assert "Checks rule interactions." in prompt
    assert "`deck-builder`" in prompt
    # A persona's own prompt is the CHILD's instruction and must not cost the
    # parent context.
    assert "SECRET CHILD INSTRUCTIONS" not in prompt


def test_no_personas_means_no_persona_catalogue():
    assert "## Personas" not in build_system_prompt(SkillRegistry(()), [], personas=[])
    assert "## Personas" not in build_system_prompt(SkillRegistry(()), [])
