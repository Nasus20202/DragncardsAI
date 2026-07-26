# Force re-claim safety for in-flight evaluations

## Why

A force re-evaluation (`force=true`) resets an existing target row from `running`
back to `pending` so a fresh verdict is produced. But when the force re-claim
lands while a worker is mid-evaluation on that same target, nothing cancels the
in-flight task: the next drain starts a SECOND task for the same target. Both the
stale and the fresh task can pass the `running` re-check and write a verdict to
history. When the two evaluations use different judge configs their idempotency
keys differ, so history dedup does not collapse them — the target ends up with
two verdict events plus eval-service DB / history divergence. Additionally, the
stale task overwrote the fresh task in the in-flight registry, leaving the live
task uncancellable.

Two smaller correctness gaps compound the churn: the judge-config digest that
feeds the idempotency key does not sort the `skills` list, so a semantically
identical re-eval with reordered skills yields a different key (spurious second
event); and the pending-target claim orders only by `created_at`, which is
identical for all targets of one request, so the drain order is nondeterministic
and deferred round/game roll-ups churn.

## What Changes

- **eval-service (force re-claim)** — the request/force path SHALL cancel any
  in-flight task for a target before the next drain can start a fresh one, so at
  most one evaluation of a target is ever in flight. The cancel mirrors the
  cancel route (durable state changed first, then abort the task) and happens
  with no `await` between the durable reset and the cancel, so the worker cannot
  re-claim the row in the gap.
- **eval-service (in-flight registry)** — `unregister` becomes identity-aware:
  a stale task finishing its `finally` SHALL NOT evict a newer task that a force
  re-claim registered for the same `target_id`, so the live task stays
  cancellable.
- **eval-service (idempotency digest)** — the judge-config digest SHALL sort the
  `skills` list before hashing, so a re-eval with the same skill SET in a
  different order produces the same idempotency key (no spurious second event).
  Only the digest copy is sorted; the stored/injected skill order is untouched.
- **eval-service (claim ordering)** — pending-target claims SHALL apply a stable
  secondary sort by `id` after `created_at`, so the drain order among a request's
  targets is deterministic and deferred roll-ups do not churn.

## Impact

- Affected specs: `agent-move-evaluation` (idempotent/at-most-once verdict
  write-back under force; verdict identity invariance to skill order).
- Affected code: `services/eval-service/src/eval_service/runtime/requests.py`
  (cancel prior in-flight on force re-claim), `runtime/inflight.py`
  (identity-aware unregister), `runtime/worker.py` (pass task identity on
  unregister), `runtime/app.py` (share the registry with `RequestService`),
  `judge/writeback.py` (sort skills in the digest),
  `storage/repository.py` (stable claim ordering).
- No API or schema changes; all fixes are internal correctness hardening.
