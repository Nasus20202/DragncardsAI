## Context

`prompt_player_agent` currently accepts arbitrary coordinator prose, while an orchestrated seat is a persistent session whose prior prompts and tool exchanges are replayed. The old reference described a DragnCards-only hand-written board template with fields such as maximum HP and target threat that are not guaranteed by the normalized state. It also told the coordinator to decide which details belonged in the prompt, leaving room for stale reports, inferred values, and choice coaching. DRA-83 supplies the platform-neutral Marvel state contract: `playRound`, `phase`, `phaseLabel`, `mode`, `players`, `zones`, optional `pendingSeats`, and optional authoritative `villainHitPoints`.

## Goals and non-goals

**Goals:**

- Make one platform-neutral player prompt envelope that carries only verified current state and engine-owned decisions.
- Preserve the Marvel state normalizer as the sole source for board facts, including main-scheme and side-scheme threat/effect fields.
- Make a persistent seat's current checkpoint override all replayed context on every invocation.
- Stop on an unresolved missing or contradictory checkpoint rather than allowing a guessed prompt or action.
- Prevent a threat value or stale HP/stage fact from becoming a terminal villain claim.
- Ensure the contract is visible to the coordinator through the skill reference, tool catalogue, and player-seat system prompt.

**Non-goals:**

- No state reads, normalizer changes, game action changes, or engine option semantics.
- No changes to the player strategy corpus, evaluator, history store, or recorded event schema.
- No machine parsing of opaque `phaseLabel` text or synthesis of printed card values.

## Decisions

### Use a single data-boundary prompt envelope

`references/player-turn-prompt.md` becomes the sole template for ordinary turns and a compact variant for recovery/engine decisions. Its state block is the complete normalized `get_game_state` object, and its engine block is the exact current `list_game_options` response when the platform supplies one. The surrounding prose is limited to seat scope, tool ownership, freshness handling, and return format. This removes the old fixed board fields that encouraged the coordinator to fabricate values.

For Marvel LCG, option ids, target identifiers, payment data, prompt ids, and prompt versions remain engine output. The coordinator may schedule the seat but cannot rewrite the engine prompt into a preferred choice. DragnCards records that no enumerated engine prompt applies and relies on its normalized state and platform reference.

### Treat normalized state as authoritative and sparse

The prompt contract names the exact neutral locations for active schemes and insists that omitted values remain omitted. `zones.sharedMainScheme[0].tokens.threat` is the main-scheme source; `zones.sharedSideSchemes` is the side-scheme source; and `villainHitPoints` is used only when present. `phase` is the only phase classifier. A present `pendingSeats` list constrains which seat can be scheduled. No current value is copied from a seat report, previous prompt, raw world descriptor, printed card memory, or arithmetic over an absent field.

### Invalidate persistent seat memory by precedence

The runtime adds a dedicated player-session contract to the subagent system prompt only when the session metadata identifies a seat. The immutable system instruction states that prior transcript data is historical, the current prompt checkpoint wins, one fresh authoritative state read is allowed for an absent/incomplete/contradictory block, and the seat must stop when the fresh read does not resolve the problem. The contract is inserted before persona text, so a user-authored persona cannot weaken it. Generic subagents retain their existing system prompt.

### Gate terminal claims on state mode

Both the reference and player-session system contract require `mode=win` or `mode=loss`, or an explicitly terminal current engine response, before reporting a terminal outcome. Missing `villainHitPoints` never means zero, and a main-scheme threat at its target does not establish villain defeat. The verified Rhino regression is documented as three ongoing checkpoints (`9/14`, `12/14`, and `14/14`) with `villainHitPoints=19` and `mode=in progress`.

### Keep the runtime discoverable

The orchestrator `SKILL.md` links the prompt contract and tells the coordinator to load it for every seat. Platform round-loop references point to the same envelope. The `prompt_player_agent` built-in description repeats the authority and freshness requirements so the contract survives skill-loading mistakes. `PromptRunService` passes `player_session=True` when constructing a seat's system prompt, making the memory contract part of every actual seat invocation rather than documentation alone.

## Risks and mitigations

- A model may still emit an invalid report. The coordinator must re-read normalized state before accepting it, and the existing seat/report guards keep output untrusted.
- A platform may omit a fact. The sparse contract explicitly reports it as unavailable and stops when it is required, rather than restoring an old value.
- Persistent transcripts become larger. The contract does not disable memory; it makes replay subordinate to the fresh checkpoint while preserving existing session behavior.
