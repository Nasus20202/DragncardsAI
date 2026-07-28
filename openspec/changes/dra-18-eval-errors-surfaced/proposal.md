# Surface evaluation errors live, with redacted detail (DRA-18)

## Why

A user reported (DRA-18): *"Errors during evaluation were skipped and not reported
to the user. Details should be reported live, not only final `failed` state."*

Traced. The detail was lost in three distinct places, and the reporter's wording
names the first two exactly.

**1. Mid-run attempt failures were logged and dropped.** In
`services/eval-service/src/eval_service/runtime/evaluator.py` the judge retry loop
caught `(BifrostError, VerdictParseError)` and did nothing with it but
`logger.info(...)` before sleeping and retrying. Nothing was persisted and nothing
was pushed, so with `EVAL_MAX_ATTEMPTS=3` and a 120s judge timeout a client could
watch a target sit at `running` for six minutes with no indication that anything
was wrong — and then receive only the LAST error. "Reported live, not only final
state" is precisely this gap.

**2. Errors were recorded as `skipped`.** Every failure path — judge attempts
exhausted, assembly error, undetected round boundary, failed history read, failed
verdict write-back, unset `EVAL_JUDGE_MODEL` — called `mark_skipped`, the same
channel the *deliberate* non-strategic skip uses ("a card search cannot be a wrong
play"). On real games that deliberate skip fires on ~32% of moves, so an error was
indistinguishable from routine bookkeeping: the reason string was there, but no
client could tell which `skipped` rows were problems. "Errors were skipped" is
literal.

**3. The dashboard dropped the detail entirely.** The eval-service already
returned `error` per target on all three endpoints, but the dashboard's queue type
`EvaluationQueueTarget` had no `error` field and `evaluation-queue.tsx` rendered
only game / scope / status / progress. A failed evaluation showed a `failed` chip
and nothing else — no reason, ever, at any point.

Separately, the detail on the way out was unsafe to show: `extract_error_message`
falls back to `str(payload)` of the gateway's whole error body, which can carry an
`Authorization` header or a provider echoing the request (prompt plus a recorded
game state). Nothing bounded or scrubbed it before it was stored and served.

## What Changes

- **`failed` means an error; `skipped` means "nothing to grade".** Every error
  path records `failed` with its reason. `skipped` is reserved for the
  non-strategic-action skip, so the two can never be conflated. `failed` was
  already a terminal status in the schema and the request-status aggregate, so no
  migration and no new status.
- **Every failed judge attempt is reported as it happens.** The retry loop writes
  the attempt's reason onto the target row (Postgres) *while the row is still
  `running`* via a new `Repository.record_attempt_error`, and pushes it through a
  new `on_error` sink — mirroring the existing `on_token` sink. The worker's sink
  wakes the existing live bus, so a connected SSE client re-reads the snapshot at
  once, and the dashboard's existing 2s queue poll picks it up on its next tick.
  No new transport, no new SSE event type, and no error detail held in the worker.
- **All recorded error text is redacted and truncated** by a new
  `error_detail.sanitize_error_detail`, applied at the repository boundary so no
  call site can bypass it: credential-bearing fields and bare provider key
  literals become `[REDACTED]`, and the text is capped at 1,000 characters so a
  provider echoing the full request body cannot be persisted or streamed.
- **The dashboard queue row lists the request's per-target failures**, including
  those on still-running targets, in the danger treatment already used in that
  component. Deliberate `skipped` reasons and `cancelled` bookkeeping are not
  failures and are not listed.

## Non-goals

- No new transport. The dashboard queue keeps polling `GET /evaluations`; the
  eval-service keeps its single SSE stream. No `EventSource` was added to the
  queue.
- No new SSE event type. The `status` payload already carries per-target `error`;
  the fix is that a mid-run failure now *wakes* the stream and the snapshot it
  re-reads already contains the detail.
- No restyling of the evaluations queue or any other existing component.
- Non-strategic `skipped` reasons are still not shown in the UI. They are
  high-volume routine bookkeeping, not failures; surfacing them is a separate
  product decision.
- The `/ready` readiness probe's own `except Exception` swallows are untouched —
  they are a different (documented, no-secret) surface.

## Capabilities

### New Capabilities

This change introduces no new capability. Reporting an evaluation failure belongs
to the capability that already owns evaluation outcomes (`agent-move-evaluation`)
and to the one that already owns the evaluations queue (`game-history-ui`), so
both spec deltas correct and extend existing requirements rather than declaring a
new area.

### Modified Capabilities

- **agent-move-evaluation**: failure isolation now requires a `failed` outcome
  with a recorded reason rather than a skip; a new requirement mandates live
  reporting of in-progress failures and redaction/truncation of all error detail;
  the non-strategic-skip requirement reserves `skipped` for deliberate skips; the
  cross-game listing must carry each target's error.
- **game-history-ui**: the persistent evaluations queue must show the per-target
  failure detail of a request, including while it is still running.

## Impact

- **Production code**:
  - `services/eval-service/src/eval_service/error_detail.py` (new)
  - `services/eval-service/src/eval_service/storage/repository.py`
  - `services/eval-service/src/eval_service/runtime/evaluator.py`
  - `services/eval-service/src/eval_service/runtime/worker.py`
  - `services/dashboard/features/shared/lib/types.ts`
  - `services/dashboard/features/history/lib/eval-queue.ts`
  - `services/dashboard/features/history/components/evaluation-queue.tsx`
- **Tests**: `services/eval-service/tests/unit/test_error_detail.py` (new),
  `tests/unit/test_worker_error_reporting.py` (new), `tests/unit/test_evaluator.py`,
  `tests/unit/test_evaluator_provenance.py`,
  `tests/integration/test_worker_end_to_end.py`,
  `services/dashboard/features/history/__tests__/eval-queue.test.ts`,
  `services/dashboard/features/history/__tests__/evaluation-queue.test.tsx`
- **Documentation**: `services/eval-service/README.md`,
  `services/eval-service/AGENTS.md`
- **Database**: none. The existing `error` column carries the detail; `failed` was
  already a valid status.

## Notes

- `game-service`'s unit suite does not collect in this worktree (384 collection
  errors, `literal "expected" cannot be empty, obj=typing.Literal[()]` from an
  empty generated action registry). Verified pre-existing on the unmodified
  branch and unrelated to this change.
