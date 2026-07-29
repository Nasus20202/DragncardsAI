from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_orchestrator.runtime.player_agents import MAX_PLAYER_SKILLS


class PlayerReasoningConfig(BaseModel):
    """Per-seat reasoning settings.

    Stored folded into ``gateway_options`` under ``reasoning`` — the shape the
    runtime already reads — so callers never have to hand-assemble it.
    ``enabled=False`` removes reasoning for the seat entirely.
    """

    enabled: bool = True
    effort: Literal["low", "medium", "high"] | None = None
    max_tokens: int | None = Field(default=None, ge=1)


class PlayerConfigRequest(BaseModel):
    """A seat's configuration. Unset fields inherit from the session."""

    display_name: str | None = Field(default=None, max_length=255)
    provider_id: str | None = None
    model_name: str | None = Field(default=None, max_length=255)
    reasoning: PlayerReasoningConfig | None = None
    # The seat's persona, validated when the seat is configured so an unknown name
    # is reported to whoever is setting up the table, not to the orchestrator
    # mid-game. Captured onto the seat's session when that session is created.
    persona: str | None = Field(default=None, max_length=64)
    # ``None`` inherits the session's enabled skills; a list overrides them.
    skills: list[str] | None = Field(default=None, max_length=MAX_PLAYER_SKILLS)
    gateway_options: dict[str, Any] = Field(default_factory=dict)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class PlayerConfigResponse(BaseModel):
    player_id: str
    display_name: str | None
    provider_id: str | None
    model_name: str | None
    reasoning: dict[str, Any] | None
    persona: str | None
    skills: list[str] | None
    # The seat's own persistent agent session, ``None`` until the seat is first
    # prompted. Reading this session is how a user reads the seat's context.
    agent_session_id: str | None
    gateway_options: dict[str, Any]
    provider_options: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PlayerConfigListResponse(BaseModel):
    players: list[PlayerConfigResponse]
