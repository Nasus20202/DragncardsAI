from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agent_orchestrator.integrations.mcp.tools import (
    McpToolCatalog,
    SessionToolDefinition,
)
from agent_orchestrator.runtime.builtin_tools import (
    build_builtin_registry,
    builtin_tools_as_openai,
)
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.personas import (
    narrow_tool_definitions,
    persona_allowed_tools_from_snapshot,
    session_persona_snapshot,
)
from agent_orchestrator.runtime.player_agents import SeatIdentity, resolve_seat_identity
from agent_orchestrator.runtime.session_modes import is_orchestrated
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
    seat_identity: SeatIdentity | None = None,
    session_orchestrated: bool = False,
) -> list[Any]:
    """The built-in tools a job on this session would be offered.

    `seat_identity` and `session_orchestrated` gate the seat-only and
    orchestrator-only tools exactly as they do for a real job. Omitting them
    understated an orchestrating session's catalogue by `report_illegal_action`
    and `resolve_illegal_action`, and a seat's by `send_player_message` and
    `list_my_illegal_actions` — which both this preview's readers and the
    context estimate would then have been missing.
    """
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
        seat_identity=seat_identity,
        session_orchestrated=session_orchestrated,
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
        seat_identity=await resolve_seat_identity(
            session, load_session=repository.get_session
        ),
        session_orchestrated=is_orchestrated(session),
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


async def resolve_session_request_tools(
    *,
    mcp_tool_catalog: McpToolCatalog,
    skill_registry: SkillRegistry,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session: Any,
) -> list[dict[str, Any]]:
    """The OpenAI-shaped tool list a top-level job on this session would send.

    This is what the context estimate has to cost, because it is what the
    worker puts in the request: built-in tools as well as MCP ones. Costing the
    MCP half alone understated the tools component by every built-in definition
    the model was offered.

    The worker builds its own registry, because it dispatches through it too,
    and hands that list to the estimate directly. That the two lists agree for
    a top-level job is asserted by a test rather than guaranteed by
    construction.
    """
    builtin_tools, mcp_tools = await list_effective_session_tools(
        mcp_tool_catalog=mcp_tool_catalog,
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session=session,
        is_master_job=True,
    )
    return builtin_tools_as_openai(builtin_tools) + mcp_tool_catalog.as_openai_tools(
        mcp_tools
    )
