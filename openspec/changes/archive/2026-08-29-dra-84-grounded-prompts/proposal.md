## Why

The orchestrator can send a persistent player seat a stale or coordinator-authored board summary. In the recorded Rhino game that boundary failure turned a still-live villain into a false terminal result and coached the table away from threat prevention. DRA-83 now exposes the authoritative normalized Marvel state, so prompts must consume that contract directly and treat persistent transcript data as historical.

## What Changes

- Make `player-turn-prompt.md` the single prompt envelope for both supported platforms.
- Require each seat prompt to carry the latest normalized `get_game_state` checkpoint and, for `marvel-lcg`, the exact current `list_game_options` response.
- Prohibit coordinator-authored rules, statistics, card facts, recommended choices, and inferred outcomes; omitted normalized fields remain unreported.
- Require one bounded fresh state read for missing or contradictory authority, followed by a stop when the contradiction remains.
- Define a persistent player-session memory contract that invalidates prior prompts, tool results, reports, and cached board facts at every invocation.
- Gate terminal reporting on normalized `mode=win|loss` or an explicitly terminal current engine response, including the Rhino `9/14`, `12/14`, `14/14` threat regression where villain HP remains present.
- Inject the memory and terminal contract into the runtime system prompt for seat sessions and update the discoverable `prompt_player_agent` tool description.
- Add focused tests for skill discoverability, forbidden coaching, the final Rhino threat sequence, and persistent-session stale-fact invalidation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: define authoritative player-turn prompt construction, persistent seat-session memory invalidation, and state-gated terminal reporting.

## Non-goals

- Do not change the DRA-81 Marvel play strategy or any game-service state normalization.
- Do not change eval-service or history-service behavior.
- Do not add a second game-state representation, infer values omitted by the normalizer, or change either platform's move semantics.
- Do not let the coordinator choose or execute a hero's move on behalf of a seat.
