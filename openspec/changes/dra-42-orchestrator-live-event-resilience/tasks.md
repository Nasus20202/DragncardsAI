## 1. Confirm the call sites against the code, not the report's line numbers

- [x] 1.1 Confirm `job_event_stream.py` awaits `live_subscriber.get(...)` unguarded and that the exception escapes the async generator
- [x] 1.2 Confirm `on_bifrost_delta`'s publish sits inside the callback `_stream_chat_completion` awaits, itself inside the job's `try`
- [x] 1.3 Enumerate every `live_event_bus.publish` call site and record which have a durable `append_event` twin
- [x] 1.4 Confirm `compaction` is the only publish with no twin, and that its summary is durable on its own compaction job
- [x] 1.5 Read `record_failure` on this tip rather than at the report's line number: it captures `durable_event_id` first (post-DRA-34)
- [x] 1.6 Trace what actually happens on this tip when `record_failure`'s publish throws, and correct the triage: the job *does* reach `"failed"`, via `_force_terminal_failure`, at the cost of `error_code = "worker_crash"` and a duplicated `failure` event
- [x] 1.7 Confirm from `resp.py` that connections are per-command, so a subscriber holds no socket and retrying is the whole of the recovery
- [x] 1.8 Enumerate every live-bus subscriber read in the service, not only the ones the report's tracebacks reached
- [x] 1.9 Record the fourth site found by that audit: `resolve_child_outcome`'s `_next_event` read, which failed the *parent* job when a *child's* stream reset — the orchestrated multi-agent path the issue is named after
- [x] 1.10 Confirm `resolve_question_outcome` (`ask_user`) deliberately consumes no live events, so there is no fifth site

## 2. Pin the regression before fixing it

- [x] 2.1 Add `test_live_subscriber_failure_does_not_end_the_stream` — durable events keep arriving while the bus is down
- [x] 2.2 Add `test_stream_still_closes_on_a_terminal_job_while_the_bus_is_down` — degrading must not become hanging
- [x] 2.3 Add `test_stream_resumes_live_delivery_after_the_bus_recovers` — the downgrade is not permanent
- [x] 2.4 Add `test_a_publish_failure_during_a_delta_does_not_fail_the_job` — the job completes with every publish failing
- [x] 2.5 Add `test_the_transcript_survives_a_total_live_bus_outage` — the durable rows are all still there
- [x] 2.6 Add `test_expire_failure_after_a_successful_xadd_still_publishes`
- [x] 2.7 Add `test_a_failing_xadd_still_fails_the_publish` — the guard stays narrow
- [x] 2.8 Add `test_a_job_fails_cleanly_when_its_failure_publish_fails` — terminal, with the real `error_code` and one `failure` event
- [x] 2.9 Add unit pins for the backoff shape, the wrapper's idempotence and unwrapping, and the log discipline
- [x] 2.10 Add `test_a_subagent_wait_survives_a_dead_live_bus` — the wait resolves from the child's row, without patching any backoff constant
- [x] 2.11 Add an integration pin that `GET /jobs/{id}/events/stream` answers 200 with every live-bus operation failing, since the unit pins drive the generator directly and cannot show the dying *response* the reporter saw
- [x] 2.12 Run every new test against the base with the source changes reverted, and record which fail and why: 8 of 13 unit pins fail — three raise `ConnectionResetError` at `job_event_stream.py:105`, two show `assert 'failed' == 'completed'`, one shows `assert 'completion' in ['progress', 'progress', 'model_output', 'failure', 'failure']`, one shows `assert 'worker_crash' == 'provider_error'`, and the subagent-wait pin raises the reset straight out of `resolve_child_outcome`; the integration pin fails the same way

## 3. Make publishing best-effort

- [x] 3.1 Add `runtime/live_event_resilience.py`
- [x] 3.2 Implement `FailureStreak`: one traceback per streak, counted warnings at powers of two, one recovery line with the length
- [x] 3.3 Implement `BestEffortLiveEventBus` — delegates `subscribe`/`aclose`, returns `None` from a failed `publish`, never catches `BaseException`
- [x] 3.4 Add `best_effort_live_event_bus` (idempotent) and `unwrap_live_event_bus`
- [x] 3.5 Widen `LiveEventBus.publish` to `LiveJobEvent | None` and document why on the Protocol
- [x] 3.6 Wrap the bus in `create_app` so every consumer in the process gets it
- [x] 3.7 Wrap again in `WorkerService.__init__` so the job runtime is tolerant however it is wired, and pass the wrapped bus to `PromptRunDependencies`
- [x] 3.8 Unwrap in the readiness probe, which is asking which bus is configured

## 4. Degrade the readers instead of letting them die

- [x] 4.1 Implement `LiveBusDegradation` with a short, doubling, capped delay and a reset on success
- [x] 4.2 Guard `live_subscriber.get` with `except Exception`, leaving `CancelledError` and `GeneratorExit` to the existing handler
- [x] 4.3 Route a failure into the subscriber-timeout path so a terminal job still closes the stream
- [x] 4.4 Keep the existing subscriber rather than replacing it, and record in `design.md` why replacing it would replay the stream
- [x] 4.5 Guard `resolve_child_outcome`'s live read the same way, falling through to the child's row re-read and leaving the absolute deadline intact

## 5. Stop a TTL refresh from undoing a successful publish

- [x] 5.1 Guard the `EXPIRE` that follows `XADD`, log one warning without a stack, and return the event
- [x] 5.2 Leave `XADD` raising, so losing the event is still reported to the layer that knows the durable row exists
- [x] 5.3 Record in `design.md` that this guard and its test are to be deleted, not merged, when DRA-37 makes the publish a single `EVAL`

## 6. Verify

- [x] 6.1 `./scripts/lint.sh --fix` clean
- [x] 6.2 `./scripts/test.sh unit` — agent-orchestrator 503 (490 baseline + 13 new), every other service at its baseline
- [x] 6.3 `./scripts/test.sh integration agent-orchestrator` — 29 (28 baseline + 1 new)
- [x] 6.4 `openspec validate --all` — 17 passed / 1 failed; the only failure is the pre-existing `spec/typed-game-actions`, and the extra passing item is this change
- [x] 6.5 Update `services/agent-orchestrator/README.md` with the degraded behaviour and its logging
