from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from .api_test_support import (
    GAME_SERVICE_HTTP_URL,
    GAME_SERVICE_MCP_URL,
    require_live_game_service,
)


@pytest.mark.asyncio
async def test_prompt_run_uses_real_game_service_mcp(real_mcp_app):
    await require_live_game_service()

    created_game_session_id = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=real_mcp_app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "live-mcp-demo"})
        session_id = create_response.json()["session"]["id"]

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": GAME_SERVICE_MCP_URL},
        )

        tools_response = await client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        tool_names = {tool["name"] for tool in tools_response.json()["tools"]}
        assert "game-service_create_game" in tool_names
        assert "game-service_next_step" in tool_names

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "Create a game and advance it by one step"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(120):
            job_response = await client.get(f"/jobs/{job_id}")
            if job_response.json()["job"]["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.1)

        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "Advanced the game"

        tool_call_events = [
            event for event in job["events"] if event["event_type"] == "tool_call"
        ]
        tool_result_events = [
            event for event in job["events"] if event["event_type"] == "tool_result"
        ]
        assert len(tool_call_events) == 2
        assert len(tool_result_events) == 2
        assert {event["payload"]["tool_name"] for event in tool_call_events} == {
            "create_game",
            "next_step",
        }
        assert all(
            event["payload"]["server_url"] == GAME_SERVICE_MCP_URL
            for event in tool_call_events
        )

        create_game_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "create_game"
        )
        create_game_payload = json.loads(
            create_game_result["payload"]["result"]["content"][0]["text"]
        )
        created_game_session_id = create_game_payload["session"]["session_id"]

        next_step_result = next(
            event
            for event in tool_result_events
            if event["payload"]["tool_name"] == "next_step"
        )
        next_step_payload = json.loads(
            next_step_result["payload"]["result"]["content"][0]["text"]
        )
        assert next_step_payload["session_id"] == created_game_session_id
        if "success" in next_step_payload:
            assert next_step_payload["success"] is True

    try:
        async with httpx.AsyncClient(timeout=5.0) as live_client:
            games_response = await live_client.get(f"{GAME_SERVICE_HTTP_URL}/games")
            assert games_response.status_code == 200
            ids = [item["session_id"] for item in games_response.json()["sessions"]]
            assert created_game_session_id in ids
    finally:
        if created_game_session_id is not None:
            async with httpx.AsyncClient(timeout=5.0) as live_client:
                await live_client.delete(
                    f"{GAME_SERVICE_HTTP_URL}/games/{created_game_session_id}"
                )
