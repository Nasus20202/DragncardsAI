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


@pytest.mark.asyncio
async def test_session_endpoints_return_404_for_missing_resources(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session_response = await client.get("/sessions/missing")
        update_response = await client.patch("/sessions/missing", json={"name": "x"})
        terminate_response = await client.post("/sessions/missing/terminate")
        model_config_response = await client.put(
            "/sessions/missing/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        skill_response = await client.post(
            "/sessions/missing/skills",
            json={"skill_name": "test-skill"},
        )
        mcp_response = await client.post(
            "/sessions/missing/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

    assert session_response.status_code == 404
    assert update_response.status_code == 404
    assert terminate_response.status_code == 404
    assert model_config_response.status_code == 404
    assert skill_response.status_code == 404
    assert mcp_response.status_code == 404


@pytest.mark.asyncio
async def test_set_model_config_rejects_unsupported_provider(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post(
            "/sessions", json={"name": "unsupported-provider"}
        )
        session_id = create_response.json()["session"]["id"]
        response = await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "unsupported", "model_name": "x"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported provider"


@pytest.mark.asyncio
async def test_assign_skill_rejects_unknown_skill(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "skill-error"})
        session_id = create_response.json()["session"]["id"]
        response = await client.post(
            f"/sessions/{session_id}/skills",
            json={"skill_name": "unknown-skill"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown skill"


@pytest.mark.asyncio
async def test_session_tools_reflect_mcp_assignment_changes(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "tool-preview"})
        session_id = create_response.json()["session"]["id"]

        initial_tools_response = await client.get(f"/sessions/{session_id}/tools")
        assign_response = await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )
        tools_with_mcp_response = await client.get(f"/sessions/{session_id}/tools")
        remove_response = await client.delete(
            f"/sessions/{session_id}/mcps/game-service"
        )
        tools_after_remove_response = await client.get(f"/sessions/{session_id}/tools")

    assert initial_tools_response.status_code == 200
    initial_tool_names = {
        tool["name"] for tool in initial_tools_response.json()["tools"]
    }
    assert {
        "load_skill",
        "load_skill_reference",
        "spawn_subagent",
        "wait_for_subagent",
    }.issubset(initial_tool_names)
    assert "game-service_next_step" not in initial_tool_names

    assert assign_response.status_code == 201
    assert tools_with_mcp_response.status_code == 200
    tools_with_mcp_names = {
        tool["name"] for tool in tools_with_mcp_response.json()["tools"]
    }
    assert "game-service_next_step" in tools_with_mcp_names

    assert remove_response.status_code == 204
    assert tools_after_remove_response.status_code == 200
    tools_after_remove_names = {
        tool["name"] for tool in tools_after_remove_response.json()["tools"]
    }
    assert "game-service_next_step" not in tools_after_remove_names
