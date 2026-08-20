"""
Pydantic request/response models for the Game Service HTTP API.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field
from game_service.api.enums import LayoutId, PlayerN, SeatId

from game_service.logic.actions import GameAction
from game_service.logic.platform import DRAGNCARDS_PLATFORM, MoveSurface, PlatformSlug
from game_service.logic.snapshots import GameStateSnapshot
from game_service.schemas.base import StrictRequest

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

ChoiceIdentifier = (
    Annotated[int, Field(ge=0, le=2**63 - 1)]
    | Annotated[str, Field(min_length=1, max_length=128)]
)


class CreateGameRequest(StrictRequest):
    platform: PlatformSlug = Field(
        default=DRAGNCARDS_PLATFORM,
        description="Game platform to use for the session",
    )
    plugin_name: str = Field(
        default="marvel-champions",
        description="Plugin identifier to use for the new game session",
    )
    ephemeral: bool = Field(
        default=False,
        description=(
            "Create a non-emitting, server-reaped reconstruction session used "
            "only for viewing a past moment. Ephemeral sessions emit no history "
            "events and are deleted by a background reaper after a TTL even if "
            "the client never tears them down."
        ),
    )


class AttachGameRequest(StrictRequest):
    platform: PlatformSlug = Field(
        default=DRAGNCARDS_PLATFORM,
        description="Game platform hosting the existing game",
    )
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
    GameAction,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SessionMetadata(BaseModel):
    session_id: str
    platform: PlatformSlug = DRAGNCARDS_PLATFORM
    # These fields belong to the DragnCards platform. They remain present for
    # DragnCards responses, while a platform without plugins may leave them null.
    plugin_name: str | None = None
    plugin_id: int | None = None
    plugin_version: int | None = None
    room_slug: str
    created_at: str  # ISO-8601
    frontend_url: str | None = None
    # True for non-emitting, server-reaped reconstruction sessions (view-only).
    ephemeral: bool = False


class CreateGameResponse(BaseModel):
    session: SessionMetadata


class AttachGameResponse(BaseModel):
    session: SessionMetadata


class ListGamesResponse(BaseModel):
    sessions: list[SessionMetadata]


class LookupSessionBySlugResponse(BaseModel):
    """Metadata returned when resolving a session by its room slug.

    A non-mutating convenience read. Session endpoints accept a room slug directly,
    so this is only needed to inspect a session's full metadata or to obtain its
    canonical `session_id`.
    """

    session: SessionMetadata


class SimplifiedCard(BaseModel):
    """A simplified card representation for LLM consumption."""

    model_config = ConfigDict(extra="allow")

    id: str = "Unknown"
    instanceId: str = "Unknown"
    name: str = "Unknown"
    currentSide: str = "A"
    exhausted: bool = False
    tokens: dict = Field(default_factory=dict)
    stackSize: int = 1


class SimplifiedGameState(BaseModel):
    """Simplified Marvel Champions game state for LLM consumption."""

    model_config = ConfigDict(extra="allow")

    playRound: int | None = None
    mode: str = "unknown"
    villainHitPoints: int = 0
    stepId: str | int | None = None
    stepDescription: str | None = None
    phase: Literal["setup", "player", "villain", "passive", "unknown"] = "unknown"
    phaseLabel: str | None = None
    # A platform that does not expose pending seats omits this field entirely.
    pendingSeats: list[str] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    players: dict[str, dict[str, int]] = Field(default_factory=dict)
    zones: dict[str, list[SimplifiedCard]] = Field(default_factory=dict)


class GameStateResponse(BaseModel):
    session_id: str
    state: Union[SimplifiedGameState, dict[str, Any]] = Field(
        description="Current DragnCards game state object. Simplified format for Marvel Champions (flat keys), raw format for other plugins."
    )


class ExecuteActionResponse(BaseModel):
    session_id: str
    success: Literal[True]
    error: str | None = Field(
        default=None,
        description="Error message from action execution, if any",
    )


class DeleteGameResponse(BaseModel):
    session_id: str
    deleted: Literal[True] = True


class LoadPrebuiltDeckResponse(BaseModel):
    session_id: str
    success: Literal[True] = True


class ChooseGameOptionRequest(StrictRequest):
    """One neutral option choice; the driver translates it to ``POST /post``."""

    player_n: SeatId = "player1"
    option_id: ChoiceIdentifier | None = None
    targets: list[ChoiceIdentifier] = Field(default_factory=list, max_length=32)
    resources: list[ChoiceIdentifier] = Field(default_factory=list, max_length=32)
    decline: bool = False
    prompt_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Prompt signature returned by the preceding options read",
    )
    prompt_version: int = Field(
        ...,
        ge=0,
        le=2**32 - 1,
        description="Prompt version returned by the preceding options read",
    )


class ChooseGameOptionResponse(BaseModel):
    session_id: str
    player_n: SeatId
    option_id: int | str
    resolved: bool


class MarvelLcgScenariosResponse(BaseModel):
    scenarios: list[str]


class MarvelLcgDecksResponse(BaseModel):
    decks: list[str]


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


class ResetGameRequest(StrictRequest):
    save: bool = Field(default=False, description="Save the game before resetting")
    reload_plugin: bool = Field(
        default=False, description="Reload the plugin after resetting"
    )


class SetSeatRequest(StrictRequest):
    player_id: SeatId = Field(
        description=(
            "DragnCards seat id, 'player1' to 'player4'. Not an index: DragnCards "
            "uses this value directly as a key of the room's seat map, so a number "
            "writes an entry that no seat lookup ever finds."
        )
    )
    user_id: int = Field(description="DragnCards user ID to assign to the seat")


class SetSpectatorRequest(StrictRequest):
    user_id: int = Field(description="DragnCards user ID")
    spectating: bool = Field(
        description="True to enable spectator mode, False to disable"
    )


class SendAlertRequest(StrictRequest):
    message: str = Field(description="Alert message text to broadcast to the room")


# ---------------------------------------------------------------------------
# Room control response models
# ---------------------------------------------------------------------------


class ResetGameResponse(BaseModel):
    session_id: str
    state: Union[SimplifiedGameState, dict[str, Any]] = Field(
        description="Game state after the reset"
    )


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


class SetPlayerCountRequest(StrictRequest):
    num_players: int = Field(..., ge=1, description="Number of players (1 or more)")
    layout_id: LayoutId | None = Field(
        default=None,
        description=(
            "Optional plugin-specific layout ID to apply alongside the player count change, "
            "e.g. 'standard2Player'. Required by plugins that use a playerCountMenu."
        ),
    )


class SetPlayerCountResponse(BaseModel):
    session_id: str
    state: Union[SimplifiedGameState, dict[str, Any]] = Field(
        description="Game state after the player count was changed"
    )


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
    attributes: "CardAttributes" = Field(
        default_factory=lambda: CardAttributes(),
        description=(
            "Provider-derived card metadata normalized from the source card and printing data. "
            "Keys are provider-defined snake_case field names."
        ),
    )


class CardAttributes(BaseModel):
    """Provider-specific card attributes normalized into a typed object."""

    model_config = ConfigDict(extra="allow")


class PluginNamedActionList(BaseModel):
    id: str = Field(description="Plugin-defined named action list identifier")
    action_list: Any = Field(
        description="Named or inline DragnLang action list defined by the plugin"
    )


class PluginHotkey(BaseModel):
    scope: str = Field(description="Hotkey scope such as 'game', 'card', or 'token'")
    key: str = Field(description="Keyboard shortcut")
    label: str | None = Field(default=None, description="Plugin label for the hotkey")
    action_list: Any = Field(
        default=None,
        description="Named or inline action list triggered by the hotkey, if any",
    )
    token_type: str | None = Field(
        default=None, description="Token type adjusted by the hotkey, if any"
    )


class PluginTouchBarAction(BaseModel):
    id: str = Field(description="Plugin-defined touch bar action identifier")
    row: int = Field(description="Zero-based touch bar row index")
    order: int = Field(description="Zero-based order within the row")
    action_type: str = Field(
        description="Plugin action type such as card, game, token, or engine"
    )
    label: str | None = Field(
        default=None, description="Plugin label for the touch bar action"
    )
    action_list: Any = Field(
        default=None,
        description="Named or inline action list triggered by the touch bar action, if any",
    )
    token_type: str | None = Field(
        default=None, description="Token type adjusted by the touch bar action, if any"
    )
    image_url: str | None = Field(
        default=None, description="Optional image URL used by the plugin UI"
    )


class PluginDefaultAction(BaseModel):
    label: str | None = Field(
        default=None, description="Plugin label for the default action"
    )
    action_list: Any = Field(description="Named or inline default action list")
    condition: Any = Field(
        default=None,
        description="Plugin condition that controls whether the action is available",
    )
    position: str | None = Field(
        default=None, description="Optional plugin UI position for the action"
    )


class PluginPlayerCountLayout(BaseModel):
    label: str = Field(description="Plugin label for the player-count option")
    num_players: int = Field(description="Number of active players")
    layout_id: LayoutId | None = Field(
        default=None, description="Plugin layout ID associated with the player count"
    )


class PluginActionCatalogMetadata(BaseModel):
    platform: PlatformSlug | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    move_surface: MoveSurface | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    named_action_lists: list[PluginNamedActionList] = Field(default_factory=list)
    hotkeys: list[PluginHotkey] = Field(default_factory=list)
    touch_bar: list[PluginTouchBarAction] = Field(default_factory=list)
    default_actions: list[PluginDefaultAction] = Field(default_factory=list)
    player_count_layouts: list[PluginPlayerCountLayout] = Field(default_factory=list)
    load_groups: list[str] = Field(default_factory=list)


class SearchCardsResponse(BaseModel):
    total: int = Field(
        description="Number of results returned (may be capped by limit)"
    )
    cards: list[CardResult]


class CardProviderMetadataResponse(BaseModel):
    provider: str = Field(description="Plugin/provider identifier")
    display_name: str = Field(description="Human-readable plugin/provider name")
    default: bool = Field(description="Whether this is the default provider")
    filters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Supported search filters for this provider",
    )
    load_groups: list[str] = Field(
        default_factory=list,
        description="Supported load group IDs for this provider",
    )


class ListCardProvidersResponse(BaseModel):
    providers: list[CardProviderMetadataResponse]


class PrebuiltSetSummary(BaseModel):
    id: str = Field(description="Stable identifier for the prebuilt set")
    name: str = Field(description="Human-readable set name")
    type: str = Field(description="Set type, such as hero set or modular set")


class ListPrebuiltSetsResponse(BaseModel):
    total: int = Field(description="Number of matching prebuilt sets")
    sets: list[PrebuiltSetSummary]


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
    plugin_metadata: PluginActionCatalogMetadata = Field(
        description="Plugin-defined action metadata and UI affordances for this session"
    )
