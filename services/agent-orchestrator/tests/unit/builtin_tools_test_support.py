from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    """A per-test database that tolerates the detached child monitors.

    Deliberately file-backed rather than ``:memory:``. SQLAlchemy serves a
    memory SQLite URL from a StaticPool — one connection shared by every session
    — and these tests spawn detached `monitor-child-*` tasks that keep querying
    the repository after the call that started them returns. Two sessions
    interleaving on one connection means one task's transaction boundary can
    discard another's uncommitted INSERT, which surfaced as a rare
    `create_session` returning a row it had just written as `None`. A file gives
    each session its own connection and lets SQLite's own locking order the
    writers, so the race cannot express itself.
    """
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'orchestrator.db'}")
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


async def await_job_event(repository, job_id: str, event_type: str):
    """Wait for a detached child monitor to record ``event_type``.

    The monitor consults the database before it trusts the event stream, so how
    long it takes depends on database latency. Polling for the event keeps these
    tests deterministic instead of racing a fixed sleep.
    """
    for _ in range(500):
        events = await repository.list_events(job_id)
        match = [event for event in events if event.event_type == event_type]
        if match:
            return match[0]
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} never recorded a {event_type} event")
