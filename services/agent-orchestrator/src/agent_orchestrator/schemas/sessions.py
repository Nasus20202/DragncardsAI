from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_orchestrator.schemas.common import PageInfo
from agent_orchestrator.schemas.jobs import JobSummary, SessionToolResponse


class SessionCreateRequest(BaseModel):
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    multi_turn_memory: bool = True


class SessionUpdateRequest(BaseModel):
    name: str | None = None
    metadata: dict[str, Any] | None = None


class ModelConfigRequest(BaseModel):
    provider_id: str
    model_name: str
    gateway_options: dict[str, Any] = Field(default_factory=dict)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class SkillAssignmentRequest(BaseModel):
    skill_name: str


class McpAssignmentRequest(BaseModel):
    name: str
    transport: str = "streamable-http"
    server_url: str
    headers: dict[str, str] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    id: str
    name: str | None
    status: str
    multi_turn_memory: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    terminated_at: datetime | None
    session_model_config: ModelConfigResponse | None = Field(
        default=None,
        serialization_alias="model_config",
    )
    skills: list[SkillAssignmentResponse] = Field(default_factory=list)
    mcps: list[McpAssignmentResponse] = Field(default_factory=list)
    recent_job: JobSummary | None = None


class ModelConfigResponse(BaseModel):
    provider_id: str
    model_name: str
    gateway_options: dict[str, Any]
    provider_options: dict[str, Any]
    updated_at: datetime


class SkillAssignmentResponse(BaseModel):
    id: str
    skill_name: str
    skill_path: str
    created_at: datetime


class McpAssignmentResponse(BaseModel):
    id: str
    name: str
    transport: str
    server_url: str
    headers: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionSummary):
    recent_jobs: list[JobSummary]


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    page: PageInfo


class SessionToolsResponse(BaseModel):
    tools: list[SessionToolResponse]
