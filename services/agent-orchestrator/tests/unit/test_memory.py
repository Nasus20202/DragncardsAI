"""Unit tests for multi-turn message history builder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_orchestrator.runtime.memory import (
    _reconstruct_job_messages,
    build_message_history,
)
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "memory_test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


async def _make_session(repo: Repository, multi_turn_memory: bool = True):
    session = await repo.create_session("test", {}, multi_turn_memory=multi_turn_memory)
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    return session


async def _complete_job(
    repo: Repository, session_id: str, prompt: str, output: str
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.mark_job_completed(job.id, output)
    return job.id


async def _complete_job_with_tool_exchange(
    repo: Repository,
    session_id: str,
    *,
    prompt: str,
    assistant_text: str,
    tool_call_id: str,
    exposed_tool_name: str,
    tool_name: str,
    assignment: str,
    result: dict,
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None
    await repo.append_event(
        job.id, session_id, "model_output", {"text": assistant_text}
    )
    await repo.append_event(
        job.id,
        session_id,
        "tool_call",
        {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": exposed_tool_name,
            "tool_name": tool_name,
            "assignment": assignment,
            "server_url": "http://localhost:4001/mcp/",
            "arguments": {},
        },
    )
    await repo.append_event(
        job.id,
        session_id,
        "tool_result",
        {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": exposed_tool_name,
            "tool_name": tool_name,
            "assignment": assignment,
            "server_url": "http://localhost:4001/mcp/",
            "is_error": False,
            "result": result,
        },
    )
    await repo.mark_job_completed(job.id, assistant_text)
    return job.id


@pytest.mark.asyncio
async def test_build_message_history_no_prior_jobs(repository: Repository):
    session = await _make_session(repository)
    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="hello", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    assert history == []


@pytest.mark.asyncio
async def test_build_message_history_with_prior_jobs(repository: Repository):
    session = await _make_session(repository)

    await _complete_job(repository, session.id, "first prompt", "first response")
    await _complete_job(repository, session.id, "second prompt", "second response")

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="third prompt", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)

    # Should have: user, assistant, user, assistant (two prior jobs)
    roles = [m["role"] for m in history]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"] == "first prompt"
    assert history[1]["content"] == "first response"
    assert history[2]["content"] == "second prompt"
    assert history[3]["content"] == "second response"


@pytest.mark.asyncio
async def test_build_message_history_with_compaction_checkpoint(repository: Repository):
    session = await _make_session(repository)

    job1_id = await _complete_job(
        repository, session.id, "job1 prompt", "job1 response"
    )
    job2_id = await _complete_job(
        repository, session.id, "job2 prompt", "job2 response"
    )

    # Create a compaction record covering up to job1
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

    # Should have: compaction summary (system), then only job2 events
    assert history[0]["role"] == "system"
    assert history[0]["content"] == "Game summary after turn 1"
    assert history[1]["role"] == "user"
    assert history[1]["content"] == "job2 prompt"
    assert history[2]["role"] == "assistant"
    assert history[2]["content"] == "job2 response"


def test_reconstruct_job_messages_with_tool_calls():
    """Unit test for tool call reconstruction without hitting DB."""
    mock_job = MagicMock()
    mock_job.prompt = "do a thing"

    model_event = MagicMock()
    model_event.id = 1
    model_event.event_type = "model_output"
    model_event.payload_json = {"text": "Using tool..."}

    tool_call_event = MagicMock()
    tool_call_event.id = 2
    tool_call_event.event_type = "tool_call"
    tool_call_event.payload_json = {
        "tool_call_id": "tc1",
        "exposed_tool_name": "draw_card",
        "arguments": {"player": "player1"},
    }

    tool_result_event = MagicMock()
    tool_result_event.id = 3
    tool_result_event.event_type = "tool_result"
    tool_result_event.payload_json = {
        "tool_call_id": "tc1",
        "exposed_tool_name": "draw_card",
        "result": {"ok": True},
    }

    completion_event = MagicMock()
    completion_event.id = 4
    completion_event.event_type = "completion"
    completion_event.payload_json = {"text": "Done"}

    mock_job.events = [
        model_event,
        tool_call_event,
        tool_result_event,
        completion_event,
    ]

    messages = _reconstruct_job_messages(mock_job)

    assert messages[0] == {"role": "user", "content": "do a thing"}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Using tool..."
    assert len(messages[1]["tool_calls"]) == 1
    assert messages[1]["tool_calls"][0]["id"] == "tc1"
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "tc1"


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

    await _complete_job(repository, session.id, "first prompt", "first response")
    await _complete_job(repository, session.id, "second prompt", "second response")

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
async def test_build_message_history_applies_recent_tool_exchange_limit(
    repository: Repository,
):
    session = await repository.create_session(
        "test", {}, multi_turn_memory=True, context_recent_tool_exchange_limit=1
    )
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    await _complete_job_with_tool_exchange(
        repository,
        session.id,
        prompt="turn 1",
        assistant_text="calling one",
        tool_call_id="tc1",
        exposed_tool_name="game-service_next_step",
        tool_name="next_step",
        assignment="game-service",
        result={"ok": 1},
    )
    await _complete_job_with_tool_exchange(
        repository,
        session.id,
        prompt="turn 2",
        assistant_text="calling two",
        tool_call_id="tc2",
        exposed_tool_name="game-service_next_step",
        tool_name="next_step",
        assignment="game-service",
        result={"ok": 2},
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="turn 3", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    tool_messages = [message for message in history if message["role"] == "tool"]
    assistant_tool_messages = [
        message
        for message in history
        if message["role"] == "assistant" and "tool_calls" in message
    ]

    assert len(tool_messages) == 1
    assert len(assistant_tool_messages) == 1
    assert assistant_tool_messages[0]["content"] == "calling two"
    assert tool_messages[0]["tool_call_id"] == "tc2"


@pytest.mark.asyncio
async def test_build_message_history_prefers_newest_state_heavy_exchange(
    repository: Repository,
):
    session = await repository.create_session(
        "test", {}, multi_turn_memory=True, context_recent_tool_exchange_limit=1
    )
    await repository.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    await _complete_job_with_tool_exchange(
        repository,
        session.id,
        prompt="state one",
        assistant_text="snapshot one",
        tool_call_id="tc1",
        exposed_tool_name="game-service_get_game_state",
        tool_name="get_game_state",
        assignment="game-service",
        result={"state": 1},
    )
    await _complete_job_with_tool_exchange(
        repository,
        session.id,
        prompt="lookup",
        assistant_text="lookup card",
        tool_call_id="tc2",
        exposed_tool_name="game-service_search_cards_marvel_champions",
        tool_name="search_cards_marvel_champions",
        assignment="game-service",
        result={"cards": ["A"]},
    )
    await _complete_job_with_tool_exchange(
        repository,
        session.id,
        prompt="state two",
        assistant_text="snapshot two",
        tool_call_id="tc3",
        exposed_tool_name="game-service_execute_action",
        tool_name="execute_action",
        assignment="game-service",
        result={"state": 2},
    )

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    tool_messages = [message for message in history if message["role"] == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "tc3"


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

    job1_id = await _complete_job(repository, session.id, "first", "first response")
    await repository.create_compaction_record(
        session.id,
        summary_text="summary",
        covers_up_to_job_id=job1_id,
        tokens_used=100,
    )
    await _complete_job(repository, session.id, "second", "second response")

    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="third", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await build_message_history(repository, session.id, current_job.id)
    assert history[0] == {"role": "system", "content": "summary"}
    assert history[1:] == [{"role": "assistant", "content": "second response"}]
