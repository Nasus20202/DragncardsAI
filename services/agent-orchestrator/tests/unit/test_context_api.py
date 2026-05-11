"""Unit tests for context management API endpoints (compact and context metadata)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_orchestrator.integrations.bifrost import BifrostClient, ChatResponse
from agent_orchestrator.integrations.mcp.client import StreamableHttpMcpClient, McpToolDefinition
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
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

    async def get_model_context_length(self, provider_id: str, model_name: str) -> int | None:
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


async def _make_completed_job(repo: Repository, session_id: str, prompt: str = "hi", output: str = "ok") -> str:
    job = await repo.enqueue_prompt_job(session_id, prompt=prompt, metadata_json={}, max_attempts=1)
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.update_job_tokens_used(job.id, 100)
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
    await _make_completed_job(repo, session_id)

    try:
        with TestClient(app) as client:
            response = client.get(f"/sessions/{session_id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["tokens_used"] == 100
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
        with TestClient(app) as client:
            response = client.get(f"/sessions/{session_id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["tokens_used"] == 0
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
        with TestClient(app) as client:
            response = client.get(f"/sessions/{session_id}/context")
        assert response.status_code == 200
        body = response.json()
        assert body["compaction_count"] == 1
        assert body["last_compacted_at"] is not None
        # tokens_used includes the compaction summary tokens as baseline (30)
        assert body["tokens_used"] == 30
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
