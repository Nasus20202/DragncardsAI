from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agent_orchestrator.api.deps import (
    get_live_event_bus,
    get_mcp_tool_catalog,
    get_repository,
    get_settings,
    get_skill_registry,
    require_session,
)
from agent_orchestrator.api.tool_catalog import list_effective_session_tools
from agent_orchestrator.api.serializers import (
    serialize_builtin_tool_definition,
    serialize_job,
    serialize_mcp_assignment,
    serialize_mcp_registry,
    serialize_model_config,
    serialize_session_detail,
    serialize_session_enabled_skill,
    serialize_session_summary,
    serialize_tool_definition,
)
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.mcp.tools import (
    McpToolCatalog,
)
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.common import PageInfo
from agent_orchestrator.schemas.jobs import SessionJobsResponse, SessionToolResponse
from agent_orchestrator.schemas.sessions import (
    McpAssignmentResponse,
    McpRegistryRequest,
    McpRegistryResponse,
    ModelConfigRequest,
    ModelConfigResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
    SessionMcpEnableRequest,
    SessionRestoreRequest,
    SessionRestoreResponse,
    SessionToolsResponse,
    SessionUpdateRequest,
    SkillAssignmentRequest,
)
from agent_orchestrator.runtime.history_emitter import (
    SESSION_GAME_ID_KEY,
    SESSION_RESTORED_CONTEXT_KEY,
)
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["sessions"])


@router.get("/sessions", operation_id="list_sessions")
async def list_sessions(
    repo: Repository = Depends(get_repository),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SessionListResponse:
    sessions, total = await repo.list_sessions(
        status=status, limit=limit, offset=offset
    )
    return SessionListResponse(
        sessions=[serialize_session_summary(item) for item in sessions],
        page=PageInfo(limit=limit, offset=offset, total=total),
    )


async def _require_known_persona(repo: Repository, name: str | None) -> None:
    """Reject a default subagent persona that does not exist.

    Checked when the session is written rather than at spawn time, so a mistyped
    persona is reported to whoever typed it instead of the session quietly
    spawning plain subagents until someone reads a transcript.
    """
    if name is None:
        return
    if await repo.get_persona(name) is None:
        raise HTTPException(status_code=400, detail=f"Unknown persona: {name}")


@router.post("/sessions", status_code=201, operation_id="create_session")
async def create_session(
    body: SessionCreateRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, SessionDetail]:
    await _require_known_persona(repo, body.default_subagent_persona)
    item = await repo.create_session(
        body.name,
        body.metadata,
        multi_turn_memory=body.multi_turn_memory,
        session_mode=body.session_mode,
        context_recent_message_limit=body.context_recent_message_limit,
        context_recent_tool_exchange_limit=body.context_recent_tool_exchange_limit,
        default_subagent_persona=body.default_subagent_persona,
    )
    return {"session": serialize_session_detail(item)}


@router.post("/sessions/restore", status_code=201, operation_id="restore_session")
async def restore_session(
    body: SessionRestoreRequest,
    repo: Repository = Depends(get_repository),
) -> SessionRestoreResponse:
    """Create or resume an agent session seeded with a supplied conversation context.

    - ``mode="new"`` creates a fresh branchable session bound to ``game_id``.
    - ``mode="in_place"`` resumes the existing active session bound to ``game_id``,
      replacing its conversation context with the supplied one.

    The resulting session's conversation context matches the supplied context so
    the agent can continue from an identical decision situation.
    """
    restored_context = list(body.conversation_context)
    if body.mode == "in_place":
        existing = await repo.get_active_session_by_game_id(body.game_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail="No active session bound to the supplied game_id",
            )
        metadata = dict(existing.metadata_json or {})
        metadata[SESSION_GAME_ID_KEY] = body.game_id
        metadata[SESSION_RESTORED_CONTEXT_KEY] = restored_context
        updated = await repo.update_session(existing.id, metadata_json=metadata)
        if updated is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionRestoreResponse(session_id=updated.id)

    item = await repo.create_session(
        name=None,
        metadata_json={
            SESSION_GAME_ID_KEY: body.game_id,
            SESSION_RESTORED_CONTEXT_KEY: restored_context,
        },
    )
    return SessionRestoreResponse(session_id=item.id)


@router.get("/sessions/{session_id}/jobs", operation_id="list_session_jobs")
async def list_session_jobs(
    session_id: str,
    repo: Repository = Depends(get_repository),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    item=Depends(require_session),
) -> SessionJobsResponse:
    del item
    jobs, total = await repo.list_session_jobs(
        session_id, status=status, limit=limit, offset=offset
    )
    return SessionJobsResponse(
        jobs=[serialize_job(job) for job in jobs],
        page=PageInfo(limit=limit, offset=offset, total=total),
    )


@router.get("/sessions/{session_id}", operation_id="get_session")
async def get_session(item=Depends(require_session)) -> dict[str, SessionDetail]:
    return {"session": serialize_session_detail(item)}


@router.patch("/sessions/{session_id}", operation_id="update_session")
async def update_session(
    session_id: str,
    body: SessionUpdateRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, SessionDetail]:
    changes = body.model_dump(exclude_unset=True)
    if "metadata" in changes:
        changes["metadata_json"] = changes.pop("metadata")
    if "default_subagent_persona" in changes:
        await _require_known_persona(repo, changes["default_subagent_persona"])
    # The mode is applied through its own repository call because it is the one
    # session field with a precondition: it is frozen once the session has run a
    # job. Applying it first means a refused mode change leaves nothing else
    # half-written.
    requested_mode = changes.pop("session_mode", None)
    if requested_mode is not None:
        moved, refusal = await repo.update_session_mode(
            session_id, session_mode=requested_mode
        )
        if refusal is not None:
            raise HTTPException(status_code=409, detail=refusal)
        if moved is None:
            raise HTTPException(status_code=404, detail="Session not found")
    if not changes:
        item = await repo.get_session(session_id)
    else:
        item = await repo.update_session(session_id, **changes)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": serialize_session_detail(item)}


@router.delete("/sessions/{session_id}", status_code=204, operation_id="delete_session")
async def delete_session(
    session_id: str,
    repo: Repository = Depends(get_repository),
    live_event_bus: LiveEventBus = Depends(get_live_event_bus),
) -> None:
    """Permanently remove a session and everything recorded under it.

    Terminate-then-delete: cancellation is requested for any queued or running
    job first, so a worker mid-run observes the cancellation flag rather than
    discovering that its rows vanished, and only then are the session, its model
    config, enabled skills, MCP assignments, player configs, jobs, transcript
    events and compaction records deleted.
    """
    for status in ("queued", "running"):
        jobs, _ = await repo.list_session_jobs(session_id, status=status, limit=200)
        for job in jobs:
            _, appended = await repo.request_cancel(job.id)
            # Announce each terminal `cancellation` on the bus for the same
            # reason the cancel endpoint does: a client still streaming one of
            # these jobs otherwise waits out the stream's idle interval before
            # noticing, and here the rows it would eventually have polled are
            # about to be deleted underneath it.
            for record in appended:
                await live_event_bus.publish(
                    record.job_id,
                    "cancellation",
                    {"requested": True},
                    durable_event_id=record.event_id,
                )

    # A seat's session is a separate session row, so deleting the orchestrating
    # session does not cascade into it. Collect the seats before the delete removes
    # their configuration rows, then delete each seat's own session too — otherwise
    # deleting a game would leave its players behind with nothing pointing at them.
    seat_session_ids = [
        config.agent_session_id
        for config in await repo.list_player_configs(session_id)
        if config.agent_session_id
    ]
    deleted = await repo.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    for seat_session_id in seat_session_ids:
        await repo.delete_session(seat_session_id)


@router.post("/sessions/{session_id}/terminate", operation_id="terminate_session")
async def terminate_session(
    session_id: str,
    repo: Repository = Depends(get_repository),
) -> dict[str, SessionDetail]:
    item = await repo.terminate_session(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    # A seat's session outlives its individual jobs, so terminating the
    # orchestrating session is what ends the table. Nothing is left running.
    for config in await repo.list_player_configs(session_id):
        if config.agent_session_id:
            await repo.terminate_session(config.agent_session_id)
    return {"session": serialize_session_detail(item)}


@router.put(
    "/sessions/{session_id}/model-config", operation_id="set_session_model_config"
)
async def set_model_config(
    session_id: str,
    body: ModelConfigRequest,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict[str, ModelConfigResponse]:
    if body.provider_id not in settings.enabled_provider_ids:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    item = await repo.set_model_config(
        session_id,
        provider_id=body.provider_id,
        model_name=body.model_name,
        gateway_options=body.gateway_options,
        provider_options=body.provider_options,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"model_config": serialize_model_config(item)}


# Global Skill Registry endpoints
async def _register_on_disk_skill(
    repo: Repository,
    registry: SkillRegistry,
    skill_name: str,
    *,
    metadata_json: dict[str, Any] | None = None,
) -> Any:
    """
    Upsert the registry row for an on-disk skill and return the stored row.

    Enabling a skill for a session requires a `skill_registries` row, so every
    route that enables one registers it first. Skills are discovered from the
    skill roots, which can gain a skill after boot, so the sync at startup is
    not on its own enough to guarantee the row exists.
    """
    definition = registry.resolve(skill_name)
    if definition is None:
        raise HTTPException(status_code=400, detail="Unknown skill")
    return await repo.add_skill_registry(
        name=skill_name,
        skill_path=str(definition.path),
        description=definition.description,
        metadata_json=(
            dict(definition.metadata) if metadata_json is None else metadata_json
        ),
    )


@router.post("/skills", status_code=201, operation_id="register_skill")
async def add_skill_registry(
    body: dict[str, Any],
    repo: Repository = Depends(get_repository),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, Any]:
    skill_name = body.get("name")
    if not skill_name:
        raise HTTPException(status_code=400, detail="name is required")
    item = await _register_on_disk_skill(
        repo, registry, skill_name, metadata_json=body.get("metadata")
    )
    return {
        "skill": {
            "name": item.name,
            "skill_path": item.skill_path,
            "description": item.description,
            "metadata": item.metadata_json,
        }
    }


@router.delete("/skills/{skill_name}", status_code=204, operation_id="unregister_skill")
async def remove_skill_registry(
    skill_name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    removed = await repo.remove_skill_registry(skill_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Skill not found")


# Session Skill enablement endpoints
@router.post(
    "/sessions/{session_id}/skills",
    status_code=201,
    operation_id="enable_session_skill",
)
async def enable_session_skill(
    session_id: str,
    body: SkillAssignmentRequest,
    repo: Repository = Depends(get_repository),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, Any]:
    # Verify session exists
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    item = await _register_on_disk_skill(repo, registry, body.skill_name)
    enabled = await repo.enable_skill_for_session(session_id, body.skill_name, True)
    if enabled is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "skill": {
            "id": f"{session_id}:{body.skill_name}",
            "skill_name": body.skill_name,
            "skill_path": item.skill_path,
            "created_at": enabled.created_at,
        }
    }


@router.get("/sessions/{session_id}/skills", operation_id="list_session_skills")
async def list_session_skills(
    item=Depends(require_session),
) -> dict[str, list[dict[str, Any]]]:
    return {
        "skills": [
            {
                "id": f"{item.id}:{skill.skill_name}",
                "skill_name": skill.skill_name,
                "skill_path": skill.skill.skill_path if skill.skill else "",
                "created_at": skill.created_at,
                "description": skill.skill.description if skill.skill else "",
                "enabled": skill.enabled,
            }
            for skill in item.enabled_skills
            if skill.enabled
        ]
    }


@router.patch(
    "/sessions/{session_id}/skills/{skill_name}",
    operation_id="set_session_skill_enabled",
)
async def enable_skill_for_session(
    session_id: str,
    skill_name: str,
    body: SessionMcpEnableRequest,
    repo: Repository = Depends(get_repository),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, Any]:
    if await repo.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not body.enabled:
        # Turning a skill off is idempotent: a session that never had this skill
        # is already in the requested state, so report it rather than failing.
        await _disable_session_skill(repo, session_id, skill_name)
        return {"skill": {"name": skill_name, "enabled": False}}

    await _register_on_disk_skill(repo, registry, skill_name)
    item = await repo.enable_skill_for_session(session_id, skill_name, True)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"skill": {"name": skill_name, "enabled": item.enabled}}


@router.delete(
    "/sessions/{session_id}/skills/{skill_name}",
    status_code=204,
    operation_id="disable_session_skill",
)
async def disable_skill_for_session(
    session_id: str,
    skill_name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    if await repo.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await _disable_session_skill(repo, session_id, skill_name)


async def _disable_session_skill(
    repo: Repository, session_id: str, skill_name: str
) -> None:
    """
    Ensure a skill is off for a session, whatever state it is in.

    Disabling is a no-op when the skill is already off or was never enabled.
    Rejecting those cases used to strand the dashboard: saving a session config
    replays the desired skill set, so one already-disabled skill aborted the
    whole save and no other setting was applied.
    """
    state = await repo.get_session_enabled_skill_state(session_id, skill_name)
    if state is None or not state.enabled:
        return
    await repo.enable_skill_for_session(session_id, skill_name, enabled=False)


# Global MCP Registry endpoints
@router.get("/mcps", operation_id="list_mcp_registry")
async def list_mcp_registry(
    repo: Repository = Depends(get_repository),
) -> dict[str, list[McpRegistryResponse]]:
    registries = await repo.list_mcp_registries()
    return {"mcps": [serialize_mcp_registry(mcp) for mcp in registries]}


@router.post("/mcps", status_code=201, operation_id="register_mcp")
async def add_mcp_registry(
    body: McpRegistryRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, McpRegistryResponse]:
    item = await repo.add_mcp_registry(
        name=body.name,
        transport=body.transport,
        server_url=body.server_url,
        headers_json=body.headers,
    )
    return {"mcp": serialize_mcp_registry(item)}


@router.delete("/mcps/{mcp_name}", status_code=204, operation_id="unregister_mcp")
async def remove_mcp_registry(
    mcp_name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    removed = await repo.remove_mcp_registry(mcp_name)
    if not removed:
        registry = await repo.get_mcp_registry(mcp_name)
        if registry is not None and not registry.custom:
            raise HTTPException(
                status_code=403, detail="Cannot delete non-custom MCP registry"
            )
        raise HTTPException(status_code=404, detail="MCP registry not found")


# Session MCP enablement endpoints
@router.post(
    "/sessions/{session_id}/mcps", status_code=201, operation_id="add_session_mcp"
)
async def add_mcp_to_session(
    session_id: str,
    body: McpRegistryRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, McpAssignmentResponse]:
    # Add or update the global MCP registry
    registry = await repo.add_mcp_registry(
        name=body.name,
        transport=body.transport,
        server_url=body.server_url,
        headers_json=body.headers,
    )
    # Enable the MCP for this session
    item = await repo.enable_mcp_for_session(session_id, body.name, enabled=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "mcp": McpAssignmentResponse(
            name=registry.name,
            transport=registry.transport,
            server_url=registry.server_url,
            headers=registry.headers_json,
            enabled=True,
            custom=registry.custom,
        )
    }


@router.get("/sessions/{session_id}/mcps", operation_id="list_session_mcps")
async def list_session_mcps(
    item=Depends(require_session),
    repo: Repository = Depends(get_repository),
) -> dict[str, list[McpAssignmentResponse]]:
    all_registries = await repo.list_mcp_registries()
    registry_map = {r.name: r for r in all_registries}
    enabled_map = {em.mcp_name: em for em in item.enabled_mcps}
    result = []
    for registry in all_registries:
        enabled_mcp = enabled_map.get(registry.name)
        result.append(
            McpAssignmentResponse(
                name=registry.name,
                transport=registry.transport,
                server_url=registry.server_url,
                headers=registry.headers_json,
                enabled=enabled_mcp.enabled if enabled_mcp else False,
                custom=registry.custom,
            )
        )
    return {"mcps": result}


@router.delete(
    "/sessions/{session_id}/mcps/{mcp_name}",
    status_code=204,
    operation_id="remove_session_mcp",
)
async def disable_mcp_for_session(
    session_id: str,
    mcp_name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    item = await repo.get_session_enabled_mcp_state(session_id, mcp_name)
    if item is None or not item.enabled:
        raise HTTPException(status_code=404, detail="MCP not enabled for session")
    await repo.enable_mcp_for_session(session_id, mcp_name, enabled=False)


@router.patch(
    "/sessions/{session_id}/mcps/{mcp_name}", operation_id="set_session_mcp_enabled"
)
async def enable_mcp_for_session(
    session_id: str,
    mcp_name: str,
    body: SessionMcpEnableRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, McpAssignmentResponse]:
    item = await repo.enable_mcp_for_session(session_id, mcp_name, body.enabled)
    if item is None:
        raise HTTPException(status_code=404, detail="Session or MCP not found")
    # Get the registry for transport/server_url info
    registries = await repo.list_mcp_registries()
    registry = next((r for r in registries if r.name == mcp_name), None)
    if registry is None:
        raise HTTPException(status_code=404, detail="MCP registry not found")
    return {
        "mcp": McpAssignmentResponse(
            name=mcp_name,
            transport=registry.transport,
            server_url=registry.server_url,
            headers=registry.headers_json,
            enabled=item.enabled,
            custom=registry.custom,
        )
    }


@router.get("/sessions/{session_id}/tools", operation_id="list_session_tools")
async def list_session_tools(
    tool_catalog: McpToolCatalog = Depends(get_mcp_tool_catalog),
    repo: Repository = Depends(get_repository),
    live_event_bus: LiveEventBus = Depends(get_live_event_bus),
    skill_registry: SkillRegistry = Depends(get_skill_registry),
    item=Depends(require_session),
) -> SessionToolsResponse:
    builtin_tools, mcp_tools = await list_effective_session_tools(
        mcp_tool_catalog=tool_catalog,
        skill_registry=skill_registry,
        repository=repo,
        live_event_bus=live_event_bus,
        session=item,
        is_master_job=True,
    )
    return SessionToolsResponse(
        tools=[
            *[serialize_builtin_tool_definition(tool) for tool in builtin_tools],
            *[serialize_tool_definition(tool) for tool in mcp_tools],
        ]
    )
