## MODIFIED Requirements

### Requirement: Parallel evaluation without in-memory state

The eval-service SHALL evaluate multiple targets concurrently, and the concurrency SHALL be bounded WITHOUT any in-process queue, set, or dictionary of work: the pending set, the claim, and the in-flight count SHALL all live in the service's database. Concurrent evaluation SHALL neither lose nor duplicate a result — every claimed target SHALL reach a terminal status exactly once and SHALL produce at most one verdict.

A higher-level target that is re-deferred because its children are still in flight SHALL NOT cause the worker to spin: a drain cycle in which no target made progress SHALL be treated as an idle cycle.

Capacity freed by a finished evaluation SHALL be refilled as soon as that evaluation finishes, and SHALL NOT wait for other evaluations started alongside it. The worker MAY hold the in-flight tasks it is awaiting, but that collection SHALL NOT be what bounds concurrency: the bound SHALL remain computed from the recorded target statuses, so a second replica that has never seen those tasks is bounded identically.

The concurrency cap SHALL hold across concurrently-claiming workers, not merely within one: the capacity computation and the claim SHALL be serialized against other claims so that two workers claiming at the same time cannot each spend the same remaining capacity.

Targets SHALL NOT be starved by another game's backlog: games already at their per-game cap SHALL be excluded before the candidate window is selected, so that a game with free capacity is served while another game's evaluation is saturated.

#### Scenario: Multiple targets of one request evaluate in parallel
- **WHEN** an evaluation request expands to more targets than the per-game concurrency cap
- **THEN** up to that cap SHALL be evaluated concurrently and the rest SHALL wait for capacity, rather than being evaluated one at a time

#### Scenario: A freed slot is refilled without waiting for the rest of the batch
- **WHEN** several targets are evaluated concurrently and one of them finishes while the others are still running
- **THEN** a further pending target SHALL be claimed and started immediately, and SHALL NOT wait for the slowest in-flight evaluation to finish

#### Scenario: Concurrency stays bounded while slots are continuously refilled
- **WHEN** a long backlog of pending targets is drained with continuous refill
- **THEN** the number of judge calls in flight at any instant SHALL never exceed the configured caps

#### Scenario: Two workers claiming at once cannot exceed the global cap
- **WHEN** two workers run their claim transactions concurrently against the same database with capacity for fewer targets than the two would claim independently
- **THEN** the total number of targets moved to `running` SHALL NOT exceed the configured global cap

#### Scenario: A saturated game does not hide another game's pending targets
- **WHEN** one game has more pending targets than the candidate window and is already at its per-game concurrency cap, and a second game has pending targets and free capacity
- **THEN** the second game's targets SHALL be claimed rather than the claim returning nothing

#### Scenario: Parallel evaluation neither loses nor duplicates a verdict
- **WHEN** many targets of a game are drained concurrently
- **THEN** each target SHALL end in exactly one terminal status and each SHALL have at most one verdict written to history, with none left pending

#### Scenario: No in-process registry bounds the work
- **WHEN** the service restarts with targets still recorded as in flight
- **THEN** the concurrency bound SHALL still hold, because it is computed from the recorded target statuses rather than from a process-local structure

#### Scenario: An all-deferred cycle does not hot-loop
- **WHEN** every target a drain cycle claimed is re-deferred because its children are still being graded
- **THEN** the worker SHALL treat the cycle as idle and wait before draining again

## ADDED Requirements

### Requirement: Claims are fenced by a claim epoch

Each claim of a target SHALL carry a monotonically increasing claim epoch recorded on the target, and every transition out of `running` — completion, failure, skip, deferral, and the recording of a mid-evaluation error — SHALL be conditional on the target still being `running` AND still being at the epoch the writing worker claimed. A worker whose claim has been superseded — by a force re-evaluation, by a cancel, or by a stale-claim reclaim — SHALL NOT be able to write its verdict, its status, or its error over the row, and SHALL NOT overwrite the work of the worker that now owns the target.

#### Scenario: A superseded worker's verdict is discarded
- **WHEN** a worker is mid-evaluation on a target, the target is reset and re-claimed by another worker, and the first worker's judge call then returns
- **THEN** the first worker's verdict SHALL NOT be written to the target row and SHALL NOT mark the target terminal, and the target SHALL remain owned by the worker that claimed it most recently

#### Scenario: The current claim holder still writes normally
- **WHEN** a worker completes an evaluation for a target that has not been reset or re-claimed since it claimed it
- **THEN** its verdict SHALL be written and the target SHALL reach a terminal status

### Requirement: Stale claims are reclaimed after a lease expires

A target left `running` by a worker that has stopped making progress SHALL be returned to `pending` so that another worker can evaluate it, without operator intervention. Liveness SHALL be signalled by the owning worker refreshing the claims it still holds; a claim SHALL be considered stale only when it has not been refreshed within a configurable lease window, so that an unusually slow judge call belonging to a live worker is NOT reclaimed.

Reclaiming SHALL be attempted as part of the worker's normal cycle, and SHALL be best-effort: a failure to reclaim SHALL be logged and the cycle SHALL continue, rather than aborting the cycle and causing the worker to spin.

Reclaim attempts SHALL be bounded. A target that has been claimed more times than the configured maximum SHALL be recorded as `failed` with a reason, rather than being reclaimed again, so that a target which reliably kills its worker cannot be retried indefinitely at unbounded judge cost.

The lease window and the refresh interval SHALL be configurable.

#### Scenario: A dead worker's claim is returned to the queue
- **WHEN** a target has been `running` past the lease window with no refresh from the worker that claimed it
- **THEN** it SHALL be returned to `pending` and SHALL be claimable by a worker on a later cycle

#### Scenario: Capacity is not lost when a worker dies
- **WHEN** a worker holding claims on targets stops without releasing them, and those claims pass the lease window
- **THEN** the capacity those targets consumed SHALL become available again and evaluation of other pending targets SHALL resume

#### Scenario: A live worker's slow evaluation is not reclaimed
- **WHEN** a worker is still running and refreshing its claims, and one of its evaluations takes longer than the lease window
- **THEN** that target SHALL NOT be reclaimed while the refreshes continue

#### Scenario: A repeatedly-failing target stops being retried
- **WHEN** a target has been claimed more times than the configured maximum and its claim is found stale again
- **THEN** it SHALL be recorded as `failed` with a reason, SHALL NOT be returned to `pending`, and SHALL NOT consume further judge calls

#### Scenario: A failing reclaim does not stop the worker
- **WHEN** the attempt to reclaim stale claims fails
- **THEN** the failure SHALL be logged and the worker SHALL continue that cycle normally rather than aborting it

#### Scenario: A roll-up blocked by an abandoned child recovers
- **WHEN** a round roll-up cannot be graded because one of its move children was left `running` by a worker that died
- **THEN** once that child's claim is reclaimed and the child is evaluated, the roll-up SHALL be graded rather than deferring indefinitely
