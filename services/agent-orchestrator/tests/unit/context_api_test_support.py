from __future__ import annotations

from pathlib import Path

from agent_orchestrator.api.tool_catalog import build_preview_builtin_tools
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient, ChatResponse
from agent_orchestrator.integrations.mcp.client import (
    McpToolDefinition,
    StreamableHttpMcpClient,
)
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.builtin_tools import builtin_tools_as_openai
from agent_orchestrator.runtime.player_agents import resolve_seat_identity
from agent_orchestrator.runtime.session_modes import is_orchestrated
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.memory import build_message_history
from agent_orchestrator.runtime.skills import SkillRegistry, enabled_skill_assignments
from agent_orchestrator.runtime.system_prompts import build_system_prompt
from agent_orchestrator.runtime.tokens import (
    estimate_tokens_for_messages,
    estimate_tokens_for_tools,
)
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

from .app_test_support import UNIT_ENABLED_PROVIDER_IDS


class FakeBifrostClient(BifrostClient):
    def __init__(self):
        self.compact_response = "Hero HP: 12/15, Villain HP: 30/60, villain stage 1."

    async def aclose(self) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def list_models(self, provider_id: str):
        return []

    async def get_model_context_length(
        self, provider_id: str, model_name: str
    ) -> int | None:
        return None

    async def chat_completion(self, *args, **kwargs) -> ChatResponse:
        return ChatResponse(
            content=self.compact_response,
            tool_calls=[],
            raw={"usage": {"total_tokens": 42}},
        )


class FakeMcpClient(StreamableHttpMcpClient):
    def __init__(self):
        pass

    async def list_tools(self, server_url, transport, headers=None):
        return [
            McpToolDefinition(
                name="next_step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


async def build_context_test_app(tmp_path: Path, bifrost_client=None):
    database_path = tmp_path / "context_api_test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))

    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    await repository.add_mcp_registry(
        name="game-service",
        transport="streamable-http",
        server_url="http://localhost:4001/mcp/",
        headers_json=None,
        custom=False,
    )

    app = create_app(
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            bifrost_url="http://bifrost",
            bifrost_api_key="dummy",
            SKILL_ROOTS=str(skill_root),
            ENABLED_PROVIDER_IDS=UNIT_ENABLED_PROVIDER_IDS,
        ),
        repository=repository,
        bifrost_client=bifrost_client or FakeBifrostClient(),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=FakeMcpClient(),
        skill_registry=SkillRegistry((skill_root,)),
    )
    return app, engine, repository


async def expected_system_prompt(app, session) -> str:
    """The system prompt a top-level job on this session would be sent.

    The persona catalogue is part of it, so the endpoint's figure has to
    include it too — the worker always builds the prompt with the catalogue in
    place.
    """
    return build_system_prompt(
        app.state.skill_registry,
        enabled_skill_assignments(session.enabled_skills),
        personas=await app.state.repository.list_personas(),
    )


async def expected_request_tools(app, session) -> list[dict]:
    """Every tool definition the model is offered, built-in ones included.

    Composed here rather than by calling `resolve_session_request_tools`, which
    is the function under test: sharing that would put the same call on both
    sides of the assertion and no wrong tool set could fail it. The two halves
    are assembled from the primitives instead, so dropping either one from the
    estimate turns these tests red.
    """
    builtin = build_preview_builtin_tools(
        skill_registry=app.state.skill_registry,
        repository=app.state.repository,
        live_event_bus=app.state.live_event_bus,
        session_id=session.id,
        skill_assignments=enabled_skill_assignments(session.enabled_skills),
        is_master_job=True,
        player_configs=list(getattr(session, "player_configs", []) or []),
        seat_identity=await resolve_seat_identity(
            session, load_session=app.state.repository.get_session
        ),
        session_orchestrated=is_orchestrated(session),
    )
    mcp = await app.state.mcp_tool_catalog.list_session_tools(
        session.enabled_mcps,
        await app.state.repository.list_mcp_registries(),
        ignore_failures=True,
    )
    return builtin_tools_as_openai(
        builtin
    ) + app.state.mcp_tool_catalog.as_openai_tools(mcp)


async def expected_token_breakdown(app, session, replay_messages):
    """The breakdown, assembled and summed independently of the estimator.

    Every component is composed here from primitives rather than from the
    functions under test, so a component dropped from the endpoint's estimate
    fails these tests instead of being mirrored by them.
    """
    system_prompt = await expected_system_prompt(app, session)
    return {
        "system_prompt": estimate_tokens_for_messages(
            [{"role": "system", "content": system_prompt}]
        ),
        "replay": estimate_tokens_for_messages(replay_messages),
        "tools": estimate_tokens_for_tools(await expected_request_tools(app, session)),
    }


async def expected_request_tokens(app, session, replay_messages):
    breakdown = await expected_token_breakdown(app, session, replay_messages)
    return breakdown["system_prompt"] + breakdown["replay"] + breakdown["tools"]


async def make_session_with_model(repo: Repository) -> str:
    session = await repo.create_session("test", {})
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    return session.id


async def make_completed_job(
    repo: Repository, session_id: str, prompt: str = "hi", output: str = "ok"
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.update_job_tokens_used(job.id, 100)
    await repo.mark_job_completed(job.id, output)
    return job.id


async def make_completed_job_with_tool_exchange(
    repo: Repository,
    session_id: str,
    *,
    prompt: str,
    output: str,
    tool_call_id: str,
    tool_name: str,
    result: dict,
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    await repo.append_event(
        job.id,
        session_id,
        "tool_call",
        {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": f"game-service_{tool_name}",
            "tool_name": tool_name,
            "assignment": "game-service",
            "server_url": "http://localhost:4001/mcp/",
            "arguments": {},
        },
    )
    await repo.append_event(
        job.id,
        session_id,
        "tool_result",
        {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": f"game-service_{tool_name}",
            "tool_name": tool_name,
            "assignment": "game-service",
            "server_url": "http://localhost:4001/mcp/",
            "is_error": False,
            "result": result,
        },
    )
    await repo.update_job_tokens_used(job.id, 500)
    await repo.mark_job_completed(job.id, output)
    return job.id


async def build_replay_messages(repo: Repository, session_id: str):
    return await build_message_history(repo, session_id, "")
