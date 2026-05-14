"""Unit tests for context metadata API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .context_api_test_support import (
    build_context_test_app,
    build_replay_messages,
    expected_request_tokens,
    expected_token_breakdown,
    make_completed_job,
    make_completed_job_with_tool_exchange,
    make_session_with_model,
)


@pytest.mark.asyncio
async def test_get_context_metadata_active_session(tmp_path: Path):
    app, engine, repo = await build_context_test_app(tmp_path)
    session_id = await make_session_with_model(repo)
    await make_completed_job(repo, session_id)

    try:
        session = await repo.get_session(session_id)
        assert session is not None
        replay_messages = await build_replay_messages(repo, session_id)
        with TestClient(app) as client:
            expected_tokens = await expected_request_tokens(
                app, session, replay_messages
            )
            expected_breakdown = await expected_token_breakdown(
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
    app, engine, repo = await build_context_test_app(tmp_path)
    session_id = await make_session_with_model(repo)

    try:
        session = await repo.get_session(session_id)
        assert session is not None
        with TestClient(app) as client:
            expected_tokens = await expected_request_tokens(app, session, [])
            expected_breakdown = await expected_token_breakdown(app, session, [])
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
    app, engine, repo = await build_context_test_app(tmp_path)
    session_id = await make_session_with_model(repo)
    job_id = await make_completed_job(repo, session_id)
    await repo.create_compaction_record(
        session_id,
        summary_text="summary",
        covers_up_to_job_id=job_id,
        tokens_used=30,
    )

    try:
        session = await repo.get_session(session_id)
        assert session is not None
        replay_messages = await build_replay_messages(repo, session_id)
        with TestClient(app) as client:
            expected_tokens = await expected_request_tokens(
                app, session, replay_messages
            )
            expected_breakdown = await expected_token_breakdown(
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
    app, engine, repo = await build_context_test_app(tmp_path)
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

    await make_completed_job(repo, session.id, prompt="first", output="first reply")
    await make_completed_job_with_tool_exchange(
        repo,
        session.id,
        prompt="second",
        output="second reply",
        tool_call_id="tool-1",
        tool_name="get_game_state",
        result={"state": {"villain": "Rhino"}},
    )

    try:
        reloaded_session = await repo.get_session(session.id)
        assert reloaded_session is not None
        expected_messages = await build_replay_messages(repo, session.id)
        with TestClient(app) as client:
            expected_tokens = await expected_request_tokens(
                app, reloaded_session, expected_messages
            )
            expected_breakdown = await expected_token_breakdown(
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
    app, engine, _repo = await build_context_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/sessions/no-such-session/context")
        assert response.status_code == 404
    finally:
        await engine.dispose()
