from __future__ import annotations

from pathlib import Path

import pytest

from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import build_system_prompt
from agent_orchestrator.runtime.tokens import (
    estimate_tokens_for_messages,
    estimate_tokens_for_tools,
)
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeMcp:
    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]


@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "session_transcript.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


@pytest.fixture
def skill_registry(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    skill_dir = root / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("follow instructions", encoding="utf-8")
    return SkillRegistry((root,))


async def _make_session(repo: Repository, multi_turn_memory: bool = True):
    session = await repo.create_session("test", {}, multi_turn_memory=multi_turn_memory)
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    await repo.add_skill_assignment(session.id, "demo-skill", "/tmp/demo-skill")
    await repo.add_mcp_assignment(
        session.id,
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp",
        headers_json={},
    )
    return session


async def _complete_job(
    repo: Repository, session_id: str, prompt: str, output: str, tokens: int = 100
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    assert job is not None
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.update_job_tokens_used(job.id, tokens)
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
    await repo.claim_next_job()
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
async def test_session_transcript_builds_history_with_compaction(
    repository: Repository,
):
    session = await _make_session(repository)
    first_job_id = await _complete_job(repository, session.id, "first", "first reply")
    await _complete_job(repository, session.id, "second", "second reply")
    await repository.create_compaction_record(
        session.id,
        summary_text="summary",
        covers_up_to_job_id=first_job_id,
        tokens_used=100,
    )
    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="third", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    await repository.claim_next_job()

    history = await SessionTranscriptService(repository).build_message_history(
        session.id, current_job.id
    )

    assert history == [
        {"role": "system", "content": "summary"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "second reply"},
    ]


@pytest.mark.asyncio
async def test_session_transcript_prefers_newest_state_heavy_tool_exchange(
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

    history = await SessionTranscriptService(repository).build_message_history(
        session.id, current_job.id
    )
    tool_messages = [message for message in history if message["role"] == "tool"]

    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "tc3"


@pytest.mark.asyncio
async def test_session_transcript_builds_context_metadata(
    repository: Repository, skill_registry: SkillRegistry
):
    session = await _make_session(repository)
    await _complete_job(repository, session.id, "first", "reply", tokens=150)

    transcript = SessionTranscriptService(repository)
    mcp_tool_catalog = McpToolCatalog(FakeMcp())
    metadata = await transcript.build_context_metadata(
        session.id,
        128000,
        skill_registry=skill_registry,
        mcp_tool_catalog=mcp_tool_catalog,
    )

    reloaded_session = await repository.get_session(session.id)
    assert reloaded_session is not None
    replay_messages = await transcript.build_message_history(session.id, "")
    expected_breakdown = {
        "system_prompt": estimate_tokens_for_messages(
            [
                {
                    "role": "system",
                    "content": build_system_prompt(
                        skill_registry, reloaded_session.skill_assignments
                    ),
                }
            ]
        ),
        "replay": estimate_tokens_for_messages(replay_messages),
        "tools": estimate_tokens_for_tools(
            mcp_tool_catalog.as_openai_tools(
                await mcp_tool_catalog.list_session_tools(
                    reloaded_session.mcp_assignments,
                    ignore_failures=True,
                )
            )
        ),
    }

    assert metadata.multi_turn_memory is True
    assert metadata.compaction_count == 0
    assert metadata.last_compacted_at is None
    assert metadata.token_breakdown == expected_breakdown
    assert metadata.tokens_used == sum(expected_breakdown.values())
    assert 0.0 <= metadata.usage_ratio <= 1.0
