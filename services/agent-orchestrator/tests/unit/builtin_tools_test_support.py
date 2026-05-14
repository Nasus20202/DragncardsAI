from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


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
    (skill_dir / "SKILL.md").write_text(
        "# Demo Skill\n\nFollow the demo instructions.", encoding="utf-8"
    )
    ref_dir = skill_dir / "reference"
    ref_dir.mkdir()
    (ref_dir / "guide.md").write_text("Guide content.", encoding="utf-8")
    alt_dir = skill_dir / "docs"
    alt_dir.mkdir()
    (alt_dir / "tips.md").write_text("Tip content.", encoding="utf-8")
    return SkillRegistry((root,))


@pytest.fixture
def live_event_bus():
    return InMemoryLiveEventBus()


def make_skill_assignment(skill_name: str):
    return SimpleNamespace(skill_name=skill_name, skill_path="/tmp")


def make_job(parent_job_id=None, job_type="prompt"):
    return SimpleNamespace(parent_job_id=parent_job_id, job_type=job_type)
