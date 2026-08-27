from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
    SESSION_PLAYER_NAME_KEY,
)
from .app_test_support import build_test_app


@pytest.mark.asyncio
async def test_session_lifecycle_supports_lmstudio_provider_and_game_service_mcp(
    tmp_path: Path,
):
    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "smoke"}).json()[
                "session"
            ]["id"]

            model_response = client.put(
                f"/sessions/{session_id}/model-config",
                json={
                    "provider_id": "lmstudio",
                    "model_name": "qwen3.5-0.8b",
                },
            )
            assert model_response.status_code == 200

            mcp_response = client.post(
                f"/sessions/{session_id}/mcps",
                json={
                    "name": "game-service",
                    "server_url": "http://localhost:4001/mcp",
                },
            )
            assert mcp_response.status_code == 201

            tools_response = client.get(f"/sessions/{session_id}/tools")
            assert tools_response.status_code == 200
            tool_names = [tool["name"] for tool in tools_response.json()["tools"]]
            assert "game-service_next_step" in tool_names

            detail_response = client.get(f"/sessions/{session_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()["session"]
            assert detail["model_config"]["provider_id"] == "lmstudio"
            assert detail["model_config"]["model_name"] == "qwen3.5-0.8b"
            assert detail["mcps"][0]["name"] == "game-service"
    finally:
        await engine.dispose()


def test_session_lifecycle_and_assignments(app):
    provider_id = app.state.settings.enabled_provider_ids[0]
    with TestClient(app) as client:
        create_response = client.post("/sessions", json={"name": "demo"})
        assert create_response.status_code == 201
        session_id = create_response.json()["session"]["id"]

        model_response = client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": provider_id, "model_name": "gpt-4o-mini"},
        )
        assert model_response.status_code == 200

        skill_response = client.post(
            f"/sessions/{session_id}/skills",
            json={"skill_name": "demo-skill"},
        )
        assert skill_response.status_code == 201

        mcp_response = client.post(
            f"/sessions/{session_id}/mcps",
            json={
                "name": "game-service",
                "server_url": "http://localhost:4001/mcp",
            },
        )
        assert mcp_response.status_code == 201
        assert mcp_response.json()["mcp"]["server_url"] == "http://localhost:4001/mcp/"

        tools_response = client.get(f"/sessions/{session_id}/tools")
        assert tools_response.status_code == 200
        tool_names = [tool["name"] for tool in tools_response.json()["tools"]]
        assert "load_skill" in tool_names
        assert "load_skill_reference" in tool_names
        assert "spawn_subagent" in tool_names
        assert "wait_for_subagent" in tool_names
        assert "game-service_next_step" in tool_names

        jobs_response = client.get(f"/sessions/{session_id}/jobs")
        assert jobs_response.status_code == 200
        assert jobs_response.json()["jobs"] == []
        assert jobs_response.json()["page"] == {"limit": 50, "offset": 0, "total": 0}

        detail_response = client.get(f"/sessions/{session_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["session"]
        assert detail["model_config"]["provider_id"] == provider_id
        assert detail["skills"][0]["skill_name"] == "demo-skill"
        assert detail["mcps"][0]["name"] == "game-service"

        terminate_response = client.post(f"/sessions/{session_id}/terminate")
        assert terminate_response.status_code == 200
        assert terminate_response.json()["session"]["status"] == "terminated"

        rejected_prompt = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "hello"},
        )
        assert rejected_prompt.status_code == 400


def test_list_sessions_returns_pagination_metadata(app):
    provider_id = app.state.settings.enabled_provider_ids[0]
    with TestClient(app) as client:
        first_session_id = client.post("/sessions", json={"name": "a"}).json()[
            "session"
        ]["id"]
        second_session_id = client.post("/sessions", json={"name": "b"}).json()[
            "session"
        ]["id"]
        client.put(
            f"/sessions/{first_session_id}/model-config",
            json={"provider_id": provider_id, "model_name": "gpt-4o-mini"},
        )
        client.post(
            f"/sessions/{second_session_id}/skills",
            json={"skill_name": "demo-skill"},
        )
        client.post(
            f"/sessions/{second_session_id}/mcps",
            json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
        )
        response = client.get("/sessions", params={"limit": 1, "offset": 1})
    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 1
    assert body["page"] == {"limit": 1, "offset": 1, "total": 2}
    session = body["sessions"][0]
    assert session["model_config"]["provider_id"] == provider_id
    assert session["skills"] == []
    assert len(session["mcps"]) == 1
    assert session["mcps"][0]["name"] == "game-service"
    assert session["mcps"][0]["enabled"] is True
    assert session["recent_job"] is None


def test_list_sessions_includes_dashboard_summary_fields(app):
    provider_id = app.state.settings.enabled_provider_ids[0]
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"][
            "id"
        ]
        client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": provider_id, "model_name": "gpt-4o-mini"},
        )
        client.post(
            f"/sessions/{session_id}/skills",
            json={"skill_name": "demo-skill"},
        )
        client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
        )
        response = client.get("/sessions")

    assert response.status_code == 200
    session = response.json()["sessions"][0]
    assert session["model_config"]["provider_id"] == provider_id
    assert session["skills"][0]["skill_name"] == "demo-skill"
    assert session["mcps"][0]["name"] == "game-service"
    assert session["recent_job"] is None


def test_create_session_accepts_memory_settings(app):
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={
                "name": "memory-aware",
                "multi_turn_memory": False,
                "context_recent_message_limit": 3,
                "context_recent_tool_exchange_limit": 2,
                "metadata": {"source": "unit-test"},
            },
        )

    assert response.status_code == 201
    session = response.json()["session"]
    assert session["multi_turn_memory"] is False
    assert session["context_recent_message_limit"] == 3
    assert session["context_recent_tool_exchange_limit"] == 2
    assert session["metadata"] == {"source": "unit-test"}


def test_public_session_metadata_cannot_claim_a_player_seat(app):
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={
                "name": "untrusted",
                "metadata": {
                    "source": "unit-test",
                    SESSION_PLAYER_ID_KEY: "player1",
                    SESSION_PLAYER_NAME_KEY: "Captain",
                    SESSION_ORCHESTRATOR_ID_KEY: "table",
                },
            },
        )

    assert response.status_code == 201
    session = response.json()["session"]
    assert session["metadata"] == {"source": "unit-test"}

    patched = client.patch(
        f"/sessions/{session['id']}",
        json={
            "metadata": {
                "updated": "yes",
                SESSION_PLAYER_ID_KEY: "player2",
                SESSION_PLAYER_NAME_KEY: "Impostor",
                SESSION_ORCHESTRATOR_ID_KEY: "other-table",
            }
        },
    )
    assert patched.status_code == 200
    assert patched.json()["session"]["metadata"] == {"updated": "yes"}


def test_update_session_persists_name_metadata_and_context_limits(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "before"}).json()[
            "session"
        ]["id"]
        response = client.patch(
            f"/sessions/{session_id}",
            json={
                "name": "after",
                "metadata": {"mode": "patched"},
                "context_recent_message_limit": 6,
                "context_recent_tool_exchange_limit": 1,
            },
        )

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["name"] == "after"
    assert session["metadata"] == {"mode": "patched"}
    assert session["context_recent_message_limit"] == 6
    assert session["context_recent_tool_exchange_limit"] == 1


def test_list_session_assignments_returns_skills_and_mcps(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"][
            "id"
        ]
        client.post(
            f"/sessions/{session_id}/skills",
            json={"skill_name": "demo-skill"},
        )
        client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
        )

        skills_response = client.get(f"/sessions/{session_id}/skills")
        mcps_response = client.get(f"/sessions/{session_id}/mcps")

        assert skills_response.status_code == 200
        skills = skills_response.json()["skills"]
        assert len(skills) == 1
        assert skills[0]["skill_name"] == "demo-skill"
        assert skills[0]["enabled"] is True
        assert "id" in skills[0]
        assert "skill_path" in skills[0]
        assert "created_at" in skills[0]
        assert mcps_response.status_code == 200
        mcps = mcps_response.json()["mcps"]
        assert mcps[0]["name"] == "game-service"
        assert mcps[0]["transport"] == "streamable-http"
        assert mcps[0]["enabled"] is True


def test_rejects_unknown_provider(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["session"]["id"]
        response = client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "bad-provider", "model_name": "x"},
        )
    assert response.status_code == 400


def test_rejects_disabled_provider(app):
    settings = app.state.settings
    # Pick a provider that is supported by the build but not enabled on this
    # app, so the test names no specific vendor. The unit harness pins a partial
    # provider set (see UNIT_ENABLED_PROVIDER_IDS), so one always exists.
    disabled_provider_id = next(
        (
            provider_id
            for provider_id in settings.supported_provider_ids
            if provider_id not in settings.enabled_provider_ids
        ),
        None,
    )
    assert disabled_provider_id is not None, (
        "the unit app must enable only a subset of the supported providers so "
        "this test has a genuinely disabled provider to reject"
    )
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["session"]["id"]
        response = client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": disabled_provider_id, "model_name": "x"},
        )
    assert response.status_code == 400


def test_rejects_unknown_skill(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["session"]["id"]
        response = client.post(
            f"/sessions/{session_id}/skills",
            json={"skill_name": "missing-skill"},
        )
    assert response.status_code == 400


def test_missing_resources_return_404(app):
    with TestClient(app) as client:
        assert client.get("/sessions/missing").status_code == 404
        assert (
            client.patch("/sessions/missing", json={"name": "demo"}).status_code == 404
        )
        assert client.post("/sessions/missing/terminate").status_code == 404
        assert client.get("/sessions/missing/jobs").status_code == 404
        assert (
            client.post("/sessions/missing/prompts", json={"prompt": "hi"}).status_code
            == 404
        )
        assert client.get("/jobs/missing").status_code == 404
        assert client.get("/jobs/missing/status").status_code == 404
        assert client.post("/jobs/missing/cancel").status_code == 404
        assert client.get("/jobs/missing/events").status_code == 404


@pytest.mark.asyncio
async def test_remove_assignments_and_filter_events_with_after(app):
    provider_id = app.state.settings.enabled_provider_ids[0]
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"][
            "id"
        ]
        client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": provider_id, "model_name": "gpt-4o-mini"},
        )
        client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
        )

        job_id = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "hello"},
        ).json()["job"]["id"]

        await app.state.repository.append_event(
            job_id, session_id, "model_output", {"text": "hello"}
        )
        await app.state.repository.append_event(
            job_id, session_id, "completion", {"text": "done"}
        )

        events = client.get(f"/jobs/{job_id}/events").json()["events"]
        assert len(events) >= 2
        later_events = client.get(
            f"/jobs/{job_id}/events",
            params={"after": events[0]["id"]},
        ).json()["events"]
        assert later_events
        assert all(event["id"] > events[0]["id"] for event in later_events)

        client.post(f"/sessions/{session_id}/skills", json={"skill_name": "demo-skill"})
        assert (
            client.delete(f"/sessions/{session_id}/skills/demo-skill").status_code
            == 204
        )
        assert (
            client.delete(f"/sessions/{session_id}/mcps/game-service").status_code
            == 204
        )
        # Disabling a skill is idempotent, so a repeat delete is a no-op rather
        # than an error. MCPs still reject a repeat delete.
        assert (
            client.delete(f"/sessions/{session_id}/skills/demo-skill").status_code
            == 204
        )
        assert (
            client.delete(f"/sessions/{session_id}/mcps/game-service").status_code
            == 404
        )
