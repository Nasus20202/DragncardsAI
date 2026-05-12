"""Unit tests for context management API endpoints (compact and context metadata)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_orchestrator.integrations.bifrost import BifrostClient, ChatResponse
from agent_orchestrator.integrations.mcp.client import (
    McpToolDefinition,
    StreamableHttpMcpClient,
)
from agent_orchestrator.runtime.memory import build_message_history
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import build_system_prompt
from agent_orchestrator.runtime.tokens import (
    estimate_tokens_for_messages,
    estimate_tokens_for_tools,
)
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrostClient(BifrostClient):
    def __init__(self):
        self.compact_response = "Hero HP: 12/15, Villain HP: 30/60, villain stage 1."

    async def aclose(self) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def list_models(self, provider_id: str):
        return []

    async def get_model_context_length(
        self, provider_id: str, model_name: str
    ) -> int | None:
        return None

    async def chat_completion(self, *args, **kwargs) -> ChatResponse:
        return ChatResponse(
            content=self.compact_response,
            tool_calls=[],
            raw={"usage": {"total_tokens": 42}},
        )


class FakeMcpClient(StreamableHttpMcpClient):
    def __init__(self):
        pass

    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]


async def _build_test_app(tmp_path: Path, bifrost_client=None):
    database_path = tmp_path / "context_api_test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    app = create_app(
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            bifrost_url="http://bifrost",
            bifrost_api_key="dummy",
            SKILL_ROOTS=str(skill_root),
            ENABLED_PROVIDER_IDS="openai,gemini",
        ),
        repository=repository,
        bifrost_client=bifrost_client or FakeBifrostClient(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeMcpClient(),
        skill_registry=SkillRegistry((skill_root,)),
    )
    return app, engine, repository


async def _expected_request_tokens(app, session, replay_messages):
    system_prompt = build_system_prompt(
        app.state.skill_registry, session.skill_assignments
    )
    listed_tool_definitions = await app.state.mcp_tool_catalog.list_session_tools(
        session.mcp_assignments,
        ignore_failures=True,
    )
    tool_definitions = app.state.mcp_tool_catalog.as_openai_tools(
        listed_tool_definitions
    )
    return (
        estimate_tokens_for_messages([{"role": "system", "content": system_prompt}])
        + estimate_tokens_for_messages(replay_messages)
        + estimate_tokens_for_tools(tool_definitions)
    )


async def _expected_token_breakdown(app, session, replay_messages):
    system_prompt = build_system_prompt(
        app.state.skill_registry, session.skill_assignments
    )
    listed_tool_definitions = await app.state.mcp_tool_catalog.list_session_tools(
        session.mcp_assignments,
        ignore_failures=True,
    )
    tool_definitions = app.state.mcp_tool_catalog.as_openai_tools(
        listed_tool_definitions
    )
    return {
        "system_prompt": estimate_tokens_for_messages(
            [{"role": "system", "content": system_prompt}]
        ),
        "replay": estimate_tokens_for_messages(replay_messages),
        "tools": estimate_tokens_for_tools(tool_definitions),
    }


async def _make_session_with_model(repo: Repository) -> str:
    session = await repo.create_session("test", {})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    return session.id


async def _make_completed_job(
    repo: Repository, session_id: str, prompt: str = "hi", output: str = "ok"
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.update_job_tokens_used(job.id, 100)
    await repo.mark_job_completed(job.id, output)
    return job.id


async def _make_completed_job_with_tool_exchange(
    repo: Repository,
    session_id: str,
    *,
    prompt: str,
    output: str,
    tool_call_id: str,
    tool_name: str,
    result: dict,
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.append_event(
        job.id,
        session_id,
        "tool_call",
        {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": f"game-service_{tool_name}",
            "tool_name": tool_name,
            "assignment": "game-service",
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
            "exposed_tool_name": f"game-service_{tool_name}",
            "tool_name": tool_name,
            "assignment": "game-service",
            "server_url": "http://localhost:4001/mcp/",
            "is_error": False,
            "result": result,
        },
    )
    await repo.update_job_tokens_used(job.id, 500)
    await repo.mark_job_completed(job.id, output)
    return job.id


# ---------------------------------------------------------------------------
# 5.4 Manual compaction endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compact_session_success(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    session_id = await _make_session_with_model(repo)
    await _make_completed_job(repo, session_id)

    try:
        with TestClient(app) as client:
            response = client.post(f"/sessions/{session_id}/compact")
        assert response.status_code == 200
        body = response.json()
        assert body["compaction_count"] == 1
        assert "tokens_used" in body
        assert "usage_ratio" in body
        assert body["multi_turn_memory"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compact_session_404(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post("/sessions/nonexistent-session-id/compact")
        assert response.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compact_session_409_when_memory_disabled(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    # Create session with multi_turn_memory=False
    session = await repo.create_session("test", {})
    await repo.update_multi_turn_memory(session.id, multi_turn_memory=False)
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    try:
        with TestClient(app) as client:
            response = client.post(f"/sessions/{session.id}/compact")
        assert response.status_code == 409
        assert "multi_turn_memory" in response.json()["detail"].lower()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 7.2 Context metadata endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_context_metadata_active_session(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    session_id = await _make_session_with_model(repo)
    latest_job_id = await _make_completed_job(repo, session_id)

    try:
        session = await repo.get_session(session_id)
        assert session is not None
        # Use sentinel "" so all completed jobs are included (same as production).
        replay_messages = await build_message_history(repo, session_id, "")
        with TestClient(app) as client:
            expected_tokens = await _expected_request_tokens(
                app,
                session,
                replay_messages,
            )
            expected_breakdown = await _expected_token_breakdown(
                app, session, replay_messages
            )
            response = client.get(f"/sessions/{session_id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["tokens_used"] == expected_tokens
        assert body["token_breakdown"] == expected_breakdown
        assert body["context_window_size"] == 128000
        assert 0.0 <= body["usage_ratio"] <= 1.0
        assert body["compaction_count"] == 0
        assert body["last_compacted_at"] is None
        assert body["multi_turn_memory"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_context_metadata_no_compactions(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    session_id = await _make_session_with_model(repo)

    try:
        session = await repo.get_session(session_id)
        assert session is not None
        with TestClient(app) as client:
            expected_tokens = await _expected_request_tokens(app, session, [])
            expected_breakdown = await _expected_token_breakdown(app, session, [])
            response = client.get(f"/sessions/{session_id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["tokens_used"] == expected_tokens
        assert body["token_breakdown"] == expected_breakdown
        assert body["compaction_count"] == 0
        assert body["last_compacted_at"] is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_context_metadata_post_compaction(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    session_id = await _make_session_with_model(repo)
    job_id = await _make_completed_job(repo, session_id)
    await repo.create_compaction_record(
        session_id,
        summary_text="summary",
        covers_up_to_job_id=job_id,
        tokens_used=30,
    )

    try:
        session = await repo.get_session(session_id)
        assert session is not None
        replay_messages = await build_message_history(repo, session_id, job_id)
        with TestClient(app) as client:
            expected_tokens = await _expected_request_tokens(
                app,
                session,
                replay_messages,
            )
            expected_breakdown = await _expected_token_breakdown(
                app, session, replay_messages
            )
            response = client.get(f"/sessions/{session_id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["compaction_count"] == 1
        assert body["last_compacted_at"] is not None
        assert body["tokens_used"] == expected_tokens
        assert body["token_breakdown"] == expected_breakdown
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_context_metadata_uses_replay_window_not_full_history(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    session = await repo.create_session(
        "test",
        {},
        context_recent_message_limit=2,
        context_recent_tool_exchange_limit=1,
    )
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )

    await _make_completed_job(repo, session.id, prompt="first", output="first reply")
    await _make_completed_job_with_tool_exchange(
        repo,
        session.id,
        prompt="second",
        output="second reply",
        tool_call_id="tool-1",
        tool_name="get_game_state",
        result={"state": {"villain": "Rhino"}},
    )

    try:
        latest_job_id = await repo.get_latest_completed_job_id(session.id)
        assert latest_job_id is not None
        reloaded_session = await repo.get_session(session.id)
        assert reloaded_session is not None
        # Use sentinel "" so all completed jobs are included (same as production).
        expected_messages = await build_message_history(repo, session.id, "")
        with TestClient(app) as client:
            expected_tokens = await _expected_request_tokens(
                app,
                reloaded_session,
                expected_messages,
            )
            expected_breakdown = await _expected_token_breakdown(
                app, reloaded_session, expected_messages
            )
            response = client.get(f"/sessions/{session.id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["tokens_used"] == expected_tokens
        assert body["token_breakdown"] == expected_breakdown
        assert body["tokens_used"] < 500
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_context_metadata_404(tmp_path: Path):
    app, engine, repo = await _build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/sessions/no-such-session/context")
        assert response.status_code == 404
    finally:
        await engine.dispose()
