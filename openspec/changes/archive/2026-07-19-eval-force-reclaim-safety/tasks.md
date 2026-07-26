## 1. Force re-claim cancels the in-flight task

- [x] 1.1 Share the `InflightRegistry` with `RequestService` (`runtime/app.py`);
      add an optional `inflight` parameter to `RequestService.__init__`.
- [x] 1.2 In `RequestService.create`, after a claimed force re-claim, call
      `inflight.cancel(target_id)` with no `await` between `claim_target`
      returning and the cancel, mirroring the cancel route (durable state first,
      then abort the task).
- [x] 1.3 Make `InflightRegistry.unregister` identity-aware: only drop the entry
      when the finishing task is still the registered one, so a stale task's
      `finally` cannot evict a newer force-re-claimed task.
- [x] 1.4 In `EvaluationWorker`, pass `asyncio.current_task()` to `unregister`.

## 2. Skill-order-invariant idempotency digest

- [x] 2.1 In `judge_config_digest`, sort the `skills` list before hashing (digest
      copy only; stored/injected order unchanged).

## 3. Deterministic pending-target claim ordering

- [x] 3.1 Add a stable secondary sort `id ASC` after `created_at ASC` in
      `Repository.claim_pending_targets`.

## 4. Tests

- [x] 4.1 Integration test: a force re-claim while a target is running (stale task
      paused inside `write_event`, past the `running` re-check) produces exactly
      ONE history write-back for that target; the fresh config wins.
- [x] 4.2 Unit test: `InflightRegistry.unregister` is identity-aware (a stale
      task's unregister keeps a newer registered task cancellable).
- [x] 4.3 Unit test: the config digest / idempotency key is invariant to the
      order of the `skills` list, while a genuinely different skill set differs.
- [x] 4.4 `./scripts/lint.sh --fix`, `uv run pytest tests/unit`, and
      `uv run pytest tests/integration` all pass.
