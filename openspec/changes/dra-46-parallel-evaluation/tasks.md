# Tasks

## 1. Schema: the claim epoch

- [x] 1.1 Add `attempts: Mapped[int]` (`Integer`, `nullable=False`, `default=0`) to `EvaluatedTargetRow` in `storage/models.py`, documenting that it is the claim epoch and the retry counter at once.
- [x] 1.2 Add `schema_migrations/sql/0003_target_attempts.postgresql.sql`: `ALTER TABLE evaluated_targets ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;`.
- [x] 1.3 Add `schema_migrations/sql/0003_target_attempts.sqlite.sql` with the equivalent `ALTER TABLE`.
- [x] 1.4 Confirm the migration is additive with a default, so rows written before this change start at `attempts = 0` and need no backfill.

## 2. Repository: fence every write on the epoch

- [x] 2.1 Increment `attempts` in the claiming `UPDATE` in `claim_pending_targets`, so the returned rows carry the epoch they were claimed at.
- [x] 2.2 Increment `attempts` in the force branch of `claim_target`, so a force re-claim also moves the epoch.
- [x] 2.3 Add an `attempts` parameter to `_transition_running` and guard on `status='running' AND attempts = :attempts`.
- [x] 2.4 Thread the claimed epoch through `finalize_completed`, `mark_skipped`, `mark_failed`, `record_attempt_error` and `defer_to_pending`.
- [x] 2.5 Keep every one of those call sites able to express "no epoch known" for paths that legitimately have none (a target failed before it was ever claimed), so the guard is not silently bypassed by passing a wrong epoch.

## 3. Repository: reclaim and heartbeat

- [x] 3.1 Add `reclaim_stale_targets(*, lease_seconds, max_attempts)`: reset `running` rows whose `updated_at` is older than the lease to `pending`, and mark those whose `attempts` exceeds `max_attempts` as `failed` with a clear reason instead.
- [x] 3.2 Return what was reclaimed and what was failed, so the worker can log it and the tests can assert on it.
- [x] 3.3 Add `heartbeat_targets(target_ids)`: bump `updated_at` for the given ids that are still `running`, in one statement.
- [x] 3.4 Make the heartbeat conditional on `status='running'` so it cannot resurrect a target that was cancelled or reclaimed underneath the worker.

## 4. Repository: make the cap a real bound

- [x] 4.1 Take `pg_advisory_xact_lock` at the start of the `claim_pending_targets` transaction on PostgreSQL only, matching how `FOR UPDATE SKIP LOCKED` is already applied dialect-conditionally.
- [x] 4.2 Use a single named constant for the lock key so every claimer contends on the same lock.
- [x] 4.3 Exclude games already at their per-game cap in the candidate `SELECT`, before the `LIMIT` window is taken, rather than filtering them out in Python afterwards.
- [x] 4.4 Keep `ORDER BY created_at, id` exactly as it is, preserving the invariant that a cascade's move targets are offered before the roll-ups that depend on them.

## 5. Worker: continuous refill

- [x] 5.1 Restructure `run_forever` into a supervisor loop that holds its in-flight tasks and waits with `asyncio.wait(..., return_when=FIRST_COMPLETED)` plus the poll interval as a timeout.
- [x] 5.2 Harvest every completed task per wake and claim once for all freed slots, so a burst of completions coalesces into one claim and one history read per game.
- [x] 5.3 Call `reclaim_stale_targets` at the head of each cycle, wrapped so a failure logs a warning and the cycle continues; re-raise `asyncio.CancelledError` so shutdown still works.
- [x] 5.4 Heartbeat the in-flight target ids once per cycle, at `EVAL_CLAIM_HEARTBEAT_SECONDS`.
- [x] 5.5 Keep `drain_once` as the single-batch entry point the existing tests and integration suite drive.
- [x] 5.6 Await outstanding tasks on `stop()` so shutdown does not orphan claims that would then have to wait out the lease.
- [x] 5.7 Document in the class docstring that the task set is lifecycle bookkeeping and never the bound, so a later reader does not mistake it for the semaphore `AGENTS.md` forbids.

## 6. Configuration

- [x] 6.1 Add `eval_claim_lease_seconds` (default 120) and `eval_claim_heartbeat_seconds` (default 30) to `config.py` with `AliasChoices` env names, matching the file's existing style.
- [x] 6.2 Validate both are positive, and that the lease is strictly greater than the heartbeat — a lease at or below the refresh interval reclaims live work on every cycle.
- [x] 6.3 Leave `EVAL_GLOBAL_CONCURRENCY` (8) and `EVAL_PER_GAME_CONCURRENCY` (4) unchanged.

## 7. Unit tests

- [x] 7.1 MOVED TO 8.2. The refill properties cannot be proven against the unit fixture: `tests/unit/conftest.py` backs sqlite with `StaticPool`, so every session shares one DBAPI connection and concurrent transactions interleave. Driving the supervisor loop against it produced duplicate claims and stuck rows for the fixture's reasons, not the code's; the identical workload is clean on real Postgres. Refill concurrency is therefore proven in the integration suite.
- [x] 7.2 MOVED TO 8.2, same reason. The cap under continuous refill is asserted against real Postgres.
- [x] 7.3 Epoch fencing: a worker whose target is reset and re-claimed mid-evaluation cannot write its verdict, and the row keeps the newer claim's outcome.
- [x] 7.4 Epoch fencing: an unsuperseded worker still completes normally.
- [x] 7.5 Reclaim: a target whose `updated_at` is aged past the lease returns to `pending` and is claimable again.
- [x] 7.6 Reclaim: capacity wedged by orphaned `running` rows is released — the regression pin for the deadlock this change fixes.
- [x] 7.7 Reclaim: a target over `EVAL_MAX_ATTEMPTS` is marked `failed`, not reclaimed again.
- [x] 7.8 Heartbeat: a refreshed target is not reclaimed even when its evaluation outlives the lease window.
- [x] 7.9 Reclaim failure is logged as a warning and the cycle continues (no traceback, no aborted cycle).
- [x] 7.10 Fairness: a saturated game with a backlog larger than the candidate window does not prevent a second game's targets from being claimed.
- [x] 7.11 Config validation: lease must exceed heartbeat.

## 8. Integration tests (real Postgres)

- [x] 8.1 Genuine concurrent claim race: two claimers on separate connections claim simultaneously; assert the combined claims never exceed the global cap. **Mutation-verified independently: 5/5 runs FAIL with `pg_advisory_xact_lock` removed (both claimers take the full cap, 16 against a cap of 8) and 5/5 PASS with it restored.** Three setup details are load-bearing and are documented in the test: the backlog must exceed `candidate_window * claimers`, the window must span more than one game (or the per-game filter masks the global overshoot), and the connection pools must be warm.
- [x] 8.2 Genuine concurrent drain with continuous refill (absorbs 7.1 and 7.2): drive `run_forever` with a scripted-latency judge and assert every target reaches exactly one terminal status with exactly one verdict, no target is graded twice (`attempts = 1` on every row), a freed slot is refilled before the straggler finishes, and peak in-flight judge calls never exceed the caps.
- [x] 8.3 Reclaim against real Postgres: orphan rows by claiming and abandoning them, age them, and assert a second worker picks them up and completes them.
- [x] 8.4 Epoch fencing against real Postgres across two workers sharing a repository.

## 9. Documentation

- [x] 9.1 `services/eval-service/README.md`: document `EVAL_CLAIM_LEASE_SECONDS` and `EVAL_CLAIM_HEARTBEAT_SECONDS` in the configuration table, and describe the reclaim behaviour.
- [x] 9.2 `services/eval-service/AGENTS.md`: extend *"Concurrency lives in the claim, not in the process"* with the claim epoch and the lease, and state that the worker's task set is not the bound.
- [x] 9.3 `services/eval-service/.env.example`: add both new settings with the rationale for their defaults.
- [x] 9.4 `docker-compose.yaml`: pass both new settings through with defaults, matching how the concurrency caps are already wired.
- [x] 9.5 Check whether the telemetry documentation lists eval-service span attributes; if it does, add the reclaim counters.

## 10. Verification

- [x] 10.1 `./scripts/lint.sh --fix`.
- [x] 10.2 `./scripts/test.sh unit` — eval-service above its 356 baseline, every other service unchanged.
- [x] 10.3 `./scripts/test.sh integration` — eval-service above its 17 baseline.
- [x] 10.4 `~/.local/share/pnpm/openspec validate --all` — exactly one failure, the pre-existing `spec/typed-game-actions`.
- [x] 10.5 Re-run the scheduling measurement after the change and record the efficiency figures against the before numbers in the proposal.
- [x] 10.6 Confirm no scratch or measurement files remain in the repository.
