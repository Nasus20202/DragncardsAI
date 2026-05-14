from __future__ import annotations

import asyncio
import json

import httpx
import pytest


@pytest.mark.asyncio
async def test_prompt_run_completes_background_job(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]

        sessions_response = await client.get("/sessions", params={"limit": 10, "offset": 0})
        assert sessions_response.status_code == 200
        assert sessions_response.json()["page"]["total"] >= 1

        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"})
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        tools_response = await client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        tools = tools_response.json()["tools"]
        tool_names = [tool["name"] for tool in tools]
        assert "load_skill" in tool_names
        assert "load_skill_reference" in tool_names
        assert "spawn_subagent" in tool_names
        assert "wait_for_subagent" in tool_names
        game_service_tool = next(
            tool for tool in tools if tool["name"] == "game-service_next_step"
        )
        assert game_service_tool["server_url"] == "http://game-service/mcp/"

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "take the next step"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(40):
            job_response = await client.get(f"/jobs/{job_id}")
            if job_response.json()["job"]["status"] == "completed":
                break
            await asyncio.sleep(0.05)
        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "All set"
        available_tool_names = [tool["name"] for tool in job["available_tools"]]
        assert "load_skill" in available_tool_names
        assert "load_skill_reference" in available_tool_names
        assert "spawn_subagent" in available_tool_names
        assert "wait_for_subagent" in available_tool_names
        assert "game-service_next_step" in available_tool_names
        assert job["latest_event_type"] == "completion"
        assert any(event["event_type"] == "tool_result" for event in job["events"])
        assert not any(
            event["event_type"] == "model_output" and event["payload"].get("stream")
            for event in job["events"]
        )
        tool_call_event = next(
            event for event in job["events"] if event["event_type"] == "tool_call"
        )
        assert tool_call_event["payload"]["server_url"] == "http://game-service/mcp/"

        session_jobs_response = await client.get(f"/sessions/{session_id}/jobs")
        assert session_jobs_response.status_code == 200
        assert session_jobs_response.json()["jobs"][0]["id"] == job_id
        assert session_jobs_response.json()["page"]["total"] == 1

        filtered_jobs_response = await client.get(
            f"/sessions/{session_id}/jobs",
            params={"status": "completed", "limit": 10, "offset": 0},
        )
        assert filtered_jobs_response.status_code == 200
        assert filtered_jobs_response.json()["jobs"][0]["status"] == "completed"

        status_response = await client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["job"]["status"] == "completed"

        filtered_events_response = await client.get(
            f"/jobs/{job_id}/events",
            params={"event_type": "tool_call"},
        )
        assert filtered_events_response.status_code == 200
        filtered_events = filtered_events_response.json()["events"]
        assert len(filtered_events) == 1
        assert filtered_events[0]["event_type"] == "tool_call"


@pytest.mark.asyncio
async def test_event_stream_replays_and_resumes(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        await client.post(f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"})
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
        )

        job_id = (
            await client.post(f"/sessions/{session_id}/prompts", json={"prompt": "go"})
        ).json()["job"]["id"]

        async with client.stream("GET", f"/jobs/{job_id}/events/stream") as response:
            assert response.status_code == 200
            lines = [line async for line in response.aiter_lines() if line]

        ids = [line.removeprefix("id: ") for line in lines if line.startswith("id: ")]
        events = [
            json.loads(line.removeprefix("data: "))
            for line in lines
            if line.startswith("data: ")
        ]
        assert any(
            event["event_type"] == "model_output" and event["payload"].get("stream")
            for event in events
        )
        assert any(event["event_type"] == "tool_call" for event in events)
        assert events[-1]["event_type"] == "completion"

        resume_cursor = ids[0]
        async with client.stream(
            "GET",
            f"/jobs/{job_id}/events/stream",
            params={"after": resume_cursor},
        ) as resumed_response:
            assert resumed_response.status_code == 200
            resumed_lines = [line async for line in resumed_response.aiter_lines() if line]

        resumed_ids = [
            line.removeprefix("id: ")
            for line in resumed_lines
            if line.startswith("id: ")
        ]
        resumed_events = [
            json.loads(line.removeprefix("data: "))
            for line in resumed_lines
            if line.startswith("data: ")
        ]
        assert resumed_ids
        assert all(event_id > resume_cursor for event_id in resumed_ids)
        assert any(event["event_type"] == "completion" for event in resumed_events)
