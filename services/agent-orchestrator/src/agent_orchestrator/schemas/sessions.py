from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agent_orchestrator.runtime.session_modes import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
)
from agent_orchestrator.schemas.base import StrictRequest
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

# The mode is constrained at the schema boundary so an unknown value is a 422
# rather than a row that no code path knows how to interpret.
SessionMode = Literal[SESSION_MODE_CHAT, SESSION_MODE_ORCHESTRATED]

# Stated once and attached to the request and response fields alike, because it
# reaches three audiences that would otherwise each guess: the OpenAPI schema, the
# MCP tool generated from it, and whoever reads the model in this file.
SESSION_PERSONA_DESCRIPTION = (
    "The persona this session's own agent runs as, or null for none. Its "
    "instructions are added to the session's system prompt and its tool "
    "allowlist narrows the session's tools. It deliberately does NOT change the "
    "session's provider, model, options or skills: those have their own controls "
    "on the same session, and a persona overwriting them would make those "
    "controls misreport what the agent runs with. Resolved and snapshotted when "
    "it is set, so editing or deleting the persona afterwards does not change a "
    "session that already adopted it. Editable for the life of the session."
)

# A session's allowlist is a selection from a deployment-global catalogue an
# operator maintains by hand. Bounded so one request cannot write an unbounded
# number of rows, at a limit no realistic catalogue reaches.
MAX_ALLOWED_SUBAGENTS = 128

# Attached to every place the allowlist is reported, because the one thing a
# reader must not have to infer is what the empty case means.
ALLOWED_SUBAGENTS_DESCRIPTION = (
    "The personas this session's agent may start a subagent from, enforced "
    "server-side when `spawn_subagent` runs. AN EMPTY LIST MEANS NO PERSONA MAY "
    "BE SPAWNED — it is never read as 'all personas'. A session that should be "
    "able to spawn every persona lists every persona. Spawning a subagent with "
    "no persona at all, which copies this session's configuration, is unaffected."
)


class SessionCreateRequest(StrictRequest):
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    multi_turn_memory: bool = True
    # ``chat`` keeps the pre-orchestration single-agent flow, unchanged.
    session_mode: SessionMode = SESSION_MODE_CHAT
    context_recent_message_limit: int | None = Field(default=None, ge=0)
    context_recent_tool_exchange_limit: int | None = Field(default=None, ge=0)
    # The persona this session's subagents are started from when the agent names
    # none. ``None`` keeps the pre-persona behaviour.
    default_subagent_persona: str | None = Field(default=None, max_length=64)
    session_persona: str | None = Field(
        default=None, max_length=64, description=SESSION_PERSONA_DESCRIPTION
    )
    allowed_subagents: list[str] = Field(
        default_factory=list,
        max_length=MAX_ALLOWED_SUBAGENTS,
        description=ALLOWED_SUBAGENTS_DESCRIPTION,
    )


class SessionUpdateRequest(StrictRequest):
    name: str | None = None
    metadata: dict[str, Any] | None = None
    # Omitted leaves the mode unchanged. A change is refused once the session has
    # run a job, because its seats' persistent sessions are recorded against it.
    session_mode: SessionMode | None = None
    context_recent_message_limit: int | None = Field(default=None, ge=0)
    context_recent_tool_exchange_limit: int | None = Field(default=None, ge=0)
    # Sent as ``null`` to clear the default; omitted to leave it unchanged.
    default_subagent_persona: str | None = Field(default=None, max_length=64)
    # Sent as ``null`` to drop the session's persona; omitted to leave it
    # unchanged. Editable for the life of the session — see the description.
    session_persona: str | None = Field(
        default=None, max_length=64, description=SESSION_PERSONA_DESCRIPTION
    )
    # Sent to replace the whole allowlist in one write; omitted to leave it
    # unchanged. `[]` is a real value and means "allow no persona".
    allowed_subagents: list[str] | None = Field(
        default=None,
        max_length=MAX_ALLOWED_SUBAGENTS,
        description=ALLOWED_SUBAGENTS_DESCRIPTION,
    )


class ModelConfigRequest(StrictRequest):
    provider_id: str
    model_name: str
    gateway_options: dict[str, Any] = Field(default_factory=dict)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class SkillAssignmentRequest(StrictRequest):
    skill_name: str


class SkillRegistrationRequest(StrictRequest):
    """Register an on-disk skill in the deployment-global registry.

    ``name`` is declared optional even though the endpoint requires it, so that a
    body omitting it keeps answering `400 name is required` rather than turning
    into a `422`. Requiring it here would have been tidier and would have moved an
    error this change has no business moving: what became strict is the body's
    *shape*, not the endpoint's validation of the values in it.
    """

    name: str | None = None
    metadata: dict[str, Any] | None = None


class SubagentAllowanceRequest(StrictRequest):
    """Add one persona to a session's subagent allowlist."""

    persona: str = Field(min_length=1, max_length=64)


class SubagentAllowanceEnabledRequest(StrictRequest):
    enabled: bool


class SubagentAllowanceResponse(BaseModel):
    """One persona of the deployment catalogue, and whether this session allows it.

    Every persona is reported with its own ``allowed`` flag rather than only the
    permitted ones being listed. That is deliberate: a response that returned just
    an allowlist would make a reader interpret the empty array, and interpreting
    it is exactly the mistake this control exists to prevent.
    """

    name: str
    display_name: str | None = None
    description: str | None = None
    allowed: bool


class SubagentAllowanceListResponse(BaseModel):
    subagents: list[SubagentAllowanceResponse]


class McpRegistryRequest(StrictRequest):
    name: str
    transport: Literal["streamable-http", "sse"] = "streamable-http"
    server_url: str
    headers: dict[str, str] = Field(default_factory=dict)


class SessionMcpEnableRequest(StrictRequest):
    enabled: bool


class SessionRestoreRequest(StrictRequest):
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
    session_mode: str
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
    # The persona subagents spawned from this session are started from when the
    # agent names none. ``None`` keeps the pre-persona behaviour.
    default_subagent_persona: str | None = None
    session_persona: str | None = Field(
        default=None, description=SESSION_PERSONA_DESCRIPTION
    )
    allowed_subagents: list[str] = Field(
        default_factory=list, description=ALLOWED_SUBAGENTS_DESCRIPTION
    )
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
