from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_orchestrator.runtime.personas import (
    MAX_PERSONA_ALLOWED_TOOLS,
    MAX_PERSONA_DESCRIPTION_CHARS,
    MAX_PERSONA_PROMPT_CHARS,
    MAX_PERSONA_SKILLS,
)
from agent_orchestrator.schemas.base import StrictRequest
from agent_orchestrator.schemas.players import PlayerReasoningConfig


class PersonaRequest(StrictRequest):
    """A persona's configuration. Unset fields inherit from the spawning session.

    Every field is bounded here rather than only at the database column, so an
    oversized prompt is a 422 before it reaches storage. The persona carries no
    credentials: `provider_id` and `model_name` NAME a provider configuration,
    and API keys stay in the gateway's own configuration.
    """

    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(
        default=None, max_length=MAX_PERSONA_DESCRIPTION_CHARS
    )
    # The detailed prompt that makes this persona distinct. Treated purely as
    # text: it is concatenated into the child's system prompt and never used as a
    # format string or interpolated anywhere text becomes code.
    system_prompt: str = Field(default="", max_length=MAX_PERSONA_PROMPT_CHARS)
    provider_id: str | None = None
    model_name: str | None = Field(default=None, max_length=255)
    reasoning: PlayerReasoningConfig | None = None
    # ``None`` inherits the spawning session's enabled skills; a list overrides.
    skills: list[str] | None = Field(default=None, max_length=MAX_PERSONA_SKILLS)
    # ``None`` narrows nothing; a list is an allowlist that can only REMOVE tools
    # from what the child session already exposes.
    allowed_tools: list[str] | None = Field(
        default=None, max_length=MAX_PERSONA_ALLOWED_TOOLS
    )
    gateway_options: dict[str, Any] = Field(default_factory=dict)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class PersonaResponse(BaseModel):
    name: str
    display_name: str | None
    description: str | None
    system_prompt: str
    provider_id: str | None
    model_name: str | None
    reasoning: dict[str, Any] | None
    skills: list[str] | None
    allowed_tools: list[str] | None
    gateway_options: dict[str, Any]
    provider_options: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PersonaListResponse(BaseModel):
    personas: list[PersonaResponse]
