from __future__ import annotations

from fastapi import HTTPException, Request

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.job_event_stream import JobEventStreamService
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_bifrost_client(request: Request) -> BifrostClient:
    return request.app.state.bifrost_client


def get_skill_registry(request: Request) -> SkillRegistry:
    return request.app.state.skill_registry


def get_mcp_tool_catalog(request: Request) -> McpToolCatalog:
    return request.app.state.mcp_tool_catalog


def get_live_event_bus(request: Request) -> LiveEventBus:
    return request.app.state.live_event_bus


def get_job_event_stream(request: Request) -> JobEventStreamService:
    return request.app.state.job_event_stream


async def require_session(request: Request, session_id: str):
    repo = get_repository(request)
    await repo.ensure_session_default_mcps(session_id)
    item = await repo.get_session(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return item


async def require_job(request: Request, job_id: str):
    repo = get_repository(request)
    item = await repo.get_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return item
