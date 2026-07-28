## 1. Make the child's persisted status the authority

- [x] 1.1 Add `resolve_child_outcome` in `builtin_tools.py`: subscribe first,
      then re-read the child's `jobs` row, treat any terminal status as the
      outcome, and consume live events so a normal finish returns at once.
- [x] 1.2 Add `interrupted` to the terminal statuses and return the child's
      `result_text` as a successful result for it.
- [x] 1.3 Make the budget absolute rather than per event, and only re-read the
      row after a whole poll interval of silence so a streaming child does not
      put the database on the hot path.
- [x] 1.4 Guarantee forward progress when a subscriber reports "nothing yet"
      faster than it was asked to wait, so the wait cannot become a busy loop.

## 2. Report outcomes the agent can act on

- [x] 2.1 Add `ChildOutcome` plus `describe_child_outcome`: name the child, its
      failure code and message, or — when giving up — its last recorded status
      and the instruction not to wait again.
- [x] 2.2 Record an abandoned wait on the parent job as `subagent_failed` with
      `reason: "wait_timeout"`, appended and published.
- [x] 2.3 End the wait when the parent job's own cancellation is requested,
      without cancelling the child.
- [x] 2.4 Update the `wait_for_subagent` tool description so the model knows the
      wait always returns and must not retry a child it was told to give up on.

## 3. Announce worker-level crashes

- [x] 3.1 Extract `WorkerService._force_terminal_failure`: mark `failed`, append
      a `failure` job event, publish a `failure` live event, and terminate a
      crashed child's session, each step guarded independently.

## 4. Share the resolver with the child monitor

- [x] 4.1 Rebuild `_make_child_monitor` on `resolve_child_outcome` so
      `subagent_failed` carries the real reason plus `error_code` /
      `error_message`, and an `interrupted` child reports as completed.
- [x] 4.2 Plumb `subagent_wait_timeout_seconds` /
      `subagent_wait_poll_interval_seconds` from `Settings` through
      `build_builtin_registry` into the wait handler and both monitors, with
      defaults so the tool-catalog preview path is unaffected.

## 5. Tests

- [x] 5.1 Unit tests: a child that crashes with an exception, a `TimeoutError`,
      or an `ExceptionGroup` while the parent is already waiting ends the wait
      with the cause, using the shipped (unshortened) budget.
- [x] 5.2 Unit test: a crash inside the child's own failure handling still ends
      the parent's wait, reporting `worker_crash`.
- [x] 5.3 Unit test: the worker crash guard publishes and persists a `failure`
      event and terminates the crashed child's session.
- [x] 5.4 Unit test: an `interrupted` child returns its partial work.
- [x] 5.5 Unit test: a child stuck in `running` (a dead-worker orphan) ends the
      wait at its budget and says so.
- [x] 5.6 Unit test: the abandoned wait is appended to the parent job.
- [x] 5.7 Unit test: continuous non-terminal events do not renew the budget.
- [x] 5.8 Unit tests: cancelling the parent releases the wait, and a child
      cancelled by the parent's cascade is reported as cancelled.
- [x] 5.9 Unit test: the monitor's `subagent_failed` names the real crash.
- [x] 5.10 Unit test: the registered tool honours the configured budget.
- [x] 5.11 `./scripts/lint.sh --fix`, `./scripts/test.sh unit`, and
      `./scripts/test.sh integration agent-orchestrator` pass.
