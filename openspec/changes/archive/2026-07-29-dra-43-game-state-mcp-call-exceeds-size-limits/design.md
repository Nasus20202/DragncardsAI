# Design notes

## Why drop defaults instead of renaming

The fields `id`, `instanceId`, `name`, `currentSide`, `exhausted`,
`tokens`, `stackSize` are part of the public surface defined in
`openspec/specs/simplified-game-state/spec.md` and consumed by:

- the `marvel-champions-play` skill (skills/marvel-champions-play/...)
- the agent-orchestrator's MCP prompt that describes state shape
- the dashboard's live board view (services/dashboard/...)

Renaming to short aliases (e.g. `n` for `name`, `i` for `id`) would
shrivel the wire format further but it would also require updating
every reader in three places and rewriting the spec. The default-drop
approach gets most of the bytes back without touching the field
names or the consumer surface.

## Why a dict, not `model_dump(exclude_defaults=True)` directly

`_simplify_marvel_state` currently returns a `SimplifiedGameState`
Pydantic model. Pydantic will fill in defaults on validation, so by
the time `model_dump` runs, the defaults are present and
`exclude_defaults=True` would only drop them if we compare against
the schema. Pydantic does support `model_dump(exclude_defaults=True)`
on the model itself, but that operates on the model's own defaults
(`"Unknown"`, `"A"`, `False`, `dict()`) which happens to be exactly
what we want — we only need to set fields when they are *meaningful*,
and let Pydantic decide what the default is.

The chosen path: build the visible card as a dict with only the
meaningful fields, hand it to `SimplifiedCard(...)`, and call
`model_dump(exclude_defaults=True)` on the result. Pydantic compares
each value to the schema default and omits the field when it matches.

For HIDDEN entries, the dict is even smaller: just `name` and
`stackSize`. Both are non-default in the Pydantic sense, so they
will always be emitted.

## Why keep `stackSize` even when it is 1

`stackSize: 1` is the default in `SimplifiedCard`, but a deck
contains many cards with `stackSize > 1` (cards under a single
stack). The agent needs that count to know how many cards are hidden
under the top card. Emitting `stackSize: 1` is harmless (3 chars) and
keeps the field shape uniform. Keeping it always-present also avoids
the consumer having to special-case "is stackSize missing or 1?".

## What does NOT change

- The raw state route `GET /games/{id}/state/raw` keeps its full,
  un-simplified payload. That is the escape hatch for any agent or
  operator that genuinely needs every DragnCards field.
- The `execute_action` endpoint still returns the simplified state
  in its `state` field, but the body is now compact.
- The snapshot import/export endpoints (`/snapshot` GET and PUT) keep
  the raw `game` payload. They are not the path agents hit on every
  turn, and shrinking them would silently corrupt any operator who
  has a stored snapshot they want to reload.
- The MCP tool names and the operation IDs are unchanged. The change
  is purely about the *value* the tools return, not the tools
  themselves.
