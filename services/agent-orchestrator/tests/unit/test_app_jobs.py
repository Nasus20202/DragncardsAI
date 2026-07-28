from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .app_test_support import FailingMcpClient, build_test_app


def test_job_status_endpoint_returns_summary(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"][
            "id"
        ]
        client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        job_id = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "hello"},
        ).json()["job"]["id"]
        response = client.get(f"/jobs/{job_id}/status")
    assert response.status_code == 200
    assert response.json()["job"]["id"] == job_id


@pytest.mark.asyncio
async def test_job_detail_ignores_unreachable_mcp_assignments(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, mcp_client=FailingMcpClient())
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "demo"}).json()[
                "session"
            ]["id"]
            client.put(
                f"/sessions/{session_id}/model-config",
                json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
            )
            client.post(
                f"/sessions/{session_id}/mcps",
                json={
                    "name": "game-service",
                    "server_url": "http://localhost:4001/mcp",
                },
            )
            job_id = client.post(
                f"/sessions/{session_id}/prompts",
                json={"prompt": "hello"},
            ).json()["job"]["id"]

            response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        tool_names = [
            tool["name"] for tool in response.json()["job"]["available_tools"]
        ]
        assert "load_skill" in tool_names
        assert "load_skill_reference" in tool_names
        assert "spawn_subagent" in tool_names
        assert "wait_for_subagent" in tool_names
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_tools_ignores_unreachable_mcp_assignments(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, mcp_client=FailingMcpClient())
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "demo"}).json()[
                "session"
            ]["id"]
            client.post(
                f"/sessions/{session_id}/mcps",
                json={
                    "name": "game-service",
                    "server_url": "http://localhost:4001/mcp",
                },
            )

            response = client.get(f"/sessions/{session_id}/tools")

        assert response.status_code == 200
        tool_names = [tool["name"] for tool in response.json()["tools"]]
        assert tool_names == [
            "load_skill",
            "load_skill_reference",
            "spawn_subagent",
            "wait_for_subagent",
            "ask_user",
        ]
    finally:
        await engine.dispose()


def test_cancel_job_requests_cancellation_and_records_event(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"][
            "id"
        ]
        job_id = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "hello"},
        ).json()["job"]["id"]

        cancel_response = client.post(f"/jobs/{job_id}/cancel")
        events_response = client.get(
            f"/jobs/{job_id}/events",
            params={"event_type": "cancellation"},
        )

    assert cancel_response.status_code == 200
    job = cancel_response.json()["job"]
    assert job["status"] in {"queued", "running", "cancelled"}
    assert job["cancellation_requested_at"] is not None
    assert job["latest_event_type"] == "cancellation"
    events = events_response.json()["events"]
    assert len(events) == 1
    assert events[0]["payload"] == {"requested": True}
