from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError, ChatResponse
from agent_orchestrator.integrations.mcp.client import McpClientError, StreamableHttpMcpClient, McpToolDefinition
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.config import Settings
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


class FakeBifrostClient(BifrostClient):
    def __init__(self, *, unavailable_provider_ids: set[str] | None = None):
        self.healthy = True
        self.unavailable_provider_ids = unavailable_provider_ids or set()

    async def aclose(self) -> None:
        return None

    async def health(self) -> bool:
        return self.healthy

    async def list_models(self, provider_id: str):
        if provider_id in self.unavailable_provider_ids:
            raise BifrostError("gateway_error", f"Provider {provider_id} unavailable")
        data = {
            "openai": ["gpt-4o-mini", "gpt-4.1-mini"],
            "gemini": ["gemini-2.0-flash"],
        }
        return [
            type("ModelInfo", (), {"id": model_id, "name": model_id, "supported_methods": ["chat_completion"]})()
            for model_id in data.get(provider_id, [])
        ]

    async def chat_completion(self, *args, **kwargs) -> ChatResponse:
        return ChatResponse(content="done", tool_calls=[], raw={})


class FakeMcpClient(StreamableHttpMcpClient):
    def __init__(self):
        pass

    async def list_tools(self, server_url, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]


class FailingMcpClient(FakeMcpClient):
    async def list_tools(self, server_url, headers=None):
        raise McpClientError(f"cannot connect to {server_url}")


@pytest.fixture
async def app(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        yield app
    finally:
        await engine.dispose()


async def build_test_app(
    tmp_path: Path,
    *,
    unavailable_provider_ids: set[str] | None = None,
    bifrost_client: BifrostClient | None = None,
    mcp_client: StreamableHttpMcpClient | None = None,
):
    database_path = tmp_path / "unit.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    demo = skill_root / "demo-skill"
    demo.mkdir()
    (demo / "SKILL.md").write_text("demo skill", encoding="utf-8")

    app = create_app(
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            bifrost_url="http://bifrost",
            bifrost_api_key="dummy",
            SKILL_ROOTS=str(skill_root),
            ENABLED_PROVIDER_IDS="openai,gemini",
        ),
        repository=repository,
        bifrost_client=bifrost_client or FakeBifrostClient(unavailable_provider_ids=unavailable_provider_ids),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=mcp_client or FakeMcpClient(),
        skill_registry=SkillRegistry((skill_root,)),
    )
    return app, engine


def test_health(app):
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_dependencies(app):
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "bifrost": True, "valkey": True, "worker": True}


def test_list_providers(app):
    with TestClient(app) as client:
        response = client.get("/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    provider_ids = {item["provider_id"] for item in providers}
    assert provider_ids == {"openai", "gemini"}
    providers_by_id = {item["provider_id"]: item for item in providers}
    assert providers_by_id["openai"]["models"] == ["gpt-4o-mini", "gpt-4.1-mini"]
    assert providers_by_id["gemini"]["models"] == ["gemini-2.0-flash"]
    assert providers_by_id["openai"]["available"] is True
    assert providers_by_id["openai"]["error"] is None


@pytest.mark.asyncio
async def test_list_providers_filters_models_to_requested_provider(tmp_path: Path):
    class MixedModelBifrostClient(FakeBifrostClient):
        async def list_models(self, provider_id: str):
            if provider_id == "openai":
                model_ids = ["gpt-4o-mini", "openai/gpt-4.1-mini", "openrouter/google/gemini-2.5-pro"]
            else:
                model_ids = ["gemini/gemini-2.0-flash", "openrouter/openai/gpt-4o-mini", "gpt-4o-mini"]
            return [
                type("ModelInfo", (), {"id": model_id, "name": model_id, "supported_methods": ["chat_completion"]})()
                for model_id in model_ids
            ]

    app, engine = await build_test_app(tmp_path, bifrost_client=MixedModelBifrostClient())
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        assert providers["openai"]["models"] == ["gpt-4o-mini", "openai/gpt-4.1-mini"]
        assert providers["gemini"]["models"] == ["gemini/gemini-2.0-flash"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_providers_marks_unavailable_provider(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, unavailable_provider_ids={"gemini"})
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        assert providers["openai"]["available"] is True
        assert providers["openai"]["error"] is None
        assert providers["gemini"]["available"] is False
        assert providers["gemini"]["models"] == []
        assert "unavailable" in providers["gemini"]["error"].lower()
    finally:
        await engine.dispose()


def test_session_lifecycle_and_assignments(app):
    with TestClient(app) as client:
        create_response = client.post("/sessions", json={"name": "demo"})
        assert create_response.status_code == 201
        session_id = create_response.json()["session"]["id"]

        model_response = client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
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
        assert tools_response.json()["tools"][0]["name"] == "game-service_next_step"

        jobs_response = client.get(f"/sessions/{session_id}/jobs")
        assert jobs_response.status_code == 200
        assert jobs_response.json()["jobs"] == []
        assert jobs_response.json()["page"] == {"limit": 50, "offset": 0, "total": 0}

        available_skills_response = client.get("/skills")
        assert available_skills_response.status_code == 200
        assert available_skills_response.json()["skills"][0]["name"] == "demo-skill"
        assert "content_markdown" in available_skills_response.json()["skills"][0]

        detail_response = client.get(f"/sessions/{session_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["session"]
        assert detail["model_config"]["provider_id"] == "openai"
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
    with TestClient(app) as client:
        first_session_id = client.post("/sessions", json={"name": "a"}).json()["session"]["id"]
        second_session_id = client.post("/sessions", json={"name": "b"}).json()["session"]["id"]
        client.put(
            f"/sessions/{first_session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
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
    assert session["model_config"]["provider_id"] == "openai"
    assert session["skills"] == []
    assert session["mcps"] == []
    assert session["recent_job"] is None


def test_list_sessions_includes_dashboard_summary_fields(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"]["id"]
        client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
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
    assert session["model_config"]["provider_id"] == "openai"
    assert session["skills"][0]["skill_name"] == "demo-skill"
    assert session["mcps"][0]["name"] == "game-service"
    assert session["recent_job"] is None


def test_job_status_endpoint_returns_summary(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"]["id"]
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
            session_id = client.post("/sessions", json={"name": "demo"}).json()["session"]["id"]
            client.put(
                f"/sessions/{session_id}/model-config",
                json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
            )
            client.post(
                f"/sessions/{session_id}/mcps",
                json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
            )
            job_id = client.post(
                f"/sessions/{session_id}/prompts",
                json={"prompt": "hello"},
            ).json()["job"]["id"]

            response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        assert response.json()["job"]["available_tools"] == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_tools_ignores_unreachable_mcp_assignments(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, mcp_client=FailingMcpClient())
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "demo"}).json()["session"]["id"]
            client.post(
                f"/sessions/{session_id}/mcps",
                json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
            )

            response = client.get(f"/sessions/{session_id}/tools")

        assert response.status_code == 200
        assert response.json()["tools"] == []
    finally:
        await engine.dispose()


def test_rejects_unknown_provider(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["session"]["id"]
        response = client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "bad-provider", "model_name": "x"},
        )
    assert response.status_code == 400


def test_rejects_disabled_provider(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={}).json()["session"]["id"]
        response = client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "mistral", "model_name": "mistral-small"},
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
        assert client.patch("/sessions/missing", json={"name": "demo"}).status_code == 404
        assert client.post("/sessions/missing/terminate").status_code == 404
        assert client.get("/sessions/missing/jobs").status_code == 404
        assert client.post("/sessions/missing/prompts", json={"prompt": "hi"}).status_code == 404
        assert client.get("/jobs/missing").status_code == 404
        assert client.get("/jobs/missing/status").status_code == 404
        assert client.post("/jobs/missing/cancel").status_code == 404
        assert client.get("/jobs/missing/events").status_code == 404


@pytest.mark.asyncio
async def test_remove_assignments_and_filter_events_with_after(app):
    with TestClient(app) as client:
        session_id = client.post("/sessions", json={"name": "demo"}).json()["session"]["id"]
        client.put(
            f"/sessions/{session_id}/model-config",
            json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
        )
        client.post(
            f"/sessions/{session_id}/mcps",
            json={"name": "game-service", "server_url": "http://localhost:4001/mcp"},
        )

        job_id = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "hello"},
        ).json()["job"]["id"]

        await app.state.repository.append_event(job_id, session_id, "model_output", {"text": "hello"})
        await app.state.repository.append_event(job_id, session_id, "completion", {"text": "done"})

        events = client.get(f"/jobs/{job_id}/events").json()["events"]
        assert len(events) >= 2
        later_events = client.get(
            f"/jobs/{job_id}/events",
            params={"after": events[0]["id"]},
        ).json()["events"]
        assert later_events
        assert all(event["id"] > events[0]["id"] for event in later_events)

        client.post(f"/sessions/{session_id}/skills", json={"skill_name": "demo-skill"})
        assert client.delete(f"/sessions/{session_id}/skills/demo-skill").status_code == 204
        assert client.delete(f"/sessions/{session_id}/mcps/game-service").status_code == 204
        assert client.delete(f"/sessions/{session_id}/skills/demo-skill").status_code == 404
        assert client.delete(f"/sessions/{session_id}/mcps/game-service").status_code == 404
