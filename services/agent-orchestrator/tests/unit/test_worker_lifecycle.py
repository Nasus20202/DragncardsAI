from __future__ import annotations

import asyncio

import pytest

from agent_orchestrator.integrations.bifrost import BifrostError, ChatResponse
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.storage.repository import Repository

from .worker_test_support import (
    FailingClaimRepository,
    FakeBifrost,
    FakeMcp,
    make_worker,
    prepare_session,
    repository,
    skill_registry,
)


@pytest.mark.asyncio
async def test_worker_survives_transient_claim_failures(skill_registry):
    repository = FailingClaimRepository()
    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(),
        mcp_client=FakeMcp(),
    )

    task = asyncio.create_task(worker.run_forever())
    await asyncio.wait_for(repository.recovered.wait(), timeout=1)
    await worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert repository.calls >= 2


@pytest.mark.asyncio
async def test_worker_terminates_child_session_on_completion(
    repository: Repository, skill_registry
):
    parent_session = await prepare_session(repository)
    child_session = await repository.create_session("child", {})
    await repository.set_model_config(
        child_session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repository.add_skill_assignment(
        child_session.id, "demo-skill", str(skill_registry._roots[0] / "demo-skill")
    )

    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="child task", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    claimed = await repository.claim_next_job()
    if claimed is not None and claimed.id == parent_job.id:
        claimed = await repository.claim_next_job()
    assert claimed is not None and claimed.id == child_job.id

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            responses=[ChatResponse(content="child done", tool_calls=[], raw={})]
        ),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    stored_child = await repository.get_job(child_job.id)
    assert stored_child is not None
    assert stored_child.status == "completed"

    child_sess = await repository.get_session(child_session.id)
    assert child_sess is not None
    assert child_sess.status == "terminated"


@pytest.mark.asyncio
async def test_worker_terminates_child_session_on_failure(
    repository: Repository, skill_registry
):
    parent_session = await prepare_session(repository)
    child_session = await repository.create_session("child", {})
    await repository.set_model_config(
        child_session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    parent_job = await repository.enqueue_prompt_job(
        parent_session.id, prompt="parent", metadata_json={}, max_attempts=1
    )
    assert parent_job is not None

    child_job = await repository.enqueue_prompt_job(
        child_session.id, prompt="child task", metadata_json={}, max_attempts=1
    )
    assert child_job is not None
    await repository.set_parent_job_id(child_job.id, parent_job.id)

    claimed = await repository.claim_next_job()
    if claimed is not None and claimed.id == parent_job.id:
        claimed = await repository.claim_next_job()
    assert claimed is not None and claimed.id == child_job.id

    worker = make_worker(
        skill_registry=skill_registry,
        repository=repository,
        bifrost_client=FakeBifrost(
            error=BifrostError("gateway_error", "permanent failure", retryable=False)
        ),
        mcp_client=FakeMcp(),
    )

    await worker._run_job(claimed)

    stored_child = await repository.get_job(child_job.id)
    assert stored_child is not None
    assert stored_child.status == "failed"

    child_sess = await repository.get_session(child_session.id)
    assert child_sess is not None
    assert child_sess.status == "terminated"
