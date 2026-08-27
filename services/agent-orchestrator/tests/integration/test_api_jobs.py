from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from .api_test_support import INTEGRATION_MODEL_CONFIG


@pytest.mark.asyncio
async def test_prompt_run_completes_background_job(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]

        sessions_response = await client.get(
            "/sessions", params={"limit": 10, "offset": 0}
        )
        assert sessions_response.status_code == 200
        assert sessions_response.json()["page"]["total"] >= 1

        await client.put(
            f"/sessions/{session_id}/model-config",
            json=INTEGRATION_MODEL_CONFIG,
        )
        await client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"}
        )
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
async def test_truncated_turn_continues_through_http_worker(truncating_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=truncating_app), base_url="http://test"
    ) as client:
        session_id = (
            await client.post("/sessions", json={"name": "continuation"})
        ).json()["session"]["id"]
        model_response = await client.put(
            f"/sessions/{session_id}/model-config",
            json=INTEGRATION_MODEL_CONFIG,
        )
        assert model_response.status_code == 200

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "finish the response"},
        )
        assert prompt_response.status_code == 202
        job_id = prompt_response.json()["job"]["id"]

        for _ in range(80):
            job_response = await client.get(f"/jobs/{job_id}")
            if job_response.json()["job"]["status"] == "completed":
                break
            await asyncio.sleep(0.05)

        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["result_text"] == "SEGMENT_ASEGMENT_B"

        events_response = await client.get(f"/jobs/{job_id}/events")
        assert events_response.status_code == 200
        events = events_response.json()["events"]
        event_types = [event["event_type"] for event in events]
        marker = event_types.index("turn_continued")
        assert event_types[marker - 1] == "model_output"
        assert event_types[marker + 1] == "model_output"
        assert event_types[-1] == "completion"
        assert event_types.count("turn_continued") == 1

        marker_event = events[marker]
        assert marker_event["payload"] == {
            "reason": "output_token_limit",
            "finish_reason": "length",
            "continuation": 1,
            "max_continuations": 3,
        }

@pytest.mark.asyncio
async def test_event_stream_replays_and_resumes(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json=INTEGRATION_MODEL_CONFIG,
        )
        await client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"}
        )
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
        assert any(event["event_type"] == "completion" for event in events)

        resume_cursor = ids[0]
        async with client.stream(
            "GET",
            f"/jobs/{job_id}/events/stream",
            params={"after": resume_cursor},
        ) as resumed_response:
            assert resumed_response.status_code == 200
            resumed_lines = [
                line async for line in resumed_response.aiter_lines() if line
            ]

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


@pytest.mark.asyncio
async def test_cancel_job_records_cancellation_event(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]

        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "cancel me"},
        )
        job_id = prompt_response.json()["job"]["id"]

        cancel_response = await client.post(f"/jobs/{job_id}/cancel")
        cancellation_events_response = await client.get(
            f"/jobs/{job_id}/events",
            params={"event_type": "cancellation"},
        )

    assert cancel_response.status_code == 200
    cancelled_job = cancel_response.json()["job"]
    assert cancelled_job["status"] == "cancelled"
    assert cancelled_job["cancellation_requested_at"] is not None
    events = cancellation_events_response.json()["events"]
    assert len(events) == 1
    assert events[0]["payload"] == {"requested": True}


@pytest.mark.asyncio
async def test_event_filter_returns_empty_list_for_unknown_type(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]
        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "hello"},
        )
        job_id = prompt_response.json()["job"]["id"]

        response = await client.get(
            f"/jobs/{job_id}/events",
            params={"event_type": "does-not-exist"},
        )

    assert response.status_code == 200
    assert response.json() == {"events": []}


@pytest.mark.asyncio
async def test_submit_prompt_rejects_terminated_session(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]

        terminate_response = await client.post(f"/sessions/{session_id}/terminate")
        prompt_response = await client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "should fail"},
        )

    assert terminate_response.status_code == 200
    assert prompt_response.status_code == 400
    assert (
        prompt_response.json()["detail"] == "Terminated sessions cannot accept prompts"
    )


@pytest.mark.asyncio
async def test_event_filter_with_after_cursor_returns_later_matching_events_only(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_response = await client.post("/sessions", json={"name": "demo"})
        session_id = create_response.json()["session"]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config",
            json=INTEGRATION_MODEL_CONFIG,
        )
        await client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"}
        )
        await client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://game-service/mcp"},
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

        all_events_response = await client.get(f"/jobs/{job_id}/events")
        all_events = all_events_response.json()["events"]
        first_tool_call = next(
            event for event in all_events if event["event_type"] == "tool_call"
        )

        filtered_response = await client.get(
            f"/jobs/{job_id}/events",
            params={"event_type": "completion", "after": first_tool_call["id"]},
        )

    assert filtered_response.status_code == 200
    filtered_events = filtered_response.json()["events"]
    assert len(filtered_events) == 1
    assert filtered_events[0]["event_type"] == "completion"
    assert filtered_events[0]["id"] > first_tool_call["id"]


@pytest.mark.asyncio
async def test_event_stream_answers_200_when_the_live_bus_is_unreachable(
    unreachable_live_bus_app,
):
    """DRA-42, end to end over HTTP: what the browser actually got was a 500.

    The unit pins drive `stream()` directly, which cannot show this. The reporter's
    failure was a *response* dying — the exception escaped the async generator into
    Starlette's `stream_response`, so the proxy logged `failed to pipe response` and
    returned `GET .../events/stream 500 in 41s`. This exercises the real ASGI path
    with every live-bus operation failing, and asserts the whole run still works:
    the request is 200, the transcript arrives from PostgreSQL, and the job
    completes.
    """
    app = unreachable_live_bus_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session_id = (await client.post("/sessions", json={"name": "demo"})).json()[
            "session"
        ]["id"]
        await client.put(
            f"/sessions/{session_id}/model-config", json=INTEGRATION_MODEL_CONFIG
        )
        await client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "test-skill"}
        )
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

    events = [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line.startswith("data: ")
    ]
    types = {event["event_type"] for event in events}
    # Every one of these reached the browser from `job_events`, with the live bus
    # refusing every command for the whole run.
    assert "tool_call" in types
    assert "completion" in types
    assert "failure" not in types

    # The stream closes on the terminal *event*, which `complete_job` appends
    # before it marks the job, so poll for the status rather than assuming the
    # two land together.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(50):
            job = (await client.get(f"/jobs/{job_id}")).json()["job"]
            if job["status"] != "running":
                break
            await asyncio.sleep(0.05)
    assert job["status"] == "completed"
