from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_orchestrator.schemas.common import PageInfo


class PromptRequest(BaseModel):
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int | None = None


class JobSummary(BaseModel):
    id: str
    prompt_run_id: str
    status: str
    attempts: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    result_text: str | None
    cancellation_requested_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    latest_event_id: int | None = None
    latest_event_type: str | None = None


class PromptRunSummary(BaseModel):
    id: str
    prompt: str
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class JobEventResponse(BaseModel):
    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class SessionToolResponse(BaseModel):
    name: str
    assignment_name: str
    transport: str
    server_url: str
    actual_name: str
    description: str | None
    parameters: dict[str, Any]


class JobDetail(JobSummary):
    prompt_run: PromptRunSummary
    outputs: list[str]
    events: list[JobEventResponse] = Field(default_factory=list)
    available_tools: list[SessionToolResponse] = Field(default_factory=list)


class SessionJobsResponse(BaseModel):
    jobs: list[JobSummary]
    page: PageInfo
