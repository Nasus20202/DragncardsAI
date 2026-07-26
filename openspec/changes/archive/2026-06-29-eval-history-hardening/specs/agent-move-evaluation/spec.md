## ADDED Requirements

### Requirement: Verdict identity reflects the judge configuration

A verdict's history identity SHALL incorporate the resolved judge configuration (model, provider, prompt override, skills, reasoning), so that a forced re-evaluation of the same target with a DIFFERENT judge is recorded as a distinct verdict rather than discarded by history deduplication, while an identical re-evaluation still deduplicates.

#### Scenario: Forced re-eval with a different judge is recorded

- WHEN a target already has a verdict and is re-evaluated with `force` using a different judge model or prompt
- THEN a new, distinct verdict event is committed to history (not dropped by dedup)

#### Scenario: Identical re-eval still dedupes

- WHEN the same target is evaluated twice with the same judge configuration
- THEN the verdict is stored exactly once

### Requirement: Cancellation prevents verdict write-back

A target that is cancelled before or during evaluation SHALL NOT have a verdict written to history.

#### Scenario: Cancel before the task registers

- WHEN a target is cancelled in the window between being claimed (`running`) and its task registering as in-flight
- THEN no verdict is written to history for that target

### Requirement: Bounded judge input

The judge input SHALL be bounded by a configurable limit; when the assembled game timeline/state exceeds it, the largest content is truncated before being sent to the model, and the truncation is logged.

#### Scenario: Large game does not overflow a small model

- WHEN a whole-game (or large) evaluation would exceed the configured input bound
- THEN the input is truncated to fit and the truncation is recorded, rather than sending an oversized prompt

### Requirement: Hardened evaluation endpoints

The eval-service SHALL restrict CORS to a configurable allowlist (not `*`), validate `game_id` against a strict pattern at the route boundary, and url-encode `game_id` in outbound service-to-service URLs.

#### Scenario: Malformed game id rejected

- WHEN a request carries a `game_id` that does not match the allowed pattern
- THEN it is rejected at the boundary before any database or outbound-HTTP use
