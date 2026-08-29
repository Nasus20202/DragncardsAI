## Why

The rules-enforcing marvel-lcg engine reports authoritative villain, main-scheme, and side-scheme values in card descriptors. The current game-service projection drops active side schemes, leaves engine token names un-normalized, and fabricates a zero villain HP when no world-level HP field exists; that makes a live Rhino board look defeated or hides threat and effects from player and evaluation agents.

## What Changes

- Derive the Marvel villain's current hit points from the visible active villain card's authoritative `health` descriptor value, and omit `villainHitPoints` when no authoritative value is present.
- Normalize Marvel card info and counter/token names into the neutral sparse token vocabulary used by the DragnCards projection, including canonical `threat` on main and side schemes.
- Project the engine's active `area_schemes_side` cards into a shared neutral side-scheme zone, retaining public threat and effect fields such as Crisis, Hazard, and acceleration.
- Classify every valid Marvel engine phase, including Enemy Activation, into the existing neutral phase categories without changing the opaque `phaseLabel`.
- Add a deterministic Rhino checkpoint fixture and regression tests for villain HP, main-scheme threat, active side schemes/effects, and valid phase values.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `simplified-game-state`: require authoritative Marvel scalar and card projections, canonical scheme threat/effect fields, active side-scheme visibility, and valid Marvel phase normalization.

## Non-goals

- Do not change orchestrator prompts, planning, evaluator logic, or any Marvel move/option behavior.
- Do not change the vendored Marvel engine or infer printed values that the current world descriptor does not report.
- Do not expose hidden cards or private side-scheme metadata to a seat that cannot see it.
