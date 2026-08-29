## Why

Marvel evaluations currently trust a judge's prose even when the recorded normalized board disproves the claimed effect. That produces positive scores for unchanged threat and for the move whose resulting 12/14-to-14/14 transition loses the game, while the evidence needed to separate a player's mistake from a coordinator-supplied rule is difficult to identify after the fact.

## What Changes

- Validate Marvel move verdicts against the authoritative normalized state immediately before and after the move.
- Treat an observed terminal loss or win transition as authoritative move evidence, with loss taking priority over stale or fabricated positive reasoning.
- Detect claimed main-scheme threat removal and remove threat-management credit when the authoritative main-scheme threat is unchanged.
- Preserve coordinator-provided prompts and provenance on resolved player moves, and present that source explicitly to the evaluator so a conflicting rule is attributed to the coordinator rather than the player.
- Persist the complete resolved Marvel enumerated option identity (`id`, `name`, and `event`) from the successful option listing in the durable history payload; never reconstruct it from a generic action name or model-authored arguments.
- Keep the existing verdict payload fields and hidden-information projection unchanged; evidence corrections are expressed through existing scores, rationale, and flags.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-move-evaluation`: require authoritative Marvel before/after effect validation, terminal outcome priority, coordinator provenance, and durable enumerated option identity.
- `history-event-store`: preserve coordinator provenance and resolved Marvel option identity as durable, forward-compatible agent-move payload data.

## Non-goals

- Do not change Marvel game rules, option legality, state normalization, or the vendored engine.
- Do not change the DRA-81 strategy skill or DRA-84 orchestrator prompt/reference files.
- Do not expose hidden cards, private hand data, raw engine payloads, or opaque phase labels to the evaluator.
- Do not change the public verdict schema or rewrite verdicts already stored in history.
