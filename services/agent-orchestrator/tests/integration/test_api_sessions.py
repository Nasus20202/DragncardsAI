from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_mcp_assignment_list_normalizes_and_remove_lifecycle(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post(
            "/sessions",
            json={
                "name": "mcp-lifecycle",
                "context_recent_message_limit": 3,
                "context_recent_tool_exchange_limit": 1,
            },
        )
        session_id = create_response.json()["session"]["id"]

        assign_response = await client.post(
            f"/sessions/{session_id}/mcps",
            json={
                "name": "game-service",
                "server_url": "http://game-service/mcp",
            },
        )
        list_response = await client.get(f"/sessions/{session_id}/mcps")
        session_response = await client.get(f"/sessions/{session_id}")
        remove_response = await client.delete(
            f"/sessions/{session_id}/mcps/game-service"
        )
        list_after_remove_response = await client.get(f"/sessions/{session_id}/mcps")
        remove_missing_response = await client.delete(
            f"/sessions/{session_id}/mcps/game-service"
        )

    assert assign_response.status_code == 201
    assigned_mcp = assign_response.json()["mcp"]
    assert assigned_mcp["server_url"] == "http://game-service/mcp/"

    assert list_response.status_code == 200
    listed_mcps = list_response.json()["mcps"]
    assert len(listed_mcps) == 1
    assert listed_mcps[0]["name"] == "game-service"
    assert listed_mcps[0]["server_url"] == "http://game-service/mcp/"

    assert session_response.status_code == 200
    session = session_response.json()["session"]
    assert session["context_recent_message_limit"] == 3
    assert session["context_recent_tool_exchange_limit"] == 1

    assert remove_response.status_code == 204
    assert list_after_remove_response.status_code == 200
    assert list_after_remove_response.json() == {"mcps": []}
    assert remove_missing_response.status_code == 404


@pytest.mark.asyncio
async def test_list_session_jobs_supports_empty_filtered_result(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "job-filter"})
        session_id = create_response.json()["session"]["id"]

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "queued only"},
        )
        job_id = prompt_response.json()["job"]["id"]
        filtered_response = await client.get(
            f"/sessions/{session_id}/jobs",
            params={"status": "failed", "limit": 10, "offset": 0},
        )

    assert job_id
    assert filtered_response.status_code == 200
    assert filtered_response.json()["jobs"] == []
    assert filtered_response.json()["page"]["total"] == 0
