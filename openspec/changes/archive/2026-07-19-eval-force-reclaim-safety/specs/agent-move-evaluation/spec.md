## MODIFIED Requirements

### Requirement: Idempotent evaluation with explicit re-evaluation
The eval-service SHALL evaluate each target at most once by default, deduplicating on `(game_id, target_seq, scope)` where `scope` is `move` or `round`, using a durable claim so that repeated requests and concurrent workers do not produce a second judge call for the same target — UNLESS the user explicitly requests re-evaluation (force), in which case a fresh verdict SHALL be produced. When a force re-evaluation resets a target that is still being evaluated, the eval-service SHALL cancel the in-flight evaluation before a fresh one starts, so at most one evaluation of a target is ever in flight and no stale verdict is written alongside the fresh one.

#### Scenario: Repeated request is not re-evaluated by default
- **WHEN** a target `(game_id, target_seq, scope)` that already has a verdict is requested again without the force option
- **THEN** the eval-service SHALL NOT issue a second judge call and SHALL return the existing verdict

#### Scenario: Explicit re-evaluation produces a fresh verdict
- **WHEN** a user requests evaluation of an already-evaluated target with the force/re-evaluate option
- **THEN** the eval-service SHALL issue a new judge call and write a fresh verdict event

#### Scenario: Concurrent claims resolve to a single evaluation
- **WHEN** two workers attempt to evaluate the same `(game_id, target_seq, scope)` concurrently
- **THEN** exactly one SHALL win the durable claim and perform the evaluation and the other SHALL treat the target as already claimed

#### Scenario: Force re-claim during a running evaluation writes a single verdict
- **WHEN** a force re-evaluation resets a target from `running` back to `pending` while a worker is still mid-evaluation on that same target (already past the `running` re-check)
- **THEN** the eval-service SHALL cancel the in-flight task so that exactly one verdict is written to history for that target — the fresh evaluation's verdict — and the stale evaluation's write-back SHALL NOT be committed

#### Scenario: Force re-claim keeps the fresh task cancellable
- **WHEN** a stale evaluation task finishes its cleanup after a force re-claim has registered a new in-flight task for the same target
- **THEN** the stale task's cleanup SHALL NOT evict the newer task from the in-flight registry, so the fresh task remains cancellable

### Requirement: Verdict identity reflects the judge configuration

A verdict's history identity SHALL incorporate the resolved judge configuration (model, provider, prompt override, skills, reasoning), so that a forced re-evaluation of the same target with a DIFFERENT judge is recorded as a distinct verdict rather than discarded by history deduplication, while an identical re-evaluation still deduplicates. The judge configuration's identity SHALL be independent of the ORDER of the selected skills, so that the same skill set in a different order is treated as identical.

#### Scenario: Forced re-eval with a different judge is recorded

- WHEN a target already has a verdict and is re-evaluated with `force` using a different judge model or prompt
- THEN a new, distinct verdict event is committed to history (not dropped by dedup)

#### Scenario: Identical re-eval still dedupes

- WHEN the same target is evaluated twice with the same judge configuration
- THEN the verdict is stored exactly once

#### Scenario: Re-eval with reordered skills still dedupes

- WHEN the same target is evaluated twice with the same skill SET supplied in a different order (and all other judge settings identical)
- THEN the two evaluations produce the same idempotency key and the verdict is stored exactly once (no spurious second event)
