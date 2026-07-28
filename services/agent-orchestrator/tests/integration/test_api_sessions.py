from __future__ import annotations

import httpx
import pytest

from .api_test_support import INTEGRATION_MODEL_CONFIG


@pytest.mark.asyncio
async def test_mcp_registry_and_session_enablement_lifecycle(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        create_response = await client.post("/sessions", json={"name": "mcp-test"})
        session_id = create_response.json()["session"]["id"]

        # Initially no additional MCPs registered (game-service is auto-created)
        list_response = await client.get("/mcps")
        assert list_response.status_code == 200
        mcps = list_response.json()["mcps"]
        # game-service is auto-created by default
        assert len(mcps) == 1
        assert mcps[0]["name"] == "game-service"

        # Add another MCP registry
        add_response = await client.post(
            "/mcps",
            json={
                "name": "custom-mcp",
                "transport": "sse",
                "server_url": "http://custom/mcp",
            },
        )
        assert add_response.status_code == 201
        assert add_response.json()["mcp"]["name"] == "custom-mcp"
        assert add_response.json()["mcp"]["transport"] == "sse"

        # List registries
        list_response = await client.get("/mcps")
        assert list_response.status_code == 200
        assert len(list_response.json()["mcps"]) == 2

        # List session MCPs (built-ins enabled by default, custom disabled)
        session_mcps = await client.get(f"/sessions/{session_id}/mcps")
        assert session_mcps.status_code == 200
        mcps = session_mcps.json()["mcps"]
        assert len(mcps) == 2
        game_mcp = next(m for m in mcps if m["name"] == "game-service")
        assert game_mcp["enabled"] is True
        custom_mcp = next(m for m in mcps if m["name"] == "custom-mcp")
        assert custom_mcp["enabled"] is False

        # Enable custom MCP for session
        enable_response = await client.patch(
            f"/sessions/{session_id}/mcps/custom-mcp",
            json={"enabled": True},
        )
        assert enable_response.status_code == 200
        assert enable_response.json()["mcp"]["enabled"] is True

        # Disable MCP for session
        disable_response = await client.patch(
            f"/sessions/{session_id}/mcps/custom-mcp",
            json={"enabled": False},
        )
        assert disable_response.status_code == 200
        assert disable_response.json()["mcp"]["enabled"] is False

        # Delete MCP registry (custom one)
        delete_response = await client.delete("/mcps/custom-mcp")
        assert delete_response.status_code == 204

        # Still have game-service
        list_after = await client.get("/mcps")
        assert len(list_after.json()["mcps"]) == 1

        # Enable non-existent MCP returns 404
        enable_missing = await client.patch(
            f"/sessions/{session_id}/mcps/missing",
            json={"enabled": True},
        )
        assert enable_missing.status_code == 404


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
            json=INTEGRATION_MODEL_CONFIG,
        )
        skill_response = await client.post(
            "/sessions/missing/skills",
            json={"skill_name": "test-skill"},
        )
        mcp_enable_response = await client.patch(
            "/sessions/missing/mcps/game-service",
            json={"enabled": True},
        )

    assert session_response.status_code == 404
    assert update_response.status_code == 404
    assert terminate_response.status_code == 404
    assert model_config_response.status_code == 404
    assert skill_response.status_code == 404
    assert mcp_enable_response.status_code == 404


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
async def test_mcp_registry_rejects_unsupported_transport(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcps",
            json={
                "name": "invalid-transport-mcp",
                "transport": "websocket",
                "server_url": "http://example/mcp",
            },
        )

    assert response.status_code == 422
    assert "transport" in str(response.json()["detail"]).lower()


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
async def test_session_tools_reflect_mcp_enablement_changes(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "tool-preview"})
        session_id = create_response.json()["session"]["id"]

        initial_tools_response = await client.get(f"/sessions/{session_id}/tools")

        # Built-in MCP is available and enabled by default for each session.
        initial_mcps_response = await client.get(f"/sessions/{session_id}/mcps")

        # Register MCP in global registry
        await client.post(
            "/mcps",
            json={
                "name": "game-service",
                "transport": "streamable-http",
                "server_url": "http://game-service/mcp",
            },
        )

        # Enable MCP for session
        await client.patch(
            f"/sessions/{session_id}/mcps/game-service",
            json={"enabled": True},
        )
        tools_with_mcp_response = await client.get(f"/sessions/{session_id}/tools")

        # Disable MCP for session
        await client.patch(
            f"/sessions/{session_id}/mcps/game-service",
            json={"enabled": False},
        )
        tools_after_disable_response = await client.get(f"/sessions/{session_id}/tools")

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
    assert "game-service_next_step" in initial_tool_names

    initial_mcps = {mcp["name"]: mcp for mcp in initial_mcps_response.json()["mcps"]}
    assert initial_mcps["game-service"]["enabled"] is True

    assert tools_with_mcp_response.status_code == 200
    tools_with_mcp_names = {
        tool["name"] for tool in tools_with_mcp_response.json()["tools"]
    }
    assert "game-service_next_step" in tools_with_mcp_names

    assert tools_after_disable_response.status_code == 200
    tools_after_disable_names = {
        tool["name"] for tool in tools_after_disable_response.json()["tools"]
    }
    assert "game-service_next_step" not in tools_after_disable_names
