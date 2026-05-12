from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_orchestrator.api.deps import (
    get_mcp_tool_catalog,
    get_repository,
    get_settings,
    get_skill_registry,
    require_session,
)
from agent_orchestrator.api.serializers import (
    serialize_job,
    serialize_mcp,
    serialize_model_config,
    serialize_session_detail,
    serialize_session_summary,
    serialize_skill,
    serialize_tool_definition,
)
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.mcp.tools import (
    McpToolCatalog,
    normalize_mcp_server_url,
)
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.common import PageInfo
from agent_orchestrator.schemas.jobs import SessionJobsResponse, SessionToolResponse
from agent_orchestrator.schemas.sessions import (
    McpAssignmentRequest,
    McpAssignmentResponse,
    ModelConfigRequest,
    ModelConfigResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
    SessionToolsResponse,
    SessionUpdateRequest,
    SkillAssignmentRequest,
    SkillAssignmentResponse,
)
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
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


@router.post("/sessions", status_code=201)
async def create_session(
    body: SessionCreateRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, SessionDetail]:
    item = await repo.create_session(
        body.name,
        body.metadata,
        multi_turn_memory=body.multi_turn_memory,
        context_recent_message_limit=body.context_recent_message_limit,
        context_recent_tool_exchange_limit=body.context_recent_tool_exchange_limit,
    )
    return {"session": serialize_session_detail(item)}


@router.get("/sessions/{session_id}/jobs")
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


@router.get("/sessions/{session_id}")
async def get_session(item=Depends(require_session)) -> dict[str, SessionDetail]:
    return {"session": serialize_session_detail(item)}


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdateRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, SessionDetail]:
    changes = body.model_dump(exclude_unset=True)
    if "metadata" in changes:
        changes["metadata_json"] = changes.pop("metadata")
    item = await repo.update_session(session_id, **changes)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": serialize_session_detail(item)}


@router.post("/sessions/{session_id}/terminate")
async def terminate_session(
    session_id: str,
    repo: Repository = Depends(get_repository),
) -> dict[str, SessionDetail]:
    item = await repo.terminate_session(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": serialize_session_detail(item)}


@router.put("/sessions/{session_id}/model-config")
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


@router.get("/sessions/{session_id}/skills")
async def list_skills(
    item=Depends(require_session),
) -> dict[str, list[SkillAssignmentResponse]]:
    return {"skills": [serialize_skill(skill) for skill in item.skill_assignments]}


@router.post("/sessions/{session_id}/skills", status_code=201)
async def assign_skill(
    session_id: str,
    body: SkillAssignmentRequest,
    repo: Repository = Depends(get_repository),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, SkillAssignmentResponse]:
    definition = registry.resolve(body.skill_name)
    if definition is None:
        raise HTTPException(status_code=400, detail="Unknown skill")
    item = await repo.add_skill_assignment(
        session_id, body.skill_name, str(definition.path)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"skill": serialize_skill(item)}


@router.delete("/sessions/{session_id}/skills/{skill_name}", status_code=204)
async def remove_skill(
    session_id: str,
    skill_name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    removed = await repo.remove_skill_assignment(session_id, skill_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Skill assignment not found")


@router.get("/sessions/{session_id}/mcps")
async def list_mcps(
    item=Depends(require_session),
) -> dict[str, list[McpAssignmentResponse]]:
    return {"mcps": [serialize_mcp(mcp) for mcp in item.mcp_assignments]}


@router.post("/sessions/{session_id}/mcps", status_code=201)
async def assign_mcp(
    session_id: str,
    body: McpAssignmentRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, McpAssignmentResponse]:
    normalized_server_url = normalize_mcp_server_url(body.server_url, body.transport)
    item = await repo.add_mcp_assignment(
        session_id,
        name=body.name,
        transport=body.transport,
        server_url=normalized_server_url,
        headers_json=body.headers,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"mcp": serialize_mcp(item)}


@router.get("/sessions/{session_id}/tools")
async def list_session_tools(
    tool_catalog: McpToolCatalog = Depends(get_mcp_tool_catalog),
    item=Depends(require_session),
) -> SessionToolsResponse:
    tools = await tool_catalog.list_session_tools(
        item.mcp_assignments, ignore_failures=True
    )
    return SessionToolsResponse(
        tools=[serialize_tool_definition(tool) for tool in tools]
    )


@router.delete("/sessions/{session_id}/mcps/{assignment_name}", status_code=204)
async def remove_mcp(
    session_id: str,
    assignment_name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    removed = await repo.remove_mcp_assignment(session_id, assignment_name)
    if not removed:
        raise HTTPException(status_code=404, detail="MCP assignment not found")
