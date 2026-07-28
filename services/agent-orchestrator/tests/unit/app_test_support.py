from __future__ import annotations

from pathlib import Path

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import (
    BifrostClient,
    BifrostError,
    ChatResponse,
)
from agent_orchestrator.integrations.mcp.client import (
    McpClientError,
    McpToolDefinition,
    StreamableHttpMcpClient,
)
from agent_orchestrator.runtime.app import create_app
from agent_orchestrator.runtime.history_emitter import InMemoryHistoryEventBus
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

# Provider set the unit app is pinned to. Deliberately a fixed subset of the
# supported providers (never the ambient ENABLED_PROVIDER_IDS) so that:
#   * the suite behaves identically whichever providers a developer enables, and
#   * there is always at least one supported-but-disabled provider to reject.
UNIT_ENABLED_PROVIDER_IDS = "openai,gemini"


class FakeBifrostClient(BifrostClient):
    def __init__(self, *, unavailable_provider_ids: set[str] | None = None):
        self.healthy = True
        self.unavailable_provider_ids = unavailable_provider_ids or set()
        self._valkey = None
        self.clear_cache_calls: list[list[str]] = []

    async def aclose(self) -> None:
        return None

    async def health(self) -> bool:
        return self.healthy

    async def clear_model_cache(self, provider_ids: list[str]) -> dict[str, int]:
        self.clear_cache_calls.append(list(provider_ids))
        return {
            "providers": len(provider_ids),
            "keys_cleared": len(provider_ids) * 2 + 1,
        }

    async def list_models(self, provider_id: str):
        if provider_id in self.unavailable_provider_ids:
            raise BifrostError("gateway_error", f"Provider {provider_id} unavailable")
        data = {
            "openai": ["gpt-4o-mini", "gpt-4.1-mini"],
            "gemini": ["gemini-2.0-flash"],
            "lmstudio": ["qwen3.5-0.8b"],
        }
        return [
            type(
                "ModelInfo",
                (),
                {
                    "id": model_id,
                    "name": model_id,
                    "supported_methods": ["chat_completion"],
                },
            )()
            for model_id in data.get(provider_id, [])
        ]

    async def chat_completion(self, *args, **kwargs) -> ChatResponse:
        return ChatResponse(content="done", tool_calls=[], raw={})


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


class FailingMcpClient(FakeMcpClient):
    async def list_tools(self, server_url, transport, headers=None):
        raise McpClientError(f"cannot connect to {server_url}")

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        raise McpClientError(f"cannot connect to {server_url}")


async def build_test_app(
    tmp_path: Path,
    *,
    unavailable_provider_ids: set[str] | None = None,
    bifrost_client: BifrostClient | None = None,
    mcp_client: StreamableHttpMcpClient | None = None,
    enabled_provider_ids: str = UNIT_ENABLED_PROVIDER_IDS,
    list_models_timeout_seconds: float | None = None,
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

    settings_kwargs: dict = {}
    if list_models_timeout_seconds is not None:
        settings_kwargs["BIFROST_LIST_MODELS_TIMEOUT_SECONDS"] = (
            list_models_timeout_seconds
        )

    app = create_app(
        settings=Settings(
            database_url=f"sqlite+aiosqlite:///{database_path}",
            bifrost_url="http://bifrost",
            bifrost_api_key="dummy",
            SKILL_ROOTS=str(skill_root),
            ENABLED_PROVIDER_IDS=enabled_provider_ids,
            **settings_kwargs,
        ),
        repository=repository,
        bifrost_client=bifrost_client
        or FakeBifrostClient(unavailable_provider_ids=unavailable_provider_ids),
        live_event_bus=InMemoryLiveEventBus(),
        mcp_client=mcp_client or FakeMcpClient(),
        skill_registry=SkillRegistry((skill_root,)),
        history_event_bus=InMemoryHistoryEventBus(),
    )
    return app, engine
