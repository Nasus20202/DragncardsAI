"""
Pydantic request/response models for the Game Service HTTP API.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from game_service.session.actions import (
    DrawCardAction,
    MoveCardAction,
    NextStepAction,
    PrevStepAction,
    RawAction,
    SetCardPropertyAction,
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateGameRequest(BaseModel):
    plugin_name: str = Field(
        default="marvel-champions",
        description="Plugin identifier to use for the new game session",
    )


# Re-export action types so API consumers can reference them from one place.
# FastAPI/Pydantic will use the discriminated union for request body validation.
ActionRequest = Annotated[
    MoveCardAction
    | DrawCardAction
    | NextStepAction
    | PrevStepAction
    | SetCardPropertyAction
    | RawAction,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SessionMetadata(BaseModel):
    session_id: str
    plugin_name: str
    plugin_id: int
    room_slug: str
    created_at: str  # ISO-8601


class CreateGameResponse(BaseModel):
    session: SessionMetadata


class ListGamesResponse(BaseModel):
    sessions: list[SessionMetadata]


class GameStateResponse(BaseModel):
    session_id: str
    state: Any = Field(description="Current DragnCards game state object")


class ExecuteActionResponse(BaseModel):
    session_id: str
    state: Any = Field(description="Game state after the action was executed")


class DeleteGameResponse(BaseModel):
    session_id: str
    deleted: Literal[True] = True


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    detail: str
