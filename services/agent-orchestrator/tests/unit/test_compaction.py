"""Unit tests for CompactionRecord repository and compaction service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "compaction_test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


async def _make_completed_job(
    repo: Repository, session_id: str, prompt: str, output: str
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    assert job is not None
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.mark_job_completed(job.id, output)
    return job.id


@pytest.mark.asyncio
async def test_create_compaction_record(repository: Repository):
    session = await repository.create_session("test", {})
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    job_id = await _make_completed_job(repository, session.id, "turn 1", "response 1")

    record = await repository.create_compaction_record(
        session.id,
        summary_text="Hero HP: 12/15, Villain HP: 30/60",
        covers_up_to_job_id=job_id,
        tokens_used=50,
    )

    assert record.session_id == session.id
    assert record.summary_text == "Hero HP: 12/15, Villain HP: 30/60"
    assert record.covers_up_to_job_id == job_id
    assert record.tokens_used == 50
    assert record.created_at is not None


@pytest.mark.asyncio
async def test_raw_job_events_preserved_after_compaction(repository: Repository):
    session = await repository.create_session("test", {})
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    job_id = await _make_completed_job(repository, session.id, "turn 1", "response 1")

    # Get event count before compaction
    job = await repository.get_job(job_id)
    assert job is not None
    events_before = len(job.events)

    # Create compaction record
    await repository.create_compaction_record(
        session.id,
        summary_text="summary",
        covers_up_to_job_id=job_id,
        tokens_used=10,
    )

    # Raw events should still exist
    job_after = await repository.get_job(job_id)
    assert job_after is not None
    assert len(job_after.events) == events_before


@pytest.mark.asyncio
async def test_get_latest_compaction_record_returns_most_recent(repository: Repository):
    session = await repository.create_session("test", {})
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    job1_id = await _make_completed_job(repository, session.id, "p1", "r1")
    job2_id = await _make_completed_job(repository, session.id, "p2", "r2")

    await repository.create_compaction_record(
        session.id, summary_text="summary1", covers_up_to_job_id=job1_id, tokens_used=10
    )
    record2 = await repository.create_compaction_record(
        session.id, summary_text="summary2", covers_up_to_job_id=job2_id, tokens_used=20
    )

    latest = await repository.get_latest_compaction_record(session.id)
    assert latest is not None
    assert latest.id == record2.id
    assert latest.summary_text == "summary2"


@pytest.mark.asyncio
async def test_count_compaction_records(repository: Repository):
    session = await repository.create_session("test", {})
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    assert await repository.count_compaction_records(session.id) == 0

    job_id = await _make_completed_job(repository, session.id, "p", "r")
    await repository.create_compaction_record(
        session.id, summary_text="s", covers_up_to_job_id=job_id, tokens_used=5
    )
    assert await repository.count_compaction_records(session.id) == 1


@pytest.mark.asyncio
async def test_get_latest_compaction_record_none_when_empty(repository: Repository):
    session = await repository.create_session("test", {})
    result = await repository.get_latest_compaction_record(session.id)
    assert result is None
