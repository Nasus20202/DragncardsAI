from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

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
    assert await repository.add_skill_registry(
        name="demo",
        skill_path="/tmp/demo",
        description=None,
        metadata_json={},
    )
    assert await repository.enable_skill_for_session("missing", "demo", True) is None

    # MCP registry operations
    assert (
        await repository.add_mcp_registry(
            name="test-mcp",
            transport="streamable-http",
            server_url="http://test/mcp",
            headers_json={},
        )
        is not None
    )
    assert await repository.remove_mcp_registry("missing") is False

    # Session MCP enablement for missing session
    assert await repository.enable_mcp_for_session("missing", "test-mcp", True) is None
    assert await repository.get_session_enabled_mcp_state("missing", "test-mcp") is None

    assert await repository.get_skill_assignment("missing") is None


@pytest.mark.asyncio
async def test_session_repository_updates_existing_assignments_and_filters(
    repository: Repository,
):
    active_session = await _create_session_with_model(repository, "active")
    terminated_session = await _create_session_with_model(repository, "terminated")
    await repository.terminate_session(terminated_session.id)

    first_skill = await repository.add_skill_registry(
        name="demo",
        skill_path="/tmp/first",
        description=None,
        metadata_json={},
    )
    await repository.enable_skill_for_session(active_session.id, "demo", enabled=True)
    second_skill = await repository.add_skill_registry(
        name="demo",
        skill_path="/tmp/second",
        description=None,
        metadata_json={},
    )
    await repository.enable_skill_for_session(active_session.id, "demo", enabled=True)
    assert first_skill is not None
    assert first_skill.skill_path == "/tmp/first"
    assert second_skill.skill_path == "/tmp/second"
    assert await repository.remove_skill_assignment(active_session.id, "demo") is True
    assert await repository.remove_skill_assignment(active_session.id, "demo") is False

    assert await repository.get_session_enabled_skill_state("missing", "demo") is None

    # MCP registry operations
    mcp = await repository.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://game-service/mcp/",
        headers_json={},
    )
    assert mcp is not None
    assert mcp.transport == "streamable-http"
    assert mcp.server_url == "http://game-service/mcp/"

    # List registries
    registries = await repository.list_mcp_registries()
    assert len(registries) == 1
    assert registries[0].name == "game-service"

    # Enable MCP for session
    enabled = await repository.enable_mcp_for_session(
        active_session.id, "game-service", True
    )
    assert enabled is not None
    assert enabled.enabled is True

    # Session enabled MCPs
    session_mcps = await repository.list_session_enabled_mcps(active_session.id)
    assert len(session_mcps) == 1
    assert session_mcps[0].mcp_name == "game-service"

    # Remove registry
    assert await repository.remove_mcp_registry("game-service") is True
    assert await repository.remove_mcp_registry("game-service") is False

    sessions, total = await repository.list_sessions(
        status="terminated", limit=10, offset=0
    )
    assert total == 1
    assert [item.id for item in sessions] == [terminated_session.id]


@pytest.mark.asyncio
async def test_list_sessions_excludes_child_subagent_sessions(repository: Repository):
    parent_session = await repository.create_session("parent", {})
    child_session = await repository.create_session("child", {})

    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    child_job = await repository.enqueue_prompt_job(
        child_session.id,
        prompt="child",
        metadata_json={"parent_job_id": parent_job.id},
        max_attempts=1,
    )
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    sessions, total = await repository.list_sessions(limit=10, offset=0)

    assert total == 1
    assert [item.id for item in sessions] == [parent_session.id]
    assert await repository.get_session(child_session.id) is not None


@pytest.mark.asyncio
async def test_enqueue_prompt_job_persists_parent_before_returning(
    repository: Repository,
):
    parent_session = await repository.create_session("parent", {})
    child_session = await repository.create_session("child", {})
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    child_job = await repository.enqueue_prompt_job(
        child_session.id,
        prompt="child",
        metadata_json={"parent_job_id": parent_job.id},
        max_attempts=1,
        parent_job_id=parent_job.id,
    )

    assert child_job is not None
    persisted = await repository.get_job(child_job.id)
    assert persisted is not None
    assert persisted.parent_job_id == parent_job.id


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

    cancelled, _ = await repository.request_cancel(job.id)
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

    assert await repository.request_cancel("missing") == (None, [])
    assert await repository.mark_job_completed("missing", "done") is None
    assert await repository.mark_job_cancelled("missing", reason="missing") is None


@pytest.mark.asyncio
async def test_terminating_session_cancels_queued_jobs(repository: Repository):
    session = await _create_session_with_model(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None

    await repository.terminate_session(session.id)

    cancelled = await repository.get_job(job.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.cancellation_requested_at is not None
    assert await repository.claim_next_job() is None


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


@pytest.mark.asyncio
async def test_session_replay_limits_default_to_unlimited(repository: Repository):
    session = await repository.create_session("demo", {})
    assert session.context_recent_message_limit is None
    assert session.context_recent_tool_exchange_limit is None


@pytest.mark.asyncio
async def test_session_replay_limits_can_be_created_and_updated(repository: Repository):
    session = await repository.create_session(
        "demo",
        {},
        context_recent_message_limit=8,
        context_recent_tool_exchange_limit=2,
    )
    assert session.context_recent_message_limit == 8
    assert session.context_recent_tool_exchange_limit == 2

    updated = await repository.update_session(
        session.id,
        context_recent_message_limit=4,
        context_recent_tool_exchange_limit=None,
    )
    assert updated is not None
    assert updated.context_recent_message_limit == 4
    assert updated.context_recent_tool_exchange_limit is None


@pytest.mark.asyncio
async def test_request_cancel_propagates_to_child_jobs(repository: Repository):
    """Cancelling a parent job must also cancel its active child jobs."""
    session = await _create_session_with_model(repository)

    parent_job = await repository.enqueue_prompt_job(
        session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    # Claim so parent is running
    await repository.claim_next_job()

    # Enqueue two child jobs – one queued, one running
    queued_child = await repository.enqueue_prompt_job(
        session.id, prompt="child queued", metadata_json={}, max_attempts=1
    )
    await repository.set_parent_job_id(queued_child.id, parent_job.id)

    running_child = await repository.enqueue_prompt_job(
        session.id, prompt="child running", metadata_json={}, max_attempts=1
    )
    await repository.set_parent_job_id(running_child.id, parent_job.id)
    await repository.claim_next_job()  # moves queued_child → running (oldest first)

    # Cancel the parent
    cancelled_parent, _ = await repository.request_cancel(parent_job.id)
    assert cancelled_parent is not None
    assert cancelled_parent.cancellation_requested_at is not None

    # Queued child must be immediately cancelled
    cancelled_queued = await repository.get_job(running_child.id)
    assert cancelled_queued is not None
    # running_child was never claimed so it's still queued → immediately cancelled
    assert cancelled_queued.status == "cancelled"
    assert cancelled_queued.cancellation_requested_at is not None

    # Running child must have cancellation requested (worker will pick it up)
    cancelled_running = await repository.get_job(queued_child.id)
    assert cancelled_running is not None
    assert cancelled_running.cancellation_requested_at is not None
    assert await repository.get_job_cancellation_requested(queued_child.id) is True


@pytest.mark.asyncio
async def test_delete_session_removes_every_dependent_row(repository: Repository):
    """A hard delete must leave no rows behind in any session-scoped table.

    The child rows are asserted through raw counts rather than the repository's
    own readers so the test would still catch an orphan that a filtered query
    hides. SQLite does not enforce the declared ON DELETE CASCADE constraints,
    which is exactly why the repository deletes each table explicitly.
    """
    session = await _create_session_with_model(repository, "deletable")
    await repository.add_skill_registry(
        name="delete-skill",
        skill_path="/tmp/delete-skill",
        description=None,
        metadata_json={},
    )
    await repository.enable_skill_for_session(session.id, "delete-skill", True)
    await repository.add_mcp_registry(
        name="delete-mcp",
        transport="streamable-http",
        server_url="http://localhost:9/mcp",
        headers_json={},
    )
    await repository.enable_mcp_for_session(session.id, "delete-mcp", True)
    await repository.upsert_player_config(
        session.id,
        "player1",
        display_name="Player One",
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
        skills=["delete-skill"],
    )
    job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert job is not None
    await repository.store_output(job.id, "some output")
    await repository.create_compaction_record(
        session.id,
        summary_text="summary",
        covers_up_to_job_id=job.id,
        tokens_used=12,
    )

    # A session that keeps its own rows, to prove the delete is scoped.
    survivor = await _create_session_with_model(repository, "survivor")
    survivor_job = await repository.enqueue_prompt_job(
        survivor.id, prompt="keep me", metadata_json={}, max_attempts=1
    )
    assert survivor_job is not None

    assert await repository.delete_session(session.id) is True

    assert await repository.get_session(session.id) is None
    assert await repository.get_job(job.id) is None

    tables = (
        "session_model_configs",
        "session_enabled_skills",
        "session_enabled_mcps",
        "session_player_configs",
        "jobs",
        "job_events",
        "compaction_records",
    )
    async with repository._session_factory() as db:
        assert (
            await db.scalar(
                text("SELECT COUNT(*) FROM agent_sessions WHERE id = :sid"),
                {"sid": session.id},
            )
            == 0
        )
        for table in tables:
            remaining = await db.scalar(
                text(
                    f"SELECT COUNT(*) FROM {table} WHERE session_id = :sid"
                ),  # noqa: S608
                {"sid": session.id},
            )
            assert remaining == 0, f"{table} still holds rows for the deleted session"
        outputs = await db.scalar(
            text("SELECT COUNT(*) FROM job_outputs WHERE job_id = :jid"),
            {"jid": job.id},
        )
        assert outputs == 0
        # The registries are global and must survive.
        assert (
            await db.scalar(
                text(
                    "SELECT COUNT(*) FROM skill_registries WHERE name = 'delete-skill'"
                )
            )
            == 1
        )
        assert (
            await db.scalar(
                text("SELECT COUNT(*) FROM mcp_registries WHERE name = 'delete-mcp'")
            )
            == 1
        )

    # The unrelated session is untouched.
    assert await repository.get_session(survivor.id) is not None
    assert await repository.get_job(survivor_job.id) is not None


@pytest.mark.asyncio
async def test_delete_session_reports_a_missing_session(repository: Repository):
    assert await repository.delete_session("missing") is False


@pytest.mark.asyncio
async def test_delete_session_detaches_subagent_children_in_other_sessions(
    repository: Repository,
):
    """Child jobs living in another session must not keep a dangling parent id."""
    parent_session = await _create_session_with_model(repository, "parent")
    child_session = await _create_session_with_model(repository, "child")
    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="child", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None and child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    assert await repository.delete_session(parent_session.id) is True

    surviving_child = await repository.get_job(child_job.id)
    assert surviving_child is not None
    assert surviving_child.parent_job_id is None
