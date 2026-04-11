"""
Pydantic request/response models for the Game Service HTTP API.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from game_service.session.actions import (
    DrawCardAction,
    LoadCardsAction,
    MoveCardAction,
    NextStepAction,
    PrevStepAction,
    RawAction,
    SetCardPropertyAction,
    SetPlayerCountAction,
    UnloadCardsAction,
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateGameRequest(BaseModel):
    plugin_name: str = Field(
        default="marvel-champions",
        description="Plugin identifier to use for the new game session",
    )


class AttachGameRequest(BaseModel):
    plugin_name: str = Field(
        default="marvel-champions",
        description="Plugin identifier for the existing room",
    )
    room_slug: str = Field(
        ...,
        description="DragnCards room slug to attach to (e.g. 'lively-fog-1234')",
    )


# Re-export action types so API consumers can reference them from one place.
# FastAPI/Pydantic will use the discriminated union for request body validation.
ActionRequest = Annotated[
    MoveCardAction
    | DrawCardAction
    | NextStepAction
    | PrevStepAction
    | SetCardPropertyAction
    | SetPlayerCountAction
    | LoadCardsAction
    | UnloadCardsAction
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


class AttachGameResponse(BaseModel):
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


class ActionSchema(BaseModel):
    """Schema for a single supported action type."""

    type: str = Field(description="Action type discriminator value")
    description: str = Field(
        description="Human-readable description of what the action does"
    )
    schema_: dict = Field(
        alias="schema", description="JSON Schema for this action's fields"
    )

    model_config = {"populate_by_name": True}


class DragnLangArg(BaseModel):
    """One argument in a DragnLang operation signature."""

    name: str = Field(description="Argument name")
    type: str = Field(
        description="Expected type, e.g. 'string', 'number', 'list', 'boolean'"
    )
    description: str = Field(description="What the argument controls")
    optional: bool = Field(default=False)


class DragnLangOp(BaseModel):
    """
    A DragnLang operation usable via the 'raw' action type.

    To use: POST /games/{id}/actions with
      {"type": "raw", "action_list": <example>, "description": "..."}
    """

    op: str = Field(description="DragnLang op name, e.g. 'SHUFFLE_GROUP'")
    description: str = Field(description="What the operation does")
    args: list[DragnLangArg] = Field(description="Ordered argument list")
    returns: str = Field(
        description="What the op returns, e.g. 'game state', 'list', 'card'"
    )
    example: list = Field(description="Example action_list to pass to a raw action")


class ListActionsResponse(BaseModel):
    """All action types supported by the execute_action endpoint."""

    actions: list[ActionSchema]
    raw_ops: list[DragnLangOp] = Field(
        default_factory=list,
        description=(
            "Curated catalogue of DragnLang operations available via the 'raw' action type. "
            "Each entry shows the op name, its argument signature, and an example action_list."
        ),
    )


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Room control request models
# ---------------------------------------------------------------------------


class ResetGameRequest(BaseModel):
    save: bool = Field(default=False, description="Save the game before resetting")
    reload_plugin: bool = Field(
        default=False, description="Reload the plugin after resetting"
    )


class SetSeatRequest(BaseModel):
    player_index: int = Field(description="Zero-based player seat index")
    user_id: int = Field(description="DragnCards user ID to assign to the seat")


class SetSpectatorRequest(BaseModel):
    user_id: int = Field(description="DragnCards user ID")
    spectating: bool = Field(
        description="True to enable spectator mode, False to disable"
    )


class SendAlertRequest(BaseModel):
    message: str = Field(description="Alert message text to broadcast to the room")


# ---------------------------------------------------------------------------
# Room control response models
# ---------------------------------------------------------------------------


class ResetGameResponse(BaseModel):
    session_id: str
    state: Any = Field(description="Game state after the reset")


class AlertsResponse(BaseModel):
    session_id: str
    alerts: list[dict] = Field(
        description="Buffered alert payloads received from the room, oldest first"
    )


class GuiUpdateResponse(BaseModel):
    session_id: str
    updates: dict[str, Any] = Field(
        description="Latest GUI update hint per player_n key"
    )


class SetPlayerCountRequest(BaseModel):
    num_players: int = Field(..., ge=1, description="Number of players (1 or more)")
    layout_id: str | None = Field(
        default=None,
        description=(
            "Optional plugin-specific layout ID to apply alongside the player count change, "
            "e.g. 'standard2Player'. Required by plugins that use a playerCountMenu."
        ),
    )


class SetPlayerCountResponse(BaseModel):
    session_id: str
    state: Any = Field(description="Game state after the player count was changed")


# ---------------------------------------------------------------------------
# Card search models
# ---------------------------------------------------------------------------


class CardResult(BaseModel):
    database_id: str = Field(description="UUID used in load_cards action")
    name: str
    subname: str | None = None
    type_code: str | None = Field(None, description="e.g. 'hero', 'ally', 'villain'")
    classification: str | None = Field(
        None, description="Aspect/classification, e.g. 'Justice'"
    )
    traits: list[str] = Field(default_factory=list)
    official: bool
    pack_id: str | None = None
    set_id: str | None = None
    pack_number: str | None = None


class SearchCardsResponse(BaseModel):
    total: int = Field(
        description="Number of results returned (may be capped by limit)"
    )
    cards: list[CardResult]


# ---------------------------------------------------------------------------
# Per-session actions model
# ---------------------------------------------------------------------------


class SessionActionsResponse(BaseModel):
    session_id: str
    plugin_name: str
    actions: list[ActionSchema] = Field(
        description="All action types accepted by POST /games/{session_id}/actions"
    )
    raw_ops: list[DragnLangOp] = Field(
        default_factory=list,
        description="Curated DragnLang operations available via the 'raw' action type",
    )
    load_groups: list[str] = Field(
        description=(
            "Valid loadGroupId values for this plugin's load_cards action. "
            "Use 'playerNDeck' etc. where N is substituted with the player number at runtime."
        )
    )
