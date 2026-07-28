from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agent_orchestrator.integrations.mcp.tools import (
    McpToolCatalog,
    SessionToolDefinition,
)
from agent_orchestrator.runtime.builtin_tools import build_builtin_registry
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.personas import (
    narrow_tool_definitions,
    persona_allowed_tools_from_snapshot,
    session_persona_snapshot,
)
from agent_orchestrator.runtime.skills import SkillRegistry, enabled_skill_assignments
from agent_orchestrator.storage.repository import Repository


def build_preview_builtin_tools(
    *,
    skill_registry: SkillRegistry,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    skill_assignments: list[Any],
    is_master_job: bool,
    player_configs: list[Any] | None = None,
) -> list[Any]:
    preview_job = SimpleNamespace(
        parent_job_id=None if is_master_job else "preview-parent",
        job_type="prompt",
    )
    registry = build_builtin_registry(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session_id,
        job_id="preview",
        skill_assignments=skill_assignments,
        job=preview_job,
        schedule_child_fn=None,
        player_configs=player_configs,
    )
    return registry.list_definitions()


async def list_effective_session_tools(
    *,
    mcp_tool_catalog: McpToolCatalog,
    skill_registry: SkillRegistry,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session: Any,
    is_master_job: bool,
) -> tuple[list[Any], list[SessionToolDefinition]]:
    builtin_tools = build_preview_builtin_tools(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        skill_assignments=enabled_skill_assignments(session.enabled_skills),
        is_master_job=is_master_job,
        player_configs=list(getattr(session, "player_configs", []) or []),
    )
    all_registries = await repository.list_mcp_registries()
    mcp_tools = await mcp_tool_catalog.list_session_tools(
        session.enabled_mcps, all_registries, ignore_failures=True
    )
    # Narrowed by the persona this session was started from, if any, so what a
    # reader is shown is what the job actually had rather than what its MCP
    # servers could have offered.
    mcp_tools = narrow_tool_definitions(
        mcp_tools,
        persona_allowed_tools_from_snapshot(session_persona_snapshot(session)),
    )
    return builtin_tools, mcp_tools
