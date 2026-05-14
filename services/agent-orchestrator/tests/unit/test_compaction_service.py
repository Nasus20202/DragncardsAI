from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_orchestrator.integrations.bifrost import ChatResponse
from agent_orchestrator.runtime.compaction import perform_compaction
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "compaction_service.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


async def make_session_with_model(repo: Repository):
    session = await repo.create_session("test", {})
    model_config = await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    assert model_config is not None
    return session, model_config


async def make_completed_job(
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
async def test_perform_compaction_uses_token_count_fallback_when_response_has_no_usage(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    await make_completed_job(repository, session.id, "turn 1", "response 1")

    bifrost = AsyncMock()
    bifrost.chat_completion.return_value = ChatResponse(
        content="Summary only",
        tool_calls=[],
        raw={},
    )

    record = await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )

    assert record.summary_text == "Summary only"
    assert record.tokens_used > 0


@pytest.mark.asyncio
async def test_perform_compaction_includes_previous_summary_and_publishes_event(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    first_job_id = await make_completed_job(
        repository, session.id, "turn 1", "response 1"
    )
    await repository.create_compaction_record(
        session.id,
        summary_text="Earlier summary",
        covers_up_to_job_id=first_job_id,
        tokens_used=12,
    )
    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next", metadata_json={}, max_attempts=1
    )
    assert current_job is not None

    captured_messages = []

    async def fake_chat_completion(*args, **kwargs):
        captured_messages.extend(args[3])
        return ChatResponse(
            content="Updated summary",
            tool_calls=[],
            raw={"usage": {"total_tokens": 21}},
        )

    live_event_bus = InMemoryLiveEventBus()
    subscriber = await live_event_bus.subscribe(current_job.id)
    try:
        record = await perform_compaction(
            repository=repository,
            bifrost_client=type(
                "FakeBifrost", (), {"chat_completion": fake_chat_completion}
            )(),
            session_id=session.id,
            model_config=model_config,
            current_job_id=current_job.id,
            live_event_bus=live_event_bus,
        )
        event = await subscriber.get(0.1)
    finally:
        await subscriber.aclose()

    assert record.summary_text == "Updated summary"
    assert any(
        message["role"] == "system"
        and "Previous summary:\nEarlier summary" in message["content"]
        for message in captured_messages
    )
    assert event is not None
    assert event.event_type == "compaction"
    assert event.payload_json["summary_text"] == "Updated summary"
    assert event.payload_json["tokens_used"] == 21


@pytest.mark.asyncio
async def test_perform_compaction_rejects_completed_jobs_without_history_content(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="", metadata_json={}, max_attempts=1
    )
    assert job is not None
    await repository.claim_next_job()
    await repository.mark_job_completed(job.id, "")

    bifrost = AsyncMock()

    with pytest.raises(ValueError, match="No history content to compact"):
        await perform_compaction(
            repository=repository,
            bifrost_client=bifrost,
            session_id=session.id,
            model_config=model_config,
        )

    bifrost.chat_completion.assert_not_called()
