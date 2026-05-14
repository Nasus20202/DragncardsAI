from __future__ import annotations

import pytest

from agent_orchestrator.runtime.memory import build_message_history
from agent_orchestrator.storage.repository import Repository

from .memory_test_support import complete_job, make_session, repository


@pytest.mark.asyncio
async def test_build_message_history_no_prior_jobs(repository: Repository):
    session = await make_session(repository)
    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    assert history == []


@pytest.mark.asyncio
async def test_build_message_history_with_prior_jobs(repository: Repository):
    session = await make_session(repository)

    await complete_job(repository, session.id, "first prompt", "first response")
    await complete_job(repository, session.id, "second prompt", "second response")

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="third prompt", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)

    assert [message["role"] for message in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert history[0]["content"] == "first prompt"
    assert history[1]["content"] == "first response"
    assert history[2]["content"] == "second prompt"
    assert history[3]["content"] == "second response"


@pytest.mark.asyncio
async def test_build_message_history_with_compaction_checkpoint(
    repository: Repository,
):
    session = await make_session(repository)

    job1_id = await complete_job(repository, session.id, "job1 prompt", "job1 response")
    await complete_job(repository, session.id, "job2 prompt", "job2 response")

    await repository.create_compaction_record(
        session.id,
        summary_text="Game summary after turn 1",
        covers_up_to_job_id=job1_id,
        tokens_used=200,
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="job3 prompt", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)

    assert history[0]["role"] == "system"
    assert history[0]["content"] == "Game summary after turn 1"
    assert history[1]["role"] == "user"
    assert history[1]["content"] == "job2 prompt"
    assert history[2]["role"] == "assistant"
    assert history[2]["content"] == "job2 response"


@pytest.mark.asyncio
async def test_build_message_history_applies_recent_message_limit(
    repository: Repository,
):
    session = await repository.create_session(
        "test", {}, multi_turn_memory=True, context_recent_message_limit=2
    )
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    await complete_job(repository, session.id, "first prompt", "first response")
    await complete_job(repository, session.id, "second prompt", "second response")

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="third prompt", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    assert history == [
        {"role": "user", "content": "second prompt"},
        {"role": "assistant", "content": "second response"},
    ]


@pytest.mark.asyncio
async def test_build_message_history_preserves_compaction_summary_outside_limits(
    repository: Repository,
):
    session = await repository.create_session(
        "test", {}, multi_turn_memory=True, context_recent_message_limit=1
    )
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    job1_id = await complete_job(repository, session.id, "first", "first response")
    await repository.create_compaction_record(
        session.id,
        summary_text="summary",
        covers_up_to_job_id=job1_id,
        tokens_used=100,
    )
    await complete_job(repository, session.id, "second", "second response")

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="third", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    assert history[0] == {"role": "system", "content": "summary"}
    assert history[1:] == [{"role": "assistant", "content": "second response"}]
