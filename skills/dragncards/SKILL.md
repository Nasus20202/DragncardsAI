---
name: dragncards
description: Skill for writing, debugging, and extending DragnCards plugins and DragnLang game logic, including action lists, automation rules, and game state manipulation.
metadata:
  version: "1.0"
---

## Scope: this is not a play skill

This skill is for **building and debugging the platform** — writing DragnLang action lists, plugin JSON, and automation rules, and reading the engine's source when something does not behave. It sits in the same skill root as the Marvel Champions play skills because that root is where all domain knowledge lives, not because it is one of them.

If you are playing a game, this is the wrong file:

| You want to...                                         | Load                                |
| ------------------------------------------------------ | ------------------------------------- |
| Take a hero's turn through the game-service tools      | `marvel-champions-play`             |
| Run a whole game across several seats                  | `marvel-champions-orchestrator`     |
| Settle a rules question                                | `marvel-champions-rules-reference`  |

**DragnLang is not a way to act on a live table.** The operations below are what the engine evaluates; they are not a back door around the typed game-service tools. A player agent has no `raw_action` and should not go looking for one — the typed tools exist because an unvalidated action list with a typo corrupts the table for every seat, and nothing rolls it back. Reading this skill to understand *why* a tool behaves as it does is fine; using it to hand-write an action list against a game in progress is not.

---

DragnCards is a browser-based platform for playing card games. A game is defined by a **plugin** (a set of JSON files) and an **engine** (a React frontend + Elixir/Phoenix backend). The frontend and backend communicate via Phoenix Channels (WebSocket) and an HTTP REST API.

Game logic is written in **DragnLang**, a custom LISP-like scripting language interpreted by the Elixir backend. Action lists are arrays of arrays that modify the game state, log messages, draw cards, move cards, and automate game rules.

## Architecture

```
Frontend (React)  <-- WebSocket (Phoenix Channels) -->  Backend (Elixir/Phoenix)
       |                                                        |
       |-- gameBroadcast("game_action", action)                 |-- Evaluate.evaluate()
       |                                                        |-- GameUI.update_state()
       |-- request_state                                        |-- broadcast("state_update")
```

- **Frontend**: React app in `external/dragncards/frontend/`. Sends `game_action` events. Receives `state_update` / `current_state` broadcasts.
- **Backend**: Elixir app in `external/dragncards/backend/`. Evaluates DragnLang. Maintains game state in-memory per room (GenServer).
- **Plugin**: JSON files in `external/dragncards-mc-plugin/json/` defining cards, groups, layouts, action lists, automation rules, and functions.

## DragnLang Fundamentals

DragnLang is a **LISP-like scripting language** for manipulating the game state. It is evaluated by `DragnCardsGame.Evaluate.evaluate/3` in the backend.

### Syntax

- Every operation is an **array**: `["OPERATION", arg1, arg2, ...]`
- Action lists are **arrays of operations**: `[op1, op2, op3]`
- Values can be **literals** (strings, numbers, booleans, objects, lists), **variables** (`$VAR`), or **nested operations**.

### Action List Execution

Action lists are sent from the frontend via the `game_action` channel event:

```json
{
  "action": "evaluate",
  "options": {
    "action_list": [...],
    "player_ui": {...},
    "description": "optional description"
  }
}
```

The backend evaluates the action list and broadcasts a `state_update` (delta) to all connected clients.

## Variables

Variables are scoped. Use `"VAR"` for local scope, `"DEFINE"` for global (persists across the whole game session).

| Variable           | Description                                                               |
| ------------------ | ------------------------------------------------------------------------- |
| `$GAME`            | The entire game state map                                                 |
| `$PLAYER_N`        | The player identifier string (e.g., `"player1"`) who triggered the action |
| `$ALIAS_N`         | The alias (display name) of `$PLAYER_N`                                   |
| `$ACTIVE_CARD`     | The card currently targeted/selected by the player                        |
| `$ACTIVE_CARD_ID`  | ID of `$ACTIVE_CARD`                                                      |
| `$ACTIVE_FACE`     | The currently visible face of `$ACTIVE_CARD`                              |
| `$ACTIVE_GROUP_ID` | The group the active card belongs to                                      |
| `$ACTIVE_TOKENS`   | Tokens on the active card                                                 |
| `$PLAYER_ORDER`    | Ordered list of player identifiers                                        |
| `$CARD_BY_ID`      | Map of all cards by ID                                                    |
| `$GROUP_BY_ID`     | Map of all groups by ID                                                   |
| `$STACK_BY_ID`     | Map of all stacks by ID                                                   |
| `$PLAYER_DATA`     | Per-player data map                                                       |

## Core DragnLang Operations

### State Manipulation

| Operation      | Arguments     | Description                                            |
| -------------- | ------------- | ------------------------------------------------------ |
| `SET`          | `path, value` | Sets a value at a dot-separated path in the game state |
| `VAR`          | `name, value` | Defines a local variable                               |
| `DEFINE`       | `name, value` | Defines a global variable                              |
| `UPDATE_VAR`   | `name, value` | Updates an existing variable                           |
| `INCREASE_VAL` | `path, delta` | Increments a numeric value at a path                   |
| `DECREASE_VAL` | `path, delta` | Decrements a numeric value at a path                   |

### Control Flow

| Operation                  | Arguments                                   | Description                                                                                                       |
| -------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `COND`                     | `condition1, then1, condition2, then2, ...` | If-else chain. Evaluates conditions left-to-right. The first true condition's corresponding `then` block executes |
| `WHILE`                    | `condition, actionList`                     | Repeatedly executes `actionList` while `condition` is true                                                        |
| `FOR_EACH_VAL`             | `varName, list, actionList`                 | Iterates over `list`, binding each value to `varName`                                                             |
| `FOR_EACH_KEY_VAL`         | `keyName, valName, obj, actionList`         | Iterates over object keys/values                                                                                  |
| `FOR_EACH_START_STOP_STEP` | `var, start, stop, step, actionList`        | Numeric loop                                                                                                      |
| `ABORT`                    | `message`                                   | Stops execution and logs an error                                                                                 |

### Card & Stack Movement

| Operation          | Arguments                                                         | Description                                     |
| ------------------ | ----------------------------------------------------------------- | ----------------------------------------------- |
| `MOVE_CARD`        | `cardId, destGroupId, destStackIndex, [destCardIndex], [options]` | Moves a card to a new group/stack               |
| `MOVE_STACK`       | `stackId, destGroupId, destStackIndex`                            | Moves a whole stack                             |
| `MOVE_STACKS`      | `srcGroupId, destGroupId, numStacks, position`                    | Moves multiple stacks between groups            |
| `DRAW_CARD`        | `[num], [playerI]`                                                | Draws `num` cards from deck to hand             |
| `SHUFFLE_GROUP`    | `groupId`                                                         | Randomizes the order of stacks in a group       |
| `SHUFFLE_TOP_X`    | `groupId, num`                                                    | Shuffles the top N stacks in a group            |
| `SHUFFLE_BOTTOM_X` | `groupId, num`                                                    | Shuffles the bottom N stacks in a group         |
| `DELETE_CARD`      | `cardId`                                                          | Permanently removes a card from the game        |
| `LOAD_CARDS`       | `loadListId` or `loadList`                                        | Loads pre-built or raw card lists into the game |
| `UNLOAD_CARDS`     | (varies)                                                          | Removes loaded cards                            |

### Logging & UI

| Operation          | Arguments                       | Description                                                |
| ------------------ | ------------------------------- | ---------------------------------------------------------- |
| `LOG`              | `...messages`                   | Concatenates all arguments and adds a line to the game log |
| `PROMPT`           | `targetPlayer, promptId`        | Shows an interactive prompt to a player                    |
| `FADE_TEXT_CARD`   | `cardId, text`                  | Displays floating text on a card                           |
| `FADE_TEXT_GAME`   | `text`                          | Displays floating text on the game board                   |
| `FADE_TEXT_PLAYER` | `playerI, text`                 | Displays floating text for a player                        |
| `INPUT`            | `type, varName, label, default` | Prompts the user for input (used inside prompts)           |

### Targeting

| Operation      | Arguments | Description                                    |
| -------------- | --------- | ---------------------------------------------- |
| `TARGET`       | `cardId`  | Marks a card as targeted by the current player |
| `SELECT_CARDS` | `...`     | Prompts the user to select cards               |

### Math & Logic

| Operation                                                  | Arguments       | Description              |
| ---------------------------------------------------------- | --------------- | ------------------------ |
| `EQUAL`, `NOT_EQUAL`                                       | `a, b`          | Comparison               |
| `LESS_THAN`, `GREATER_THAN`, `LESS_EQUAL`, `GREATER_EQUAL` | `a, b`          | Numeric comparison       |
| `AND`, `OR`                                                | `...conditions` | Logical AND/OR           |
| `NOT`                                                      | `condition`     | Logical NOT              |
| `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE`, `MODULO`          | `a, b`          | Arithmetic               |
| `LENGTH`                                                   | `list`          | Returns list length      |
| `RANDOM_INT`                                               | `min, max`      | Returns a random integer |

### Functions & Action Lists

| Operation     | Arguments           | Description                                             |
| ------------- | ------------------- | ------------------------------------------------------- |
| `ACTION_LIST` | `actionListId`      | Executes a named action list from `gameDef.actionLists` |
| `FUNCTION`    | `funcName, ...args` | Calls a plugin-defined function                         |

### Automation

| Operation         | Arguments | Description                                                    |
| ----------------- | --------- | -------------------------------------------------------------- |
| `ADVANCE_TO_STEP` | `stepId`  | Advances the game stepId, triggering intermediate step changes |
| `NEXT_STEP`       |           | Advances to the next step in `stepOrder`                       |
| `PREV_STEP`       |           | Goes to the previous step                                      |

## Game State Structure

The game state is a large nested map. Key paths used with `SET`/`INCREASE_VAL`:

```
/cardById/:id/rotation
/cardById/:id/tokens/:tokenType
/cardById/:id/currentSide
/cardById/:id/peeking/:playerN
/groupById/:id/stackIds
/playerData/:playerN/hitPoints
/playerData/:playerN/handSize
/stepId
/roundNumber
```

## Plugin Files

Plugin configuration lives in JSON files under `external/dragncards-mc-plugin/json/`:

| File                        | Purpose                                                  |
| --------------------------- | -------------------------------------------------------- |
| `actionLists.json`          | Named DragnLang action lists                             |
| `automation.json`           | Automation rules (`gameRules` and card-specific `rules`) |
| `functions.json`            | Plugin-defined functions                                 |
| `groups.json`               | Card groups (decks, hand, play area, discard)            |
| `layouts.json`              | Table layout definitions                                 |
| `phases.json`, `steps.json` | Game phase and step definitions                          |
| `tokens.json`               | Token type definitions                                   |
| `cardTypes.json`            | Card type definitions                                    |
| `cardProperties.json`       | Card property schemas                                    |

## Automation Rules

Automation rules are defined in `automation.json`. They are triggered by state changes.

```json
{
  "automation": {
    "postLoadActionList": [...],
    "gameRules": {
      "ruleName": {
        "type": "trigger",
        "listenTo": ["/cardById/*/inPlay"],
        "condition": [...],
        "then": [...]
      }
    },
    "cards": {
      "databaseId": {
        "rules": {
          "ruleName": {
            "type": "passive",
            "listenTo": ["/cardById/:id/tokens/damage"],
            "condition": [...],
            "onDo": [...],
            "offDo": [...]
          }
        }
      }
    }
  }
}
```

### Rule Types

| Type          | Description                                                             |
| ------------- | ----------------------------------------------------------------------- |
| `trigger`     | Fires once when a condition becomes true                                |
| `passive`     | Fires `onDo` when condition becomes true, `offDo` when it becomes false |
| `entersPlay`  | Shorthand for `trigger` when a card enters play                         |
| `whileInPlay` | Shorthand for `passive` while a card is in play                         |

### Auto Run Settings

```
always   - Automatically executes when the condition is met
never    - Never auto-executes
prompt   - Prompts the user to run the rule
promptYN - Shows a Yes/No prompt
```

## Writing Action Lists

### Basic Example

```json
[
  ["LOG", "{{$ALIAS_N}} drew a card."],
  ["DRAW_CARD", 1, "$PLAYER_N"]
]
```

### Conditional Example

```json
[
  [
    "COND",
    ["LESS_THAN", ["LENGTH", "$GAME.groupById.player1Deck.stackIds"], 5],
    [
      ["LOG", "Deck is low!"],
      ["DRAW_CARD", 2, "player1"]
    ],
    ["TRUE"],
    [["DRAW_CARD", 1, "player1"]]
  ]
]
```

### Loop Example

```json
[
  [
    "FOR_EACH_VAL",
    "$CARD",
    "$GAME.groupById.player1Hand.parentCardIds",
    [["LOG", "Card: {{$CARD}}"]]
  ]
]
```

## Communication Over WebSocket

The Game Service connects via Phoenix Channels.

### Joining a Room

```
Topic: "room:<slug>"
Event: "phx_join"
```

On join, the server broadcasts `:current_state` with the full game state.

### Sending an Action

```
Event: "game_action"
Payload: {
  "action": "evaluate",
  "options": {
    "action_list": [...],
    "player_ui": {...},
    "description": "Draw a card"
  },
  "timestamp": 1715097600000
}
```

### Receiving State Updates

- `state_update` - Delta update after an action.
- `current_state` - Full state broadcast on join or explicit request.
- `send_update` - Replay step update payload.
- `go_to_replay_step` - Replay navigation.

## Key Files Reference

| Path                                                                             | Description                  |
| -------------------------------------------------------------------------------- | ---------------------------- |
| `external/dragncards/backend/lib/dragncards_game/evaluate/evaluate.ex`           | DragnLang interpreter        |
| `external/dragncards/backend/lib/dragncards_game/evaluate/functions/*.ex`        | Built-in functions           |
| `external/dragncards/backend/lib/dragncards_web/channels/room_channel.ex`        | WebSocket channel            |
| `external/dragncards/frontend/src/features/engine/hooks/useDoActionList.js`      | Frontend action dispatcher   |
| `external/dragncards/frontend/src/features/engine/functions/dragnActionLists.js` | Frontend action list factory |
| `external/dragncards-mc-plugin/json/actionLists.json`                            | Plugin action lists          |
| `external/dragncards-mc-plugin/json/automation.json`                             | Plugin automation rules      |
| `external/dragncards-mc-plugin/json/functions.json`                              | Plugin-defined functions     |
| `openspec/specs/dragncards/spec.md`                                              | Integration contract spec    |
