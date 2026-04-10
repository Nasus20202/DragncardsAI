"""
Game action models and DragnCards WebSocket message translation.

DragnCards game actions are sent via the "game_action" channel event with payload:
  {
    "action": <DragnLang action list>,
    "options": {"description": <str>},
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


# ---------------------------------------------------------------------------
# Action models
# ---------------------------------------------------------------------------


class MoveCardAction(BaseModel):
    """Move a card to a different group/position on the table."""

    type: Literal["move_card"] = "move_card"
    card_id: str = Field(..., description="ID of the card to move")
    dest_group_id: str = Field(
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


class DrawCardAction(BaseModel):
    """Draw one or more cards from a player's deck to their hand."""

    type: Literal["draw_card"] = "draw_card"
    player_n: str = Field(
        default="player1",
        description="Player identifier (e.g. 'player1')",
    )
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
    card_id: str = Field(..., description="ID of the card")
    property_path: str = Field(
        ...,
        description="Slash-separated path relative to the card object, e.g. 'currentSide'",
    )
    value: Any = Field(..., description="New value to set")


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


# Union type used in API/MCP schemas
GameAction = (
    MoveCardAction
    | DrawCardAction
    | NextStepAction
    | PrevStepAction
    | SetCardPropertyAction
    | RawAction
)


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------


def translate_action(action: GameAction) -> dict:
    """
    Translate a typed GameAction into the DragnCards WebSocket game_action payload.

    Returns a dict ready to pass to Channel.push("game_action", payload).
    """
    action_list, description = _to_dragncards(action)
    return {
        "action": action_list,
        "options": {"description": description},
        "timestamp": int(time.time() * 1000),
    }


def _to_dragncards(action: GameAction) -> tuple[list, str]:
    """Return (dragnlang_action_list, description)."""
    if isinstance(action, MoveCardAction):
        args: list = [
            "MOVE_CARD",
            action.card_id,
            action.dest_group_id,
            action.dest_stack_index,
        ]
        if action.dest_card_index != 0:
            args.append(action.dest_card_index)
        return (
            args,
            f"Move card {action.card_id} to {action.dest_group_id}[{action.dest_stack_index}]",
        )

    if isinstance(action, DrawCardAction):
        return (
            ["DRAW_CARD", action.player_n, action.count],
            f"{action.player_n} draws {action.count} card(s)",
        )

    if isinstance(action, NextStepAction):
        return ["NEXT_STEP"], "Advance to next step"

    if isinstance(action, PrevStepAction):
        return ["PREV_STEP"], "Go back to previous step"

    if isinstance(action, SetCardPropertyAction):
        path = f"/cardById/{action.card_id}/{action.property_path}"
        return (
            ["SET", path, action.value],
            f"Set {action.property_path} on card {action.card_id}",
        )

    if isinstance(action, RawAction):
        return action.action_list, action.description

    raise ValueError(f"Unknown action type: {type(action)}")
