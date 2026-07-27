from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agent_orchestrator.schemas.common import PageInfo
from agent_orchestrator.schemas.jobs import JobSummary, SessionToolResponse
from agent_orchestrator.schemas.players import PlayerConfigResponse

# A supplied restored conversation context is replayed verbatim into the next
# prompt's message list and sent to the LLM, so it is validated to the same
# OpenAI chat-message shape the orchestrator itself produces. These bounds keep
# malformed or oversized input from reaching the runtime (and the session's
# persisted metadata).
MAX_CONVERSATION_CONTEXT_MESSAGES = 2000
MAX_CONVERSATION_CONTEXT_BYTES = 4_000_000
CONVERSATION_CONTEXT_ROLES = frozenset({"system", "user", "assistant", "tool"})


class SessionCreateRequest(BaseModel):
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    multi_turn_memory: bool = True
    context_recent_message_limit: int | None = Field(default=None, ge=0)
    context_recent_tool_exchange_limit: int | None = Field(default=None, ge=0)


class SessionUpdateRequest(BaseModel):
    name: str | None = None
    metadata: dict[str, Any] | None = None
    context_recent_message_limit: int | None = Field(default=None, ge=0)
    context_recent_tool_exchange_limit: int | None = Field(default=None, ge=0)


class ModelConfigRequest(BaseModel):
    provider_id: str
    model_name: str
    gateway_options: dict[str, Any] = Field(default_factory=dict)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class SkillAssignmentRequest(BaseModel):
    skill_name: str


class McpRegistryRequest(BaseModel):
    name: str
    transport: Literal["streamable-http", "sse"] = "streamable-http"
    server_url: str
    headers: dict[str, str] = Field(default_factory=dict)


class SessionMcpEnableRequest(BaseModel):
    enabled: bool


class SessionRestoreRequest(BaseModel):
    game_id: str = Field(min_length=1, max_length=64)
    conversation_context: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["new", "in_place"] = "new"

    @field_validator("conversation_context")
    @classmethod
    def validate_conversation_context(
        cls, value: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if len(value) > MAX_CONVERSATION_CONTEXT_MESSAGES:
            raise ValueError(
                "conversation_context exceeds the maximum of "
                f"{MAX_CONVERSATION_CONTEXT_MESSAGES} messages"
            )
        for index, message in enumerate(value):
            if not isinstance(message, dict):
                raise ValueError(f"conversation_context[{index}] must be an object")
            role = message.get("role")
            if not isinstance(role, str) or role not in CONVERSATION_CONTEXT_ROLES:
                allowed = ", ".join(sorted(CONVERSATION_CONTEXT_ROLES))
                raise ValueError(
                    f"conversation_context[{index}].role must be one of: {allowed}"
                )
        try:
            serialized_size = len(json.dumps(value).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("conversation_context must be JSON-serializable") from exc
        if serialized_size > MAX_CONVERSATION_CONTEXT_BYTES:
            raise ValueError(
                "conversation_context exceeds the maximum serialized size of "
                f"{MAX_CONVERSATION_CONTEXT_BYTES} bytes"
            )
        return value


class SessionRestoreResponse(BaseModel):
    session_id: str


class SessionSummary(BaseModel):
    id: str
    name: str | None
    status: str
    multi_turn_memory: bool
    context_recent_message_limit: int | None
    context_recent_tool_exchange_limit: int | None
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
    players: list[PlayerConfigResponse] = Field(default_factory=list)
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


class McpRegistryResponse(BaseModel):
    name: str
    transport: str
    server_url: str
    headers: dict[str, Any]
    custom: bool
    created_at: datetime


class McpAssignmentResponse(BaseModel):
    name: str
    transport: str
    server_url: str
    headers: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    custom: bool = False


class SessionDetail(SessionSummary):
    recent_jobs: list[JobSummary]


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    page: PageInfo


class SessionToolsResponse(BaseModel):
    tools: list[SessionToolResponse]
