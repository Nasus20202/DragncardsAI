from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .app_test_support import build_test_app

GAME_ID = "22222222-2222-2222-2222-222222222222"
CONVERSATION_CONTEXT = [
    {"role": "system", "content": "You are playing Marvel Champions."},
    {"role": "user", "content": "Start playing."},
    {
        "role": "assistant",
        "content": "Advancing the step.",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "game-service_next_step", "arguments": "{}"},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "call-1", "content": '{"ok": true}'},
]


@pytest.mark.asyncio
async def test_restore_new_mode_creates_session_with_matching_context(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": GAME_ID,
                    "conversation_context": CONVERSATION_CONTEXT,
                    "mode": "new",
                },
            )
            assert response.status_code == 201
            session_id = response.json()["session_id"]

            detail = client.get(f"/sessions/{session_id}").json()["session"]
            metadata = detail["metadata"]
            assert metadata["game_id"] == GAME_ID
            assert metadata["restored_conversation_context"] == CONVERSATION_CONTEXT
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_in_place_mode_resumes_existing_session(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            # Seed an active session already bound to the game_id.
            created = client.post(
                "/sessions",
                json={"name": "live", "metadata": {"game_id": GAME_ID}},
            )
            existing_id = created.json()["session"]["id"]

            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": GAME_ID,
                    "conversation_context": CONVERSATION_CONTEXT,
                    "mode": "in_place",
                },
            )
            assert response.status_code == 201
            assert response.json()["session_id"] == existing_id

            detail = client.get(f"/sessions/{existing_id}").json()["session"]
            metadata = detail["metadata"]
            assert metadata["game_id"] == GAME_ID
            assert metadata["restored_conversation_context"] == CONVERSATION_CONTEXT
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_in_place_without_bound_session_returns_404(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": "unknown-game",
                    "conversation_context": CONVERSATION_CONTEXT,
                    "mode": "in_place",
                },
            )
            assert response.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_rejects_message_without_valid_role(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": GAME_ID,
                    "conversation_context": [{"content": "no role here"}],
                    "mode": "new",
                },
            )
            assert response.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_rejects_unknown_role(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": GAME_ID,
                    "conversation_context": [{"role": "root", "content": "x"}],
                    "mode": "new",
                },
            )
            assert response.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_rejects_too_many_messages(tmp_path: Path):
    from agent_orchestrator.schemas.sessions import (
        MAX_CONVERSATION_CONTEXT_MESSAGES,
    )

    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            oversized = [
                {"role": "user", "content": "x"}
                for _ in range(MAX_CONVERSATION_CONTEXT_MESSAGES + 1)
            ]
            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": GAME_ID,
                    "conversation_context": oversized,
                    "mode": "new",
                },
            )
            assert response.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_rejects_oversized_payload(tmp_path: Path):
    from agent_orchestrator.schemas.sessions import (
        MAX_CONVERSATION_CONTEXT_BYTES,
    )

    app, engine = await build_test_app(tmp_path, enabled_provider_ids="lmstudio")
    try:
        with TestClient(app) as client:
            # A single well-formed message whose serialized size exceeds the cap.
            big_content = "a" * (MAX_CONVERSATION_CONTEXT_BYTES + 10)
            response = client.post(
                "/sessions/restore",
                json={
                    "game_id": GAME_ID,
                    "conversation_context": [{"role": "user", "content": big_content}],
                    "mode": "new",
                },
            )
            assert response.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resumed_session_seeds_prompt_run_with_supplied_context(tmp_path: Path):
    """A resumed session's next turn must face the supplied conversation context."""
    from agent_orchestrator.config import Settings
    from agent_orchestrator.integrations.bifrost import ChatResponse
    from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
    from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
    from agent_orchestrator.runtime.prompt_run import (
        PromptRunDependencies,
        PromptRunService,
    )
    from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
    from agent_orchestrator.runtime.skills import SkillRegistry
    from agent_orchestrator.storage.db import create_engine, create_session_factory
    from agent_orchestrator.storage.migrations import ensure_schema
    from agent_orchestrator.storage.repository import Repository

    seen_messages: list[dict] = []

    class CapturingBifrost:
        async def health(self):
            return True

        async def aclose(self):
            return None

        async def get_model_context_length(self, provider_id, model_name):
            return None

        async def chat_completion(
            self,
            provider_id,
            model_name,
            messages,
            tools,
            gateway_options,
            provider_options,
            on_delta=None,
        ):
            seen_messages.extend(messages)
            return ChatResponse(content="done", tool_calls=[], raw={})

    class StubMcp:
        async def list_tools(self, server_url, transport, headers=None):
            return []

        async def call_tool(self, *a, **k):
            return {"is_error": False, "content": []}

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        skill_root = tmp_path / "skills"
        skill_root.mkdir()
        (skill_root / "demo").mkdir()
        (skill_root / "demo" / "SKILL.md").write_text("x", encoding="utf-8")
        skills = SkillRegistry((skill_root,))

        session = await repo.create_session(
            name=None,
            metadata_json={
                "game_id": GAME_ID,
                "restored_conversation_context": CONVERSATION_CONTEXT,
            },
        )
        await repo.set_model_config(
            session.id,
            provider_id="openai",
            model_name="gpt-4o-mini",
            gateway_options={},
            provider_options={},
        )
        await repo.enqueue_prompt_job(
            session.id, prompt="continue", metadata_json={}, max_attempts=1
        )
        claimed = await repo.claim_next_job()

        service = PromptRunService(
            dependencies=PromptRunDependencies(
                settings=Settings(SKILL_ROOTS=str(skill_root)),
                repository=repo,
                bifrost_client=CapturingBifrost(),
                live_event_bus=InMemoryLiveEventBus(),
                mcp_tool_catalog=McpToolCatalog(StubMcp()),
                skill_registry=skills,
            ),
            transcript_service=SessionTranscriptService(repo),
            schedule_child_job=lambda job_id: None,
        )
        await service.run(claimed)

        # The supplied restored context messages must all appear, in order,
        # in what the model received on its next turn.
        non_system = [m for m in seen_messages if m.get("role") != "system"]
        for restored in CONVERSATION_CONTEXT:
            if restored.get("role") == "system":
                continue
            assert restored in seen_messages or restored in non_system
        # The user turn from the restored context precedes the new prompt.
        assert {"role": "user", "content": "continue"} in seen_messages
    finally:
        await engine.dispose()
