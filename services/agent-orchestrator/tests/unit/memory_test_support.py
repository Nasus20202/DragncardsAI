from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

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


async def make_session(repo: Repository, multi_turn_memory: bool = True):
    session = await repo.create_session("test", {}, multi_turn_memory=multi_turn_memory)
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    return session


async def complete_job(
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


async def complete_job_with_tool_exchange(
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


def make_mock_job_with_tool_events():
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
    return mock_job
