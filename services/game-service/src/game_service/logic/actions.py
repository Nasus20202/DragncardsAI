"""
Game action models and DragnCards WebSocket message translation.

DragnCards game actions are sent via the "game_action" channel event with payload:
  {
    "action": "evaluate",
    "options": {"action_list": <DragnLang action list>, "description": <str>},
    "timestamp": <unix_ms int>
  }

A DragnLang action list is a JSON array like:
  ["MOVE_CARD", cardId, destGroupId, destStackIndex]
  ["NEXT_STEP"]
  ["DRAW_CARD", playerN, count]

This module defines a typed Python action model and translates it into the
raw WebSocket payload expected by the RoomChannel.handle_in("game_action", ...) handler.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic import field_validator
import re

from game_service.catalog.providers.marvel_champions import plugin_metadata
from game_service.api.enums import GroupId

# Import enum-like Literal types exposed at the API/schema layer so internal
# action models validate common plugin-scoped fields (group IDs, player ids,
# layout ids) while remaining tied to the same source of truth used for OpenAPI
# schemas.
# Keep internal action models permissive (string-typed). Schema-level enums are
# exposed in game_service.api.* so OpenAPI/clients see allowed values without
# coupling runtime models to plugin metadata.


class MoveCardAction(BaseModel):
    """Move a card to a different group/position on the table."""

    type: Literal["move_card"] = "move_card"
    instance_id: str = Field(
        ...,
        description="Instance ID of the card to move (corresponds to instanceId in game state)",
    )
    dest_group_id: GroupId = Field(
        ..., description="ID of the destination group (e.g. 'player1Hand')"
    )
    dest_stack_index: int = Field(
        default=-1,
        description="Stack index in the destination group; -1 appends to end",
    )
    dest_card_index: int = Field(
        default=0,
        description="Card index within the destination stack (0 = top)",
    )
    player_n: str | None = Field(
        default=None,
        description=(
            "Player context for the move (e.g. 'player1'). "
            "Should be set whenever the card is moving to/from a player group. "
            "Injects player_ui.playerN so DragnCards automation rules that "
            "reference $PLAYER_N (e.g. playerDeckEmptied) fire correctly."
        ),
    )


class DrawCardAction(BaseModel):
    """Draw one or more cards from a player's deck to their hand."""

    type: Literal["draw_card"] = "draw_card"
    player_n: str = Field(
        default="player1",
        description="Player identifier (e.g. 'player1')",
    )

    @field_validator("player_n")
    @classmethod
    def _validate_player_n(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4", "shared"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v

    count: int = Field(default=1, ge=1, description="Number of cards to draw")


class NextStepAction(BaseModel):
    """Advance the game to the next step/phase."""

    type: Literal["next_step"] = "next_step"


class PrevStepAction(BaseModel):
    """Go back to the previous step/phase."""

    type: Literal["prev_step"] = "prev_step"


class SetCardPropertyAction(BaseModel):
    """Set an arbitrary property on a card (e.g. flip face-up/face-down)."""

    type: Literal["set_card_property"] = "set_card_property"
    instance_id: str = Field(
        ...,
        description="Instance ID of the card (corresponds to instanceId in game state)",
    )
    property_path: str = Field(
        ...,
        description="Slash-separated path relative to the card object, e.g. 'currentSide'",
    )
    value: Any = Field(..., description="New value to set")


class SetPlayerCountAction(BaseModel):
    """
    Set the number of active players in the game room.

    Sends a DragnLang SET on /numPlayers. If the plugin uses separate layout
    IDs per player count (e.g. DragnCards plugins with a playerCountMenu),
    pass layout_id as well so the table layout switches atomically with the
    player count. The layout ID is plugin-specific — consult the plugin's
    playerCountMenu configuration.
    """

    type: Literal["set_player_count"] = "set_player_count"
    num_players: int = Field(..., ge=1, description="Number of players (1 or more)")
    layout_id: str | None = Field(
        default=None,
        description=(
            "Optional plugin-specific layout ID to apply alongside the player count change, "
            "e.g. 'standard2Player'. Required by plugins that use a playerCountMenu."
        ),
    )


class RawAction(BaseModel):
    """
    Escape hatch: send an arbitrary DragnLang action list directly.
    Use when no typed action covers the intended operation.
    """

    type: Literal["raw"] = "raw"
    action_list: list = Field(
        ...,
        description="A DragnLang action list, e.g. ['NEXT_STEP'] or ['MOVE_CARD', id, group, -1]",
    )
    description: str = Field(
        default="raw action", description="Human-readable description"
    )
    player_n: str | None = Field(
        default=None,
        description=(
            "Player context for this action (e.g. 'player1'). Injects player_ui.playerN "
            "into the DragnCards request so $PLAYER_N is defined during automation."
        ),
    )


class LoadCardItem(BaseModel):
    """A single card entry in a LOAD_CARDS load list."""

    database_id: str = Field(
        ...,
        alias="databaseId",
        description=(
            "UUID identifying the card in the DragnCards card database. "
            "Use GET /cards to search for cards and retrieve their databaseId."
        ),
    )
    load_group_id: GroupId = Field(
        ...,
        alias="loadGroupId",
        description=(
            "Group to load the card into, e.g. 'player1Deck', 'sharedEncounterDeck'. "
            "Use 'playerNDeck' for the active player's deck (N is substituted at runtime)."
        ),
    )

    quantity: int = Field(default=1, ge=1, description="Number of copies to load")

    model_config = {"populate_by_name": True}


class LoadCardsAction(BaseModel):
    """
    Load a list of cards into the game by databaseId.

    Each card entry specifies the databaseId (UUID from GET /cards), the
    loadGroupId (destination group, e.g. 'player1Deck', 'sharedEncounterDeck'),
    and an optional quantity.

    Use 'playerNDeck' etc. as the loadGroupId to load into the active player's
    group — DragnCards will substitute N with the player number. In that case
    you must set player_n so the backend knows which player is loading.

    DragnCards will look up card details from its internal database, place
    cards into the specified groups, and run any plugin preLoadActionList /
    postLoadActionList automation.
    """

    type: Literal["load_cards"] = "load_cards"
    cards: list[LoadCardItem] = Field(
        ...,
        description="List of cards to load. Each entry needs databaseId, loadGroupId, and quantity.",
    )
    player_n: str = Field(
        default="player1",
        description=(
            "The player performing the load (e.g. 'player1'). "
            "Sets $PLAYER_N on the DragnCards backend so 'playerN' group ID "
            "templates are substituted correctly (e.g. 'playerNDeck' → 'player1Deck')."
        ),
    )

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_loads(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4", "shared"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v

    description: str = Field(
        default="Load cards",
        description="Human-readable description logged in the game history",
    )


class UnloadCardsAction(BaseModel):
    """
    Remove all cards belonging to a player or all shared/encounter cards.

    Pass player_n='player1' (or 'player2' etc.) to remove that player's cards
    (all cards where controller == player_n). Pass player_n='shared' to remove
    all shared and encounter cards (cards whose controller is not a player).
    """

    type: Literal["unload_cards"] = "unload_cards"
    player_n: str = Field(
        ...,
        description=(
            "Whose cards to remove: 'player1', 'player2', 'player3', 'player4', or 'shared'."
        ),
    )

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_unload(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4", "shared"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v

    # Player identifier validation is intentionally permissive here; request
    # level APIs may tighten allowed values via schema enums.


class ExhaustCardAction(BaseModel):
    """Exhaust a card (turn it sideways)."""

    type: Literal["exhaust_card"] = "exhaust_card"
    instance_id: str = Field(..., description="Instance ID of the card to exhaust")


class ReadyCardAction(BaseModel):
    """Ready a card (remove exhaustion)."""

    type: Literal["ready_card"] = "ready_card"
    instance_id: str = Field(..., description="Instance ID of the card to ready")


class FlipCardAction(BaseModel):
    """Flip a card to the next side (A → B → C → A)."""

    type: Literal["flip_card"] = "flip_card"
    instance_id: str = Field(..., description="Instance ID of the card to flip")


class DealEncounterAction(BaseModel):
    """Deal an encounter card to a player."""

    type: Literal["deal_encounter"] = "deal_encounter"
    player_n: str = Field(..., description="Player to deal to (e.g., 'player1')")
    facedown: bool = Field(
        default=False, description="Deal facedown if true, faceup if false"
    )
    deck_group_id: str | None = Field(
        default=None,
        description="Optional encounter deck to draw from (e.g., 'sharedEncounter2Deck')",
    )

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_deal(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v


class DrawBoostAction(BaseModel):
    """Draw a boost card from the encounter deck."""

    type: Literal["draw_boost"] = "draw_boost"
    player_n: str = Field(..., description="Player to draw boost for (e.g., 'player1')")

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_boost(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v


class ShuffleIntoDeckAction(BaseModel):
    """Move a card to its deck and shuffle that deck."""

    type: Literal["shuffle_into_deck"] = "shuffle_into_deck"
    instance_id: str = Field(
        ..., description="Instance ID of the card to shuffle into its deck"
    )


class ZeroTokensAction(BaseModel):
    """Remove all tokens from a card."""

    type: Literal["zero_tokens"] = "zero_tokens"
    instance_id: str = Field(
        ..., description="Instance ID of the card to clear tokens from"
    )


class MulliganDrawHandAction(BaseModel):
    """Perform mulligan - redraw starting hand if round 0."""

    type: Literal["mulligan_draw_hand"] = "mulligan_draw_hand"
    player_n: str = Field(
        ..., description="Player performing mulligan (e.g., 'player1')"
    )

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_mulligan(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v


class ShadowsOfThePastAction(BaseModel):
    """Resolve Shadows of the Past - move nemesis minions and side schemes."""

    type: Literal["shadows_of_the_past"] = "shadows_of_the_past"
    player_n: str = Field(..., description="Player resolving Shadows of the Past")

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_shadows(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v


class PlayerEndPhaseAction(BaseModel):
    """End the player phase and begin villain phase."""

    type: Literal["player_end_phase"] = "player_end_phase"


class VillainEncounterPhaseAction(BaseModel):
    """Execute villain encounter phase (deal facedown to all players)."""

    type: Literal["villain_encounter_phase"] = "villain_encounter_phase"


class VillainEndPhaseAction(BaseModel):
    """End the villain phase and return to player phase."""

    type: Literal["villain_end_phase"] = "villain_end_phase"


class MultipleDoubleSidedVillainsAction(BaseModel):
    """Handle multiple double-sided villains setup."""

    type: Literal["multiple_double_sided_villains"] = "multiple_double_sided_villains"


class DiscardMinionAction(BaseModel):
    """Discard cards until a minion is found."""

    type: Literal["discard_minion"] = "discard_minion"
    player_n: str = Field(..., description="Player to discard for (e.g., 'player1')")

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_discard_minion(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v


class DiscardSideSchemeAction(BaseModel):
    """Discard cards until a side scheme is found."""

    type: Literal["discard_side_scheme"] = "discard_side_scheme"
    player_n: str = Field(..., description="Player to discard for (e.g., 'player1')")

    @field_validator("player_n")
    @classmethod
    def _validate_player_n_discard_side_scheme(cls, v: str) -> str:
        allowed = {"player1", "player2", "player3", "player4"}
        if v not in allowed:
            raise ValueError(f"Invalid player_n: {v}")
        return v


class ModifyTokensAction(BaseModel):
    """Add or remove tokens from a card."""

    type: Literal["modify_tokens"] = "modify_tokens"
    instance_id: str = Field(..., description="Instance ID of the card")
    token_type: Literal[
        "damage", "threat", "generic", "acceleration", "confused", "stunned", "tough"
    ] = Field(..., description="Type of token to modify")
    amount: int = Field(
        ..., description="Amount to add (positive) or remove (negative)"
    )


GameAction = (
    MoveCardAction
    | DrawCardAction
    | NextStepAction
    | PrevStepAction
    | SetCardPropertyAction
    | SetPlayerCountAction
    | LoadCardsAction
    | UnloadCardsAction
    | RawAction
    | ExhaustCardAction
    | ReadyCardAction
    | FlipCardAction
    | DealEncounterAction
    | DrawBoostAction
    | ShuffleIntoDeckAction
    | ZeroTokensAction
    | MulliganDrawHandAction
    | ShadowsOfThePastAction
    | PlayerEndPhaseAction
    | VillainEncounterPhaseAction
    | VillainEndPhaseAction
    | MultipleDoubleSidedVillainsAction
    | DiscardMinionAction
    | DiscardSideSchemeAction
    | ModifyTokensAction
)

ACTION_TYPES = (
    NextStepAction,
    PrevStepAction,
    DrawCardAction,
    MoveCardAction,
    SetCardPropertyAction,
    SetPlayerCountAction,
    LoadCardsAction,
    UnloadCardsAction,
    RawAction,
    ExhaustCardAction,
    ReadyCardAction,
    FlipCardAction,
    DealEncounterAction,
    DrawBoostAction,
    ShuffleIntoDeckAction,
    ZeroTokensAction,
    ShadowsOfThePastAction,
    PlayerEndPhaseAction,
    VillainEncounterPhaseAction,
    VillainEndPhaseAction,
    MultipleDoubleSidedVillainsAction,
    DiscardMinionAction,
    DiscardSideSchemeAction,
    ModifyTokensAction,
)


def translate_action(action: GameAction) -> dict:
    """
    Translate a typed GameAction into the DragnCards WebSocket game_action payload.

    Returns a dict ready to pass to Channel.push("game_action", payload).
    """
    action_list, description, player_n = _to_dragncards(action)
    options: dict = {
        "action_list": action_list,
        "description": description,
    }
    if player_n is not None:
        options["player_ui"] = {"playerN": player_n}
    return {
        "action": "evaluate",
        "options": options,
        "timestamp": int(time.time() * 1000),
    }


def _to_dragncards(action: GameAction) -> tuple[list, str, str | None]:
    """Return (dragnlang_action_list, description, player_n_or_None)."""
    if isinstance(action, MoveCardAction):
        args: list = [
            "MOVE_CARD",
            action.instance_id,
            action.dest_group_id,
            action.dest_stack_index,
        ]
        if action.dest_card_index != 0:
            args.append(action.dest_card_index)
        # If the action did not explicitly set player_n but the destination
        # group is a player-scoped group (e.g. 'player1Play1'), infer and
        # inject the player context so DragnCards automation rules that
        # reference $PLAYER_N resolve correctly.
        player_n = action.player_n
        if player_n is None:
            m = re.match(r"^(player[1-4])", str(action.dest_group_id))
            if m:
                player_n = m.group(1)

        return (
            args,
            f"Move card {action.instance_id} to {action.dest_group_id}[{action.dest_stack_index}]",
            player_n,
        )

    if isinstance(action, DrawCardAction):
        return (
            ["DRAW_CARD", action.count],
            f"{action.player_n} draws {action.count} card(s)",
            action.player_n,
        )

    if isinstance(action, NextStepAction):
        return ["NEXT_STEP"], "Advance to next step", None

    if isinstance(action, PrevStepAction):
        return ["PREV_STEP"], "Go back to previous step", None

    if isinstance(action, SetCardPropertyAction):
        path = f"/cardById/{action.instance_id}/{action.property_path}"
        return (
            ["SET", path, action.value],
            f"Set {action.property_path} on card {action.instance_id}",
            None,
        )

    if isinstance(action, SetPlayerCountAction):
        steps: list = [["SET", "/numPlayers", action.num_players]]
        if action.layout_id is not None:
            steps.append(["SET_LAYOUT", "shared", action.layout_id])
        description = f"Set player count to {action.num_players}"
        if action.layout_id is not None:
            description += f" (layout: {action.layout_id})"
        return steps, description, None

    if isinstance(action, LoadCardsAction):
        load_list = [
            {
                "databaseId": item.database_id,
                "loadGroupId": item.load_group_id,
                "quantity": item.quantity,
            }
            for item in action.cards
        ]
        return (
            ["LOAD_CARDS", ["LIST"] + load_list],
            action.description,
            action.player_n,
        )

    if isinstance(action, UnloadCardsAction):
        return (
            ["UNLOAD_CARDS", action.player_n],
            f"Unload cards for {action.player_n}",
            action.player_n,
        )

    if isinstance(action, RawAction):
        return action.action_list, action.description, action.player_n

    if isinstance(action, ExhaustCardAction):
        return (
            ["EXHAUST_CARD", action.instance_id],
            f"Exhaust card {action.instance_id}",
            None,
        )

    if isinstance(action, ReadyCardAction):
        return (
            ["READY_CARD", action.instance_id],
            f"Ready card {action.instance_id}",
            None,
        )

    if isinstance(action, FlipCardAction):
        # Implement flip logic directly since Marvel Champions flipCard action list
        # expects $ACTIVE_CARD context from UI selection which isn't available here.
        # Cycle sides: A -> B -> C -> A (using multi-condition COND)
        card_id = action.instance_id
        return (
            [
                "COND",
                ["DEFINED", f"$GAME.cardById.{card_id}.sides.C"],
                [
                    [
                        "COND",
                        ["EQUAL", f"$GAME.cardById.{card_id}.currentSide", "A"],
                        ["SET", f"/cardById/{card_id}/currentSide", "B"],
                        ["EQUAL", f"$GAME.cardById.{card_id}.currentSide", "B"],
                        ["SET", f"/cardById/{card_id}/currentSide", "C"],
                        True,
                        ["SET", f"/cardById/{card_id}/currentSide", "A"],
                    ]
                ],
                True,
                [
                    [
                        "COND",
                        ["EQUAL", f"$GAME.cardById.{card_id}.currentSide", "A"],
                        ["SET", f"/cardById/{card_id}/currentSide", "B"],
                        True,
                        ["SET", f"/cardById/{card_id}/currentSide", "A"],
                    ]
                ],
            ],
            f"Flip card {action.instance_id}",
            None,
        )

    if isinstance(action, DealEncounterAction):
        action_name = (
            "dealEncounterFaceup" if not action.facedown else "dealEncounterFacedown"
        )
        if action.deck_group_id is not None:
            # Use specific deck for second/third encounter
            action_name = (
                f"dealSecondFaceup"
                if action.deck_group_id == "sharedEncounter2Deck"
                and not action.facedown
                else (
                    f"dealSecondFacedown"
                    if action.deck_group_id == "sharedEncounter2Deck"
                    else (
                        f"dealThirdFaceup"
                        if action.deck_group_id == "sharedEncounter3Deck"
                        and not action.facedown
                        else "dealThirdFacedown"
                    )
                )
            )
            return (
                ["ACTION_LIST", action_name],
                f"Deal encounter card from {action.deck_group_id} to {action.player_n}",
                action.player_n,
            )
        return (
            ["ACTION_LIST", action_name],
            f"Deal encounter card to {action.player_n}",
            action.player_n,
        )

    if isinstance(action, DrawBoostAction):
        return (
            ["ACTION_LIST", "drawBoost"],
            f"Draw boost for {action.player_n}",
            action.player_n,
        )

    if isinstance(action, ShuffleIntoDeckAction):
        # Marvel Champions shuffleIntoDeck action list expects $ACTIVE_CARD context.
        # Implement inline: read card's deckGroupId, move card there, shuffle.
        return (
            [
                [
                    "VAR",
                    "$DECK_GROUP_ID",
                    f"/cardById/{action.instance_id}/deckGroupId",
                ],
                ["MOVE_CARD", action.instance_id, "$DECK_GROUP_ID", 0],
                ["SHUFFLE_GROUP", "$DECK_GROUP_ID"],
            ],
            f"Shuffle card {action.instance_id} into its deck",
            None,
        )

    if isinstance(action, ZeroTokensAction):
        # zeroTokens action list just does SET on tokens - we can do this directly
        return (
            [["SET", f"/cardById/{action.instance_id}/tokens", {}]],
            f"Clear tokens from card {action.instance_id}",
            None,
        )

    if isinstance(action, MulliganDrawHandAction):
        # mulliganDrawHand draws a new hand if roundNumber is 0
        return (
            [
                [
                    "COND",
                    ["EQUAL", "$GAME.roundNumber", 0],
                    [["LOG", f"{action.player_n} mulliganed."]],
                ],
                ["DRAW_HAND", action.player_n, action.player_n],
            ],
            f"Mulligan for {action.player_n}",
            action.player_n,
        )

    if isinstance(action, ShadowsOfThePastAction):
        return (
            ["ACTION_LIST", "shadowsOfThePast"],
            f"Shadows of the Past for {action.player_n}",
            action.player_n,
        )

    if isinstance(action, PlayerEndPhaseAction):
        return (
            ["ACTION_LIST", "playerEndPhase"],
            "End player phase",
            None,
        )

    if isinstance(action, VillainEncounterPhaseAction):
        return (
            ["ACTION_LIST", "villainEncounterPhase"],
            "Villain encounter phase",
            None,
        )

    if isinstance(action, VillainEndPhaseAction):
        return (
            ["ACTION_LIST", "villainEndPhase"],
            "End villain phase",
            None,
        )

    if isinstance(action, MultipleDoubleSidedVillainsAction):
        return (
            ["ACTION_LIST", "multipleDoubleSidedVillains"],
            "Multiple double-sided villains setup",
            None,
        )

    if isinstance(action, DiscardMinionAction):
        return (
            ["ACTION_LIST", "discardMinion"],
            f"Discard until minion for {action.player_n}",
            action.player_n,
        )

    if isinstance(action, DiscardSideSchemeAction):
        return (
            ["ACTION_LIST", "discardSideScheme"],
            f"Discard until side scheme for {action.player_n}",
            action.player_n,
        )

    if isinstance(action, ModifyTokensAction):
        return (
            [
                "INCREASE_VAL",
                f"/cardById/{action.instance_id}/tokens/{action.token_type}",
                action.amount,
            ],
            f"Modify {action.token_type} on card {action.instance_id} by {action.amount}",
            None,
        )

    raise ValueError(f"Unknown action type: {type(action)}")
