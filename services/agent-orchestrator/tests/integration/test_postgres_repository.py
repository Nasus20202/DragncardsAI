from __future__ import annotations

import os
from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

POSTGRES_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5441/agent_orchestrator",
)


def _database_url(database_name: str) -> str:
    return (
        make_url(POSTGRES_URL)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


async def _create_database(database_name: str) -> None:
    admin_engine = create_async_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(
                text(f'CREATE DATABASE "{quote(database_name, safe="_")}"')
            )
    finally:
        await admin_engine.dispose()


async def _drop_database(database_name: str) -> None:
    admin_engine = create_async_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(
                text("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """),
                {"database_name": database_name},
            )
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{quote(database_name, safe="_")}"')
            )
    finally:
        await admin_engine.dispose()


@pytest.fixture
async def postgres_repository():
    database_name = f"agent_orchestrator_test_{uuid4().hex}"
    await _create_database(database_name)

    engine = create_engine(_database_url(database_name))
    await ensure_schema(engine)
    session_factory = create_session_factory(engine)
    repository = Repository(session_factory)

    try:
        yield repository
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_postgres_session_persistence_and_job_ordering(
    postgres_repository: Repository,
):
    session = await postgres_repository.create_session(
        f"session-{uuid4()}", {"purpose": "test"}
    )
    await postgres_repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    job = await postgres_repository.enqueue_prompt_job(
        session.id,
        prompt="play a turn",
        metadata_json={"source": "postgres-test"},
        max_attempts=2,
    )
    assert job is not None

    claimed = await postgres_repository.claim_next_job()
    assert claimed is not None
    await postgres_repository.append_event(
        claimed.id, session.id, "model_output", {"text": "hello"}
    )
    await postgres_repository.mark_job_completed(claimed.id, "done")

    reloaded = await postgres_repository.get_job(job.id)
    assert reloaded is not None
    assert reloaded.status == "completed"
    assert reloaded.result_text == "done"
    events = await postgres_repository.list_events(job.id)
    assert [event.event_type for event in events] == ["progress", "model_output"]


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_postgres_cancellation_state(postgres_repository: Repository):
    session = await postgres_repository.create_session(f"session-{uuid4()}", {})
    await postgres_repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    job = await postgres_repository.enqueue_prompt_job(
        session.id,
        prompt="cancel me",
        metadata_json={},
        max_attempts=1,
    )
    assert job is not None

    cancelled = await postgres_repository.request_cancel(job.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.cancellation_requested_at is not None
    events = await postgres_repository.list_events(job.id)
    assert [event.event_type for event in events] == ["progress", "cancellation"]
