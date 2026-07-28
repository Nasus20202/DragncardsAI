from __future__ import annotations

import asyncio

import httpx
import pytest

from .api_test_support import INTEGRATION_MODEL_CONFIG


@pytest.mark.asyncio
async def test_context_endpoint_returns_metadata_for_active_session(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "context-demo"})
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json=INTEGRATION_MODEL_CONFIG,
        )
        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "take the next step"},
        )
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(40):
            job_response = await client.get(f"/jobs/{job_id}")
            if job_response.json()["job"]["status"] == "completed":
                break
            await asyncio.sleep(0.05)

        context_response = await client.get(f"/sessions/{session_id}/context")

    assert context_response.status_code == 200
    body = context_response.json()
    assert body["tokens_used"] >= 0
    assert body["context_window_size"] > 0
    assert 0.0 <= body["usage_ratio"] <= 1.0
    assert body["multi_turn_memory"] is True
    assert set(body["token_breakdown"].keys()) == {"system_prompt", "replay", "tools"}


@pytest.mark.asyncio
async def test_manual_compaction_rejects_session_without_model_config(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post(
            "/sessions",
            json={"name": "no-model"},
        )
        session_id = create_response.json()["session"]["id"]

        response = await client.post(f"/sessions/{session_id}/compact")

    assert response.status_code == 422
    assert response.json()["detail"] == "Session has no model configuration"


@pytest.mark.asyncio
async def test_manual_compaction_rejects_session_without_completed_history(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post(
            "/sessions",
            json={"name": "no-history"},
        )
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json=INTEGRATION_MODEL_CONFIG,
        )

        response = await client.post(f"/sessions/{session_id}/compact")

    assert response.status_code == 422
    assert response.json()["detail"] == "No completed jobs to compact"
