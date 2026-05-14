from __future__ import annotations

import pytest

from agent_orchestrator.runtime.memory import build_message_history
from agent_orchestrator.storage.repository import Repository

from .memory_test_support import (
    complete_job_with_tool_exchange,
    make_session,
    repository,
)


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

    await complete_job_with_tool_exchange(
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
    await complete_job_with_tool_exchange(
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

    await complete_job_with_tool_exchange(
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
    await complete_job_with_tool_exchange(
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
    await complete_job_with_tool_exchange(
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
