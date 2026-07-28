# Tasks

## 1. Reproduce and locate the swallow

- [x] 1.1 Confirm the retry loop in `runtime/evaluator.py` only `logger.info`s a
      failed judge attempt: nothing persisted, nothing pushed, so a client sees
      nothing until the target is terminal and then only the last error.
- [x] 1.2 Confirm every failure path called `mark_skipped`, the same channel the
      deliberate non-strategic skip uses (~32% of recorded moves), so a client
      cannot tell an error from routine bookkeeping.
- [x] 1.3 Confirm the eval-service already returns `error` per target on
      `GET /evaluations`, `GET /games/{id}/evaluations/{request_id}` and the SSE
      `status` payload — so the server-side loss is the conflation, not the field.
- [x] 1.4 Confirm the dashboard drops it: `EvaluationQueueTarget` has no `error`
      field and `evaluation-queue.tsx` renders only game/scope/status/progress.
- [x] 1.5 Confirm `dragncards_common.bifrost.extract_error_message` falls back to
      `str(payload)` of the whole gateway error body — unbounded and unredacted.

## 2. Redaction and truncation at the storage boundary

- [x] 2.1 Add `eval_service/error_detail.py` with `sanitize_error_detail`:
      credential-bearing fields (`authorization`, `x-bf-api-key`, `api_key`,
      `access_token`, `client_secret`, `password`, …), bare `Bearer` tokens, and
      bare provider key literals (`sk-`, `sk-or-v1-`, `xai-`, `gsk_`, `AIza…`)
      become `[REDACTED]`; the result is capped at `MAX_ERROR_DETAIL_CHARS`.
- [x] 2.2 Redact BEFORE truncating so a secret past the cut cannot survive.
- [x] 2.3 Apply it inside `Repository.mark_failed`, `mark_skipped` and
      `record_attempt_error` so no call site can bypass it.
- [x] 2.4 Cover it directly in `tests/unit/test_error_detail.py` (field forms,
      bearer, bare key literals, truncation, redact-before-truncate).

## 3. Errors, not skips

- [x] 3.1 Record `failed` (with the reason) for: judge attempts exhausted,
      verdict-less return, assembly `ValueError`, `BoundaryUndetectedError`,
      write-back failure, and unset `EVAL_JUDGE_MODEL`.
- [x] 3.2 Record `failed` for a per-game history read failure in
      `EvaluationWorker.drain_once`, and wake live subscribers for it.
- [x] 3.3 Leave `mark_skipped` used by exactly one caller: the non-strategic
      action skip; document that reservation on the method.
- [x] 3.4 Update the assertions that encoded the old conflation
      (`tests/unit/test_evaluator.py`, `test_evaluator_provenance.py`,
      `tests/integration/test_worker_end_to_end.py`) and assert the reason text
      survives, not just the status.

## 4. Live reporting of in-progress failures

- [x] 4.1 Add `Repository.record_attempt_error`: write the reason to the target
      row while `status='running'` (Postgres, not the worker), guarded so a
      concurrent cancel or force re-claim is never clobbered.
- [x] 4.2 Add an `on_error` sink to `Evaluator` mirroring the existing `on_token`
      sink, and call it from the retry loop for every failed attempt as well as
      from every terminal failure.
- [x] 4.3 Wire `EvaluationWorker._make_error_sink` to the existing `LiveEventBus`
      so a recorded failure wakes SSE subscribers, which re-read the durable
      snapshot that already carries `error` — no new SSE event type, no second
      transport.
- [x] 4.4 Test that a mid-run attempt error is readable from the durable row
      while the target is still `running`, and that a successful retry clears it
      instead of leaving a false failure behind.
- [x] 4.5 Test the worker's live-push wiring in
      `tests/unit/test_worker_error_reporting.py` (attempt failure, history read
      failure, terminal failure reaching `TargetResult.error`).

## 5. Dashboard

- [x] 5.1 Add `error` to `EvaluationQueueTarget`, documenting that it is present
      on a still-`running` target too.
- [x] 5.2 Add `requestErrors` to `features/history/lib/eval-queue.ts`: per-target
      failures in target order, including `running`/`pending` targets, excluding
      deliberate `skipped` reasons and `cancelled` bookkeeping and blank detail.
- [x] 5.3 Render them on the queue row using the danger treatment already present
      in `evaluation-queue.tsx`, capped at three entries with a `+N more`
      summary. No restyling of anything existing.
- [x] 5.4 Test the selector and the row rendering, including that a
      non-strategic `skipped` reason is NOT presented as a failure.

## 6. Documentation and spec

- [x] 6.1 Update `services/eval-service/README.md` with an "Errors are reported
      live" section and correct the two places that said a judge failure is
      recorded as a skip.
- [x] 6.2 Update `services/eval-service/AGENTS.md`: `skipped` is reserved,
      failures are `failed`, error detail is durable and sanitized at the
      repository boundary.
- [x] 6.3 Write the `agent-move-evaluation` and `game-history-ui` spec deltas.

## 7. Verify

- [x] 7.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh`.
- [x] 7.2 `./scripts/test.sh unit eval-service` and the dashboard/orchestrator/
      history/shared unit suites.
- [x] 7.3 Confirm the new tests FAIL without the production change (verified by
      stashing the production files and re-running).
- [x] 7.4 `openspec validate --all` (only the pre-existing
      `spec/typed-game-actions` failure remains).
