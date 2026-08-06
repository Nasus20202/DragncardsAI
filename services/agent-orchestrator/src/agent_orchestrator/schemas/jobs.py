from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_orchestrator.schemas.base import StrictRequest
from agent_orchestrator.schemas.common import PageInfo


class PromptRequest(StrictRequest):
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int | None = None
    # Skills whose full content this prompt loads into its own turn — what the
    # dashboard's `@` mentions resolve to. Names only; the content is read from
    # the skill roots server-side.
    inline_skills: list[str] = Field(default_factory=list)


class JobSummary(BaseModel):
    id: str
    prompt: str
    metadata: dict[str, Any]
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
    latest_event_id: str | None = None
    latest_event_type: str | None = None


class JobEventResponse(BaseModel):
    id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class QuestionAnswerRequest(StrictRequest):
    """An answer to a question the agent asked.

    Exactly one field is accepted. ``choice_value`` must be one of the values the
    model actually offered — the endpoint checks it against the stored question,
    never against anything carried in this request.
    """

    choice_value: str | None = None
    text: str | None = None


class QuestionChoiceResponse(BaseModel):
    label: str
    value: str
    description: str | None = None


class JobQuestionResponse(BaseModel):
    id: str
    job_id: str
    status: str
    question: str
    choices: list[QuestionChoiceResponse]
    allow_free_text: bool
    answer_source: str | None
    answer_value: str | None
    answer_label: str | None
    answer_text: str | None
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime


class SessionToolResponse(BaseModel):
    name: str
    assignment_name: str
    transport: str
    server_url: str
    actual_name: str
    description: str | None
    parameters: dict[str, Any]


class JobDetail(JobSummary):
    outputs: list[str]
    events: list[JobEventResponse] = Field(default_factory=list)
    available_tools: list[SessionToolResponse] = Field(default_factory=list)


class SessionJobsResponse(BaseModel):
    jobs: list[JobSummary]
    page: PageInfo
