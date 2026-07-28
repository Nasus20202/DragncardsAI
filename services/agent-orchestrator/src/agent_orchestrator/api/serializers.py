from __future__ import annotations

from types import SimpleNamespace

from agent_orchestrator.schemas.jobs import (
    JobDetail,
    JobEventResponse,
    JobSummary,
    SessionToolResponse,
)
from agent_orchestrator.runtime.player_agents import unfold_reasoning
from agent_orchestrator.runtime.skills import enabled_skill_assignments
from agent_orchestrator.schemas.players import PlayerConfigResponse
from agent_orchestrator.schemas.sessions import (
    McpAssignmentResponse,
    McpRegistryResponse,
    ModelConfigResponse,
    SessionDetail,
    SessionSummary,
    SkillAssignmentResponse,
)


def serialize_session_summary(item) -> SessionSummary:
    recent_jobs = sorted(item.jobs, key=lambda job: job.created_at, reverse=True)
    return SessionSummary(
        id=item.id,
        name=item.name,
        status=item.status,
        multi_turn_memory=item.multi_turn_memory,
        context_recent_message_limit=item.context_recent_message_limit,
        context_recent_tool_exchange_limit=item.context_recent_tool_exchange_limit,
        metadata=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
        terminated_at=item.terminated_at,
        session_model_config=(
            None
            if item.model_config is None
            else serialize_model_config(item.model_config)
        ),
        skills=[
            serialize_session_enabled_skill(skill)
            for skill in enabled_skill_assignments(item.enabled_skills)
        ],
        mcps=[serialize_mcp_assignment(em) for em in item.enabled_mcps],
        players=[serialize_player_config(config) for config in item.player_configs],
        recent_job=None if not recent_jobs else serialize_job(recent_jobs[0]),
    )


def serialize_player_config(item) -> PlayerConfigResponse:
    return PlayerConfigResponse(
        player_id=item.player_id,
        display_name=item.display_name,
        provider_id=item.provider_id,
        model_name=item.model_name,
        reasoning=unfold_reasoning(item.gateway_options),
        skills=item.skills_json,
        gateway_options=item.gateway_options or {},
        provider_options=item.provider_options or {},
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def serialize_model_config(item) -> ModelConfigResponse:
    return ModelConfigResponse(
        provider_id=item.provider_id,
        model_name=item.model_name,
        gateway_options=item.gateway_options,
        provider_options=item.provider_options,
        updated_at=item.updated_at,
    )


def serialize_session_enabled_skill(item) -> SkillAssignmentResponse:
    return SkillAssignmentResponse(
        id=f"{item.session_id}:{item.skill_name}",
        skill_name=item.skill_name,
        skill_path=item.skill.skill_path if item.skill else "",
        created_at=item.created_at,
    )


def serialize_mcp_registry(item) -> McpRegistryResponse:
    return McpRegistryResponse(
        name=item.name,
        transport=item.transport,
        server_url=item.server_url,
        headers=item.headers_json,
        custom=item.custom,
        created_at=item.created_at,
    )


def serialize_mcp_assignment(item) -> McpAssignmentResponse:
    # SessionEnabledMcp has mcp_name and relationship to McpRegistry via item.mcp
    if hasattr(item, "mcp") and item.mcp is not None:
        return McpAssignmentResponse(
            name=item.mcp_name,
            transport=item.mcp.transport,
            server_url=item.mcp.server_url,
            headers=item.mcp.headers_json,
            enabled=item.enabled,
            custom=item.mcp.custom,
        )
    # Fallback for other types
    return McpAssignmentResponse(
        name=item.mcp_name if hasattr(item, "mcp_name") else item.name,
        transport=getattr(item, "transport", "streamable-http"),
        server_url=getattr(item, "server_url", ""),
        headers=getattr(item, "headers_json", getattr(item, "headers", {})),
        enabled=item.enabled if hasattr(item, "enabled") else True,
        custom=getattr(item, "custom", False),
    )


def serialize_job(item) -> JobSummary:
    latest_event = (
        max(item.events, key=lambda event: event.id)
        if getattr(item, "events", None)
        else None
    )
    return JobSummary(
        id=item.id,
        prompt=item.prompt,
        metadata=item.metadata_json,
        status=item.status,
        attempts=item.attempts,
        max_attempts=item.max_attempts,
        error_code=item.error_code,
        error_message=item.error_message,
        result_text=item.result_text,
        cancellation_requested_at=item.cancellation_requested_at,
        created_at=item.created_at,
        started_at=item.started_at,
        completed_at=item.completed_at,
        latest_event_id=None if latest_event is None else str(latest_event.id),
        latest_event_type=None if latest_event is None else latest_event.event_type,
    )


def serialize_event(item) -> JobEventResponse:
    return JobEventResponse(
        id=str(item.id),
        event_type=item.event_type,
        payload=item.payload_json,
        created_at=item.created_at,
    )


def serialize_tool_definition(item) -> SessionToolResponse:
    return SessionToolResponse(
        name=item.exposed_name,
        assignment_name=item.assignment_name,
        transport=item.transport,
        server_url=item.server_url,
        actual_name=item.actual_name,
        description=item.description,
        parameters=item.parameters,
    )


def serialize_builtin_tool_definition(item) -> SessionToolResponse:
    return SessionToolResponse(
        name=item.name,
        assignment_name="builtin",
        transport="builtin",
        server_url="builtin://local",
        actual_name=item.name,
        description=item.description,
        parameters=item.parameters,
    )


def serialize_session_tool(item) -> SessionToolResponse:
    if isinstance(item, SessionToolResponse):
        return item
    if hasattr(item, "exposed_name"):
        return serialize_tool_definition(item)
    return serialize_builtin_tool_definition(item)


def serialize_session_detail(item) -> SessionDetail:
    recent_jobs = sorted(item.jobs, key=lambda job: job.created_at, reverse=True)[:5]
    summary = serialize_session_summary(item)
    return SessionDetail(
        id=summary.id,
        name=summary.name,
        status=summary.status,
        metadata=summary.metadata,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        terminated_at=summary.terminated_at,
        multi_turn_memory=summary.multi_turn_memory,
        context_recent_message_limit=summary.context_recent_message_limit,
        context_recent_tool_exchange_limit=summary.context_recent_tool_exchange_limit,
        session_model_config=summary.session_model_config,
        skills=summary.skills,
        mcps=summary.mcps,
        players=summary.players,
        recent_job=summary.recent_job,
        recent_jobs=[serialize_job(job) for job in recent_jobs],
    )


def serialize_job_detail(item, events, available_tools) -> JobDetail:
    return JobDetail(
        **serialize_job(item).model_dump(),
        outputs=[output.content for output in item.outputs],
        events=[serialize_event(event) for event in events],
        available_tools=[serialize_session_tool(tool) for tool in available_tools],
    )
