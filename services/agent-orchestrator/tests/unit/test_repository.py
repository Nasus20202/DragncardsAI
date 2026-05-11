from __future__ import annotations

from pathlib import Path

import pytest

from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "repository.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


async def _create_session_with_model(repo: Repository, name: str = "demo"):
    session = await repo.create_session(name, {"scope": name})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    return session


@pytest.mark.asyncio
async def test_session_repository_handles_missing_records(repository: Repository):
    assert await repository.update_session("missing", name="x") is None
    assert await repository.terminate_session("missing") is None
    assert (
        await repository.set_model_config(
            "missing",
            provider_id="openai",
            model_name="gpt-4o-mini",
            gateway_options={},
            provider_options={},
        )
        is None
    )
    assert await repository.add_skill_assignment("missing", "demo", "/tmp/demo") is None
    assert (
        await repository.add_mcp_assignment(
            "missing",
            name="game-service",
            transport="streamable-http",
            server_url="http://game-service/mcp/",
            headers_json={},
        )
        is None
    )
    assert await repository.get_skill_assignment("missing") is None
    assert await repository.get_mcp_assignment("missing") is None


@pytest.mark.asyncio
async def test_session_repository_updates_existing_assignments_and_filters(
    repository: Repository,
):
    active_session = await _create_session_with_model(repository, "active")
    terminated_session = await _create_session_with_model(repository, "terminated")
    await repository.terminate_session(terminated_session.id)

    first_skill = await repository.add_skill_assignment(
        active_session.id, "demo", "/tmp/first"
    )
    second_skill = await repository.add_skill_assignment(
        active_session.id, "demo", "/tmp/second"
    )
    assert first_skill is not None
    assert second_skill is not None
    assert second_skill.id == first_skill.id
    assert second_skill.skill_path == "/tmp/second"
    assert await repository.remove_skill_assignment(active_session.id, "demo") is True
    assert await repository.remove_skill_assignment(active_session.id, "demo") is False

    first_mcp = await repository.add_mcp_assignment(
        active_session.id,
        name="game-service",
        transport="streamable-http",
        server_url="http://game-service/mcp/",
        headers_json={},
    )
    second_mcp = await repository.add_mcp_assignment(
        active_session.id,
        name="game-service",
        transport="sse",
        server_url="http://game-service/sse",
        headers_json={"Authorization": "Bearer token"},
    )
    assert first_mcp is not None
    assert second_mcp is not None
    assert second_mcp.id == first_mcp.id
    assert second_mcp.transport == "sse"
    assert second_mcp.server_url == "http://game-service/sse"
    assert second_mcp.headers_json == {"Authorization": "Bearer token"}
    assert (
        await repository.remove_mcp_assignment(active_session.id, "game-service")
        is True
    )
    assert (
        await repository.remove_mcp_assignment(active_session.id, "game-service")
        is False
    )

    sessions, total = await repository.list_sessions(
        status="terminated", limit=10, offset=0
    )
    assert total == 1
    assert [item.id for item in sessions] == [terminated_session.id]


@pytest.mark.asyncio
async def test_job_repository_claims_oldest_and_filters_results(repository: Repository):
    session = await _create_session_with_model(repository)
    first_job = await repository.enqueue_prompt_job(
        session.id, prompt="first", metadata_json={}, max_attempts=1
    )
    second_job = await repository.enqueue_prompt_job(
        session.id, prompt="second", metadata_json={}, max_attempts=1
    )

    claimed = await repository.claim_next_job()
    assert claimed is not None
    assert claimed.id == first_job.id

    await repository.append_event(
        first_job.id, session.id, "model_output", {"text": "hello"}
    )
    await repository.mark_job_completed(first_job.id, "done")

    second_claimed = await repository.claim_next_job()
    assert second_claimed is not None
    assert second_claimed.id == second_job.id
    await repository.mark_job_failed(
        second_job.id,
        error_code="execution_error",
        error_message="boom",
        retryable=False,
    )

    completed_jobs, completed_total = await repository.list_session_jobs(
        session.id,
        status="completed",
        limit=10,
        offset=0,
    )
    failed_jobs, failed_total = await repository.list_session_jobs(
        session.id,
        status="failed",
        limit=10,
        offset=0,
    )
    event_slice = await repository.list_events(first_job.id, after_id=1, limit=1)

    assert completed_total == 1
    assert completed_jobs[0].id == first_job.id
    assert failed_total == 1
    assert failed_jobs[0].id == second_job.id
    assert len(event_slice) == 1
    assert event_slice[0].event_type == "model_output"


@pytest.mark.asyncio
async def test_job_repository_cancel_and_failure_branches(repository: Repository):
    session = await _create_session_with_model(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="cancel later", metadata_json={}, max_attempts=2
    )
    claimed = await repository.claim_next_job()

    cancelled = await repository.request_cancel(job.id)
    assert cancelled is not None
    assert cancelled.status == "running"
    assert cancelled.cancellation_requested_at is not None
    assert await repository.get_job_cancellation_requested(job.id) is True
    assert await repository.get_job_cancellation_requested("missing") is False

    failed = await repository.mark_job_failed(
        job.id,
        error_code="gateway_error",
        error_message="do not retry",
        retryable=True,
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.completed_at is not None
    assert failed.prompt_run.status == "failed"
    assert failed.attempts_log[0].status == "failed"
    assert failed.attempts_log[0].error_message == "do not retry"

    assert await repository.request_cancel("missing") is None
    assert await repository.mark_job_completed("missing", "done") is None
    assert await repository.mark_job_cancelled("missing", reason="missing") is None


@pytest.mark.asyncio
async def test_enqueue_prompt_job_rejects_terminated_sessions(repository: Repository):
    session = await repository.create_session("demo", {})
    await repository.terminate_session(session.id)

    with pytest.raises(ValueError):
        await repository.enqueue_prompt_job(
            session.id, prompt="hello", metadata_json={}, max_attempts=1
        )

    assert await repository.claim_next_job() is None


@pytest.mark.asyncio
async def test_session_multi_turn_memory_defaults_true(repository: Repository):
    session = await repository.create_session("demo", {})
    assert session.multi_turn_memory is True


@pytest.mark.asyncio
async def test_session_multi_turn_memory_can_be_disabled(repository: Repository):
    session = await repository.create_session("demo", {}, multi_turn_memory=False)
    assert session.multi_turn_memory is False


@pytest.mark.asyncio
async def test_update_multi_turn_memory(repository: Repository):
    session = await repository.create_session("demo", {})
    assert session.multi_turn_memory is True
    updated = await repository.update_multi_turn_memory(
        session.id, multi_turn_memory=False
    )
    assert updated is not None
    assert updated.multi_turn_memory is False


@pytest.mark.asyncio
async def test_update_multi_turn_memory_missing_session(repository: Repository):
    result = await repository.update_multi_turn_memory(
        "missing", multi_turn_memory=False
    )
    assert result is None
