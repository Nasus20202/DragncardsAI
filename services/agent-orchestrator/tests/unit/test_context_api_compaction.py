"""Unit tests for context compaction API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .context_api_test_support import (
    build_context_test_app,
    make_completed_job,
    make_session_with_model,
)


@pytest.mark.asyncio
async def test_compact_session_success(tmp_path: Path):
    app, engine, repo = await build_context_test_app(tmp_path)
    session_id = await make_session_with_model(repo)
    await make_completed_job(repo, session_id)

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
    app, engine, _repo = await build_context_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post("/sessions/nonexistent-session-id/compact")
        assert response.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_compact_session_409_when_memory_disabled(tmp_path: Path):
    app, engine, repo = await build_context_test_app(tmp_path)
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
