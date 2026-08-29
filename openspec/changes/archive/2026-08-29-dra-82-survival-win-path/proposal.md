## Why

The player strategy currently compares damage with the current villain stage only and can call a short stage race safe even when later stages remain. It also treats a hero with only a few hit points as an incidental board detail, so a race that loses the team at the next villain phase can outrank a survivable threat-control line.

## What Changes

- Extend the Marvel player strategy reference with an authoritative full-villain-path calculation that includes the current stage's remaining hit points and every remaining later stage whose hit points are visible or explicitly looked up.
- Distinguish the current-stage `villainHitPoints` total from cumulative victory damage, preserving unknown later stages and hidden values instead of guessing them.
- Add an explicit survival-versus-race comparison using each hero's remaining health, known incoming damage, threat clock, remaining villain stages, board obligations, and available resources.
- Require a survival/threat-control replan when an explicit near-death line makes expected team loss greater than the value of continuing the damage race, while reserving automatic game-over handling for authoritative terminal state or actual defeat.
- Add deterministic regressions for a multi-stage Rhino position and a low-health hero whose survival line outranks the damage race.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `marvel-champions-play-skill`: make villain-race planning stage-aware and require health-aware survival/threat-control replanning.

## Non-goals

- Do not change normalized state production, game-service schemas, platform harnesses, orchestrator round-loop prompts, evaluator/history behavior, or the shared rules corpus.
- Do not add a runtime planner or infer hidden villain stages, printed hit points, incoming damage, resources, or card effects.
- Do not treat a low-health hero as defeated until authoritative state reports zero health or `mode=loss`.
