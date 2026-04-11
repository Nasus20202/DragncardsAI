"""Router: meta endpoints (liveness check, action catalogue)."""

from __future__ import annotations

from fastapi import APIRouter

from game_service.api.models import (
    ActionSchema,
    DragnLangArg,
    DragnLangOp,
    HealthResponse,
    ListActionsResponse,
)
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

router = APIRouter(tags=["meta"])

# All concrete action types in the order they should be presented to consumers.
ACTION_TYPES = [
    NextStepAction,
    PrevStepAction,
    DrawCardAction,
    MoveCardAction,
    SetCardPropertyAction,
    SetPlayerCountAction,
    LoadCardsAction,
    UnloadCardsAction,
    RawAction,
]

# ---------------------------------------------------------------------------
# Curated DragnLang op catalogue
# Each entry is the authoritative signature from the .ex source files.
# ---------------------------------------------------------------------------

RAW_OPS: list[DragnLangOp] = [
    # --- Card & stack movement ---
    DragnLangOp(
        op="SHUFFLE_GROUP",
        description="Shuffle all stacks in the named group.",
        args=[
            DragnLangArg(
                name="groupId",
                type="string",
                description="ID of the group to shuffle, e.g. 'sharedEncounterDeck'",
            )
        ],
        returns="game state",
        example=["SHUFFLE_GROUP", "sharedEncounterDeck"],
    ),
    DragnLangOp(
        op="MOVE_CARD",
        description="Move a card to a different group/position. Runs postMoveCardActionList automation if defined.",
        args=[
            DragnLangArg(
                name="cardId", type="string", description="ID of the card to move"
            ),
            DragnLangArg(
                name="destGroupId", type="string", description="Destination group ID"
            ),
            DragnLangArg(
                name="destStackIndex",
                type="number",
                description="Stack index in destination; -1 to append at end",
            ),
            DragnLangArg(
                name="destCardIndex",
                type="number",
                description="Card index within destination stack (0 = top)",
                optional=True,
            ),
        ],
        returns="game state",
        example=["MOVE_CARD", "$CARD_ID", "player1Discard", -1],
    ),
    DragnLangOp(
        op="MOVE_STACK",
        description="Move a stack (with all its attachments) to a destination group. If the destination does not allow attachments, the stack is split.",
        args=[
            DragnLangArg(
                name="stackId", type="string", description="ID of the stack to move"
            ),
            DragnLangArg(
                name="destGroupId", type="string", description="Destination group ID"
            ),
            DragnLangArg(
                name="destStackIndex",
                type="number",
                description="Index in destination; -1 to append",
            ),
            DragnLangArg(
                name="options",
                type="object",
                description="Optional: {combine: 'left'|'right'|'on_top'}",
                optional=True,
            ),
        ],
        returns="game state",
        example=["MOVE_STACK", "$STACK_ID", "sharedVillain", -1],
    ),
    DragnLangOp(
        op="MOVE_STACKS",
        description="Move the top N stacks from one group to another.",
        args=[
            DragnLangArg(
                name="origGroupId", type="string", description="Source group ID"
            ),
            DragnLangArg(
                name="destGroupId", type="string", description="Destination group ID"
            ),
            DragnLangArg(
                name="topN",
                type="number",
                description="Number of stacks to move; -1 for all",
                optional=True,
            ),
            DragnLangArg(
                name="position",
                type="string",
                description="'shuffle' (default) | 'top' | 'bottom'",
                optional=True,
            ),
        ],
        returns="game state",
        example=["MOVE_STACKS", "player1Hand", "player1Discard", -1],
    ),
    DragnLangOp(
        op="ATTACH_CARD",
        description="Attach a card onto the stack of another card.",
        args=[
            DragnLangArg(
                name="cardId", type="string", description="ID of the card to attach"
            ),
            DragnLangArg(
                name="destCardId",
                type="string",
                description="ID of the card to attach onto",
            ),
        ],
        returns="game state",
        example=["ATTACH_CARD", "$ATTACHMENT_CARD_ID", "$TARGET_CARD_ID"],
    ),
    DragnLangOp(
        op="DELETE_CARD",
        description="Permanently remove a card from the game. Also removes the stack if it becomes empty.",
        args=[
            DragnLangArg(
                name="cardId", type="string", description="ID of the card to delete"
            )
        ],
        returns="game state",
        example=["DELETE_CARD", "$CARD_ID"],
    ),
    DragnLangOp(
        op="DRAW_CARD",
        description="Draw N cards from a player's deck to their hand.",
        args=[
            DragnLangArg(
                name="num",
                type="number",
                description="Number of cards to draw (default 1)",
                optional=True,
            ),
            DragnLangArg(
                name="playerI",
                type="string",
                description="Player identifier, e.g. 'player1' (default: active player)",
                optional=True,
            ),
        ],
        returns="game state",
        example=["DRAW_CARD", 5, "player1"],
    ),
    # --- Shuffling ---
    DragnLangOp(
        op="SHUFFLE_TOP_X",
        description="Randomly reorder only the top X cards of a group, leaving the rest in place.",
        args=[
            DragnLangArg(
                name="groupId", type="string", description="Group to partially shuffle"
            ),
            DragnLangArg(
                name="x", type="number", description="Number of top cards to shuffle"
            ),
        ],
        returns="game state",
        example=["SHUFFLE_TOP_X", "sharedEncounterDeck", 3],
    ),
    DragnLangOp(
        op="SHUFFLE_BOTTOM_X",
        description="Randomly reorder only the bottom X cards of a group, leaving the rest in place.",
        args=[
            DragnLangArg(
                name="groupId", type="string", description="Group to partially shuffle"
            ),
            DragnLangArg(
                name="x", type="number", description="Number of bottom cards to shuffle"
            ),
        ],
        returns="game state",
        example=["SHUFFLE_BOTTOM_X", "sharedEncounterDeck", 3],
    ),
    # --- Visibility / browsing ---
    DragnLangOp(
        op="LOOK_AT",
        description="Open the browse window for a player and set the peeking visibility of the top N cards in a group.",
        args=[
            DragnLangArg(
                name="playerI",
                type="string",
                description="Player to open the browse window for, e.g. 'player1'",
            ),
            DragnLangArg(name="groupId", type="string", description="Group to browse"),
            DragnLangArg(
                name="topN",
                type="number",
                description="Number of cards to peek; -1 for all",
            ),
            DragnLangArg(
                name="visibility",
                type="boolean",
                description="True to reveal, false to hide",
            ),
        ],
        returns="game state",
        example=["LOOK_AT", "player1", "sharedEncounterDeck", 3, True],
    ),
    DragnLangOp(
        op="STOP_LOOKING",
        description="Close the browse window for a player. By default also hides all peeked cards.",
        args=[
            DragnLangArg(
                name="playerI",
                type="string",
                description="Player whose browse window to close",
            ),
            DragnLangArg(
                name="option",
                type="string",
                description="'hide' (default) or 'keepPeeking' to retain card visibility",
                optional=True,
            ),
        ],
        returns="game state",
        example=["STOP_LOOKING", "player1"],
    ),
    DragnLangOp(
        op="SELECT_CARDS",
        description="Highlight a set of cards as selected in the multi-select GUI for one or more players.",
        args=[
            DragnLangArg(
                name="targetPlayerI",
                type="string or list",
                description="Player identifier or list of identifiers, e.g. 'player1'",
            ),
            DragnLangArg(
                name="selectedCards",
                type="list",
                description="List of card IDs to select; empty list clears selection",
            ),
        ],
        returns="game state",
        example=["SELECT_CARDS", "player1", ["$CARD_ID_1", "$CARD_ID_2"]],
    ),
    # --- State mutation ---
    DragnLangOp(
        op="SET",
        description="Set a value at a slash-delimited path in the game state. Triggers automations listening to that path.",
        args=[
            DragnLangArg(
                name="path",
                type="string",
                description="Slash-separated path, e.g. '/numPlayers' or '/cardById/$CARD_ID/tokens/damage'",
            ),
            DragnLangArg(
                name="value", type="any", description="New value to set at the path"
            ),
        ],
        returns="game state",
        example=["SET", "/cardById/$CARD_ID/tokens/damage", 3],
    ),
    DragnLangOp(
        op="UNSET",
        description="Remove a key and its value from the game state at the given path. Does not trigger automations.",
        args=[
            DragnLangArg(
                name="path", type="string", description="Slash-separated path to remove"
            )
        ],
        returns="game state",
        example=["UNSET", "/cardById/$CARD_ID/tokens/damage"],
    ),
    DragnLangOp(
        op="INCREASE_VAL",
        description="Increase a numeric value at a path by a delta. Triggers automations. Treats null as 0.",
        args=[
            DragnLangArg(
                name="path",
                type="string",
                description="Slash-separated path to the numeric value",
            ),
            DragnLangArg(name="delta", type="number", description="Amount to add"),
        ],
        returns="game state",
        example=["INCREASE_VAL", "/cardById/$CARD_ID/tokens/damage", 1],
    ),
    DragnLangOp(
        op="DECREASE_VAL",
        description="Decrease a numeric value at a path by a delta. Triggers automations. Treats null as 0.",
        args=[
            DragnLangArg(
                name="path",
                type="string",
                description="Slash-separated path to the numeric value",
            ),
            DragnLangArg(name="delta", type="number", description="Amount to subtract"),
        ],
        returns="game state",
        example=["DECREASE_VAL", "/cardById/$CARD_ID/tokens/damage", 1],
    ),
    # --- Card queries ---
    DragnLangOp(
        op="ONE_CARD",
        description="Find the first card matching a condition. Returns the card object or null.",
        args=[
            DragnLangArg(
                name="variableName",
                type="string",
                description="Variable name (starting with $) assigned to each card during evaluation, e.g. '$CARD'",
            ),
            DragnLangArg(
                name="condition",
                type="DragnLang code",
                description="Expression evaluated per card; return true to match",
            ),
        ],
        returns="card object or null",
        example=[
            "ONE_CARD",
            "$CARD",
            ["EQUAL", "$CARD.databaseId", "c92a3f54-6113-5ef4-8a82-f8a366cf499c"],
        ],
    ),
    DragnLangOp(
        op="FILTER_CARDS",
        description="Return all cards matching a condition.",
        args=[
            DragnLangArg(
                name="varName",
                type="string",
                description="Variable name (starting with $) assigned to each card, e.g. '$CARD'",
            ),
            DragnLangArg(
                name="condition",
                type="DragnLang code",
                description="Expression evaluated per card; return true to include",
            ),
        ],
        returns="list of card objects",
        example=["FILTER_CARDS", "$CARD", ["EQUAL", "$CARD.controller", "player1"]],
    ),
    DragnLangOp(
        op="GET_CARD",
        description="Return the card object at a specific position within a group.",
        args=[
            DragnLangArg(name="groupId", type="string", description="Group to look in"),
            DragnLangArg(
                name="stackIndex", type="number", description="Stack index (0-based)"
            ),
            DragnLangArg(
                name="cardIndex",
                type="number",
                description="Card index within the stack (0 = top)",
            ),
        ],
        returns="card object or null",
        example=["GET_CARD", "player1Deck", 0, 0],
    ),
    # --- Prompts ---
    DragnLangOp(
        op="PROMPT",
        description="Display a named prompt (from gameDef.prompts) to one or more players.",
        args=[
            DragnLangArg(
                name="targetPlayerI",
                type="string or list",
                description="Player or list of players to prompt",
            ),
            DragnLangArg(
                name="promptId",
                type="string",
                description="Key into gameDef.prompts, or built-in 'confirmAutomationYN'",
            ),
        ],
        returns="game state",
        example=["PROMPT", "player1", "confirmAutomationYN"],
    ),
    # --- Logging ---
    DragnLangOp(
        op="LOG",
        description="Append a message to the game log. Supports {{expr}} interpolation.",
        args=[
            DragnLangArg(
                name="message",
                type="string",
                description="Message to log (any number of args are concatenated)",
            )
        ],
        returns="game state",
        example=["LOG", "Player drew a card: ", "$CARD.A.name"],
    ),
    # --- Control flow ---
    DragnLangOp(
        op="COND",
        description="Evaluate condition/code pairs in order; execute the code after the first true condition.",
        args=[
            DragnLangArg(
                name="condition1", type="DragnLang code", description="First condition"
            ),
            DragnLangArg(
                name="code1",
                type="DragnLang code",
                description="Code to run if condition1 is true",
            ),
        ],
        returns="result of matching branch, or unchanged game state",
        example=[
            "COND",
            ["EQUAL", "$GAME.numPlayers", 1],
            ["LOG", "Solo game"],
            ["EQUAL", "$GAME.numPlayers", 2],
            ["LOG", "2-player game"],
        ],
    ),
    DragnLangOp(
        op="FOR_EACH_VAL",
        description="Iterate over a list, assigning each element to a variable, and evaluate a function for each.",
        args=[
            DragnLangArg(
                name="valName",
                type="string",
                description="Variable name (starting with $) for each element",
            ),
            DragnLangArg(name="list", type="list", description="List to iterate over"),
            DragnLangArg(
                name="function",
                type="DragnLang code",
                description="Code evaluated for each element",
            ),
        ],
        returns="result of final function call",
        example=[
            "FOR_EACH_VAL",
            "$PLAYER",
            ["LIST", "player1", "player2"],
            ["DRAW_CARD", 1, "$PLAYER"],
        ],
    ),
    DragnLangOp(
        op="WHILE",
        description="Repeatedly execute code while a condition is true.",
        args=[
            DragnLangArg(
                name="condition",
                type="DragnLang code",
                description="Evaluated before each iteration; loop exits when false",
            ),
            DragnLangArg(
                name="code",
                type="DragnLang code",
                description="Code executed each iteration",
            ),
        ],
        returns="game state",
        example=[
            "WHILE",
            ["NOT", ["GROUP_EMPTY", "player1Deck"]],
            ["DRAW_CARD", 1, "player1"],
        ],
    ),
    DragnLangOp(
        op="ACTION_LIST",
        description="Execute a named action list from gameDef.actionLists, or evaluate an inline action list.",
        args=[
            DragnLangArg(
                name="actionListIdOrCode",
                type="string or DragnLang code",
                description="Named action list ID from gameDef.actionLists, or inline code to evaluate",
            )
        ],
        returns="result of the evaluated action list",
        example=["ACTION_LIST", "someNamedActionList"],
    ),
    # --- Randomness ---
    DragnLangOp(
        op="RANDOM_INT",
        description="Return a uniformly random integer between min and max (inclusive). Does not modify game state.",
        args=[
            DragnLangArg(
                name="min", type="number", description="Minimum value (inclusive)"
            ),
            DragnLangArg(
                name="max", type="number", description="Maximum value (inclusive)"
            ),
        ],
        returns="integer",
        example=["RANDOM_INT", 1, 6],
    ),
    DragnLangOp(
        op="CHOOSE_N",
        description="Return a random selection of N elements from a list, without replacement.",
        args=[
            DragnLangArg(name="list", type="list", description="List to sample from"),
            DragnLangArg(
                name="n", type="number", description="Number of elements to select"
            ),
        ],
        returns="list",
        example=["CHOOSE_N", ["LIST", "player1", "player2", "player3"], 1],
    ),
    # --- Variables ---
    DragnLangOp(
        op="DEFINE",
        description="Define a global variable that persists for the duration of the action list evaluation.",
        args=[
            DragnLangArg(
                name="varName",
                type="string",
                description="Variable name starting with $",
            ),
            DragnLangArg(name="value", type="any", description="Value to assign"),
        ],
        returns="game state",
        example=[
            "DEFINE",
            "$TARGET",
            ["ONE_CARD", "$C", ["EQUAL", "$C.groupId", "sharedVillain"]],
        ],
    ),
    # --- Game lifecycle ---
    DragnLangOp(
        op="RESET_GAME",
        description="Reset the current game to its initial state, running postNewGameActionList automation if defined.",
        args=[],
        returns="fresh game state",
        example=["RESET_GAME"],
    ),
    DragnLangOp(
        op="SAVE_GAME",
        description="Save the current game state as a replay for the current player.",
        args=[],
        returns="game state (unchanged)",
        example=["SAVE_GAME"],
    ),
]


def build_action_schemas() -> list[ActionSchema]:
    """Build ActionSchema list from all supported action model classes."""
    actions = []
    for model_cls in ACTION_TYPES:
        schema = model_cls.model_json_schema()
        type_val = model_cls.model_fields["type"].default
        doc = (model_cls.__doc__ or "").strip()
        actions.append(
            ActionSchema(
                type=type_val,
                description=doc,
                schema=schema,
            )
        )
    return actions


@router.get("/health", response_model=HealthResponse, operation_id="health")
async def health():
    """Simple liveness check."""
    return HealthResponse()


@router.get(
    "/actions",
    response_model=ListActionsResponse,
    operation_id="list_actions",
    summary="List all supported actions and DragnLang operations",
)
async def list_actions():
    """
    Return the full catalogue of everything an agent can pass to the
    execute_action endpoint.

    **`actions`** — typed action wrappers (next_step, draw_card, load_cards, etc.)
    Each has a `type` discriminator, description, and full JSON Schema.

    **`raw_ops`** — curated DragnLang operations available via the `raw` action type.
    Each entry has the op name, argument signatures, return type, and an example
    `action_list` ready to drop into `{"type": "raw", "action_list": [...]}`.

    To use a raw op: POST /games/{id}/actions with
      `{"type": "raw", "action_list": ["SHUFFLE_GROUP", "sharedEncounterDeck"]}`
    """
    return ListActionsResponse(actions=build_action_schemas(), raw_ops=RAW_OPS)
