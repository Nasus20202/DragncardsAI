# `mulligan_draw_hand` must describe what it actually does

## Why

The MCP tool summary for `mulligan_draw_hand` reads:

> Discard any number of cards, then draw up to hand size — use for setup mulligan OR
> drawing cards to hand limit

It does not discard anything. The translated action list is a round-0 `LOG` line plus
`["DRAW_HAND", player_n, player_n]`, and `DRAW_HAND` only tops the hand up to the
player's current `handSize`. When the hand is already at or above `handSize` the tool is
a no-op.

The behaviour is correct — a discard-then-draw tool would have to guess which cards to
throw away, which is the agent's decision, not the harness's. The summary is what is
wrong, and it is the single most load-bearing piece of text the agent sees for this tool:
an agent that believes the summary calls it to "discard down to hand size", observes
nothing happen, and has cheated by keeping an oversized hand.

The `marvel-champions-play` skill already had to work around the bad summary, documenting
the tool as contradicting itself. With the summary fixed, that framing is obsolete.

## What Changes

- **game-service** — the `mulligan_draw_hand` endpoint summary (the MCP tool description)
  now states that it draws the player up to their hand size, discards nothing, and does
  nothing on a full hand, while keeping the existing "preferred over `draw_card`"
  guidance. The `MulliganDrawHandAction` docstring and `player_n` field description are
  corrected the same way, as is the stale translation comment claiming the action only
  draws on round 0 (only the log line is round-0 conditional).
- **skills/marvel-champions-play** — `SKILL.md` fact 9 and the `tool-reference.md` entry
  drop the "despite its summary" contradiction framing and simply state the behaviour.

No behaviour changes. The action list, the endpoint, and the MCP tool are untouched.

## Non-goals

- Making the tool actually discard. Choosing which cards to mulligan is the agent's job;
  the skill already instructs it to `move_card` them to `playerNDiscard` first.
- Auditing or rewording the other action summaries.
- The `shuffle_into_deck` defect documented alongside it in the same skill files.

## Impact

- Affected specs: `game-service` (the action-summary requirement).
- Affected code:
  `services/game-service/src/game_service/api/routers/game_action_helpers.py`,
  `services/game-service/src/game_service/logic/actions.py`,
  `skills/marvel-champions-play/SKILL.md`,
  `skills/marvel-champions-play/resources/tool-reference.md`.
- No API, schema, or migration changes. The OpenAPI `summary` and the MCP tool
  description text change; the operation id, path, and request model do not.
