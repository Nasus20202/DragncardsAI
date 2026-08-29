## Why

The normalized Marvel state now exposes every active shared side scheme and its public effect indicators, but the player strategy still reasons mostly about the main scheme and treats side schemes as a generic cleanup item. That causes a player agent to miss Crisis blocking, underestimate acceleration and denial effects, and end a player phase without naming a deterministic next-phase lethal risk. The strategy reference needs an executable, observable-only threat-clock procedure aligned with the normalized state contract.

## What Changes

- Replace the existing aggregate threat heuristic with a step-by-step calculation of the minimum next villain-phase main-scheme threat from the active main scheme's current threat, explicit base placement, explicit acceleration, and known alter-ego scheme values.
- Require the agent to read `zones.sharedMainScheme[0]` and every card in `zones.sharedSideSchemes`, rank side schemes by their actual reported Crisis, Hazard, acceleration, hand/resource denial, and threat effects, and never infer an effect that is not present.
- Make every deferred side scheme carry a current-state reason (for example, a reported blocker, an explicitly insufficient thwart budget, or a known higher-risk threat line) rather than a generic intention.
- Replan threat control versus villain damage whenever a projected clock or side-scheme effect changes, and require a 9/14 checkpoint warning for deterministic next-phase lethal risk before the player phase is reported complete.
- Add deterministic focused regression coverage for multiple active side schemes, Crisis blocking main-scheme threat removal, unknown target/gain refusal, deferred-reason reporting, and the 9/14 warning.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `marvel-champions-play-skill`: strengthen observable side-scheme prioritization, next-villain-phase threat projection, uncertainty handling, and end-of-phase risk reporting.

## Non-goals

- Do not change the normalized game-state producer, game-service schemas, action tools, or platform harness references.
- Do not edit orchestrator prompts or round-loop references, evaluator/history code, or the shared Marvel rules corpus.
- Do not estimate hidden printed values, parse opaque phase labels, or turn the strategy reference into a runtime strategy engine.
