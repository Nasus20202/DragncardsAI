from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import warnings

import pytest

from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import (
    build_subagent_system_prompt,
    build_system_prompt,
)
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


def test_build_system_prompt_includes_existing_skills_and_skips_missing(tmp_path: Path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    demo_skill = skill_root / "demo"
    demo_skill.mkdir()
    (demo_skill / "SKILL.md").write_text("follow the runbook", encoding="utf-8")
    registry = SkillRegistry((skill_root,))

    prompt = build_system_prompt(
        registry,
        [SimpleNamespace(skill_name="demo"), SimpleNamespace(skill_name="missing")],
    )

    assert "DragnCardsAI" in prompt
    # Summaries (not full content) should appear in the skills section
    assert "follow the runbook" in prompt
    assert "load_skill" in prompt
    assert "load_skill_reference" in prompt
    # missing skill should be silently skipped
    assert "missing" not in prompt


@pytest.mark.asyncio
async def test_sqlite_repository_datetime_round_trip_is_timezone_aware(tmp_path: Path):
    database_path = tmp_path / "storage.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            await ensure_schema(engine)
            repository = Repository(create_session_factory(engine))
            session = await repository.create_session("demo", {})
            terminated = await repository.terminate_session(session.id)

        assert session.created_at.tzinfo is not None
        assert terminated is not None
        assert terminated.terminated_at is not None
        assert terminated.terminated_at.tzinfo is not None
    finally:
        await engine.dispose()


def test_skill_registry_load_markdown_raises_for_missing_skill(tmp_path: Path):
    registry = SkillRegistry((tmp_path,))

    with pytest.raises(FileNotFoundError):
        registry.load_markdown("missing")


def test_build_subagent_system_prompt_allows_large_payload_tools(tmp_path: Path):
    registry = SkillRegistry((tmp_path,))
    prompt = build_subagent_system_prompt(registry, [])

    # Must permit direct large-payload tool calls
    assert "get_game_state" in prompt
    assert "search_cards_marvel_champions" in prompt

    # Must state spawn_subagent is NOT available (not delegate to it)
    assert "You do NOT have `spawn_subagent`" in prompt


def test_build_subagent_system_prompt_states_nesting_blocked(tmp_path: Path):
    registry = SkillRegistry((tmp_path,))
    prompt = build_subagent_system_prompt(registry, [])

    assert "Do not attempt further delegation" in prompt


def test_build_subagent_system_prompt_includes_skills(tmp_path: Path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    sub_skill = skill_root / "sub-demo"
    sub_skill.mkdir()
    (sub_skill / "SKILL.md").write_text("subagent runbook content", encoding="utf-8")
    registry = SkillRegistry((skill_root,))

    prompt = build_subagent_system_prompt(
        registry,
        [SimpleNamespace(skill_name="sub-demo"), SimpleNamespace(skill_name="missing")],
    )

    assert "subagent runbook content" in prompt
    assert "load_skill" in prompt
    assert "missing" not in prompt


def test_top_level_prompt_contains_spawn_subagent_section(tmp_path: Path):
    registry = SkillRegistry((tmp_path,))
    prompt = build_system_prompt(registry, [])

    assert "spawn_subagent" in prompt
    assert "wait_for_subagent" in prompt
