# DRA-51: Subagent failsafes

## Tasks

- [x] 1.1 Add `SUBAGENT_TIMEOUT_SECONDS`, `SUBAGENT_FAILSAFE_MAX_CONSECUTIVE_ERRORS`
      and `SUBAGENT_FAILSAFE_MAX_EMPTY_RESPONSES` to `Settings` with validators,
      and document them in `services/agent-orchestrator/.env.example`.
- [x] 1.2 Add `runtime/subagent_failsafes.py` owning the three checks: an
      absolute-deadline timeout, a consecutive-identical-error counter, and a
      consecutive-empty-response counter, all raising one
      `SubagentFailsafeError` carrying the job error code, the parent-side
      reason, and a message.
- [x] 1.3 Wire the failsafe object into the worker loop in `PromptRunService.run`
      for subagent jobs only: check the deadline at the top of each round and
      bound the model call itself with it; count model-call failures by error
      code so three identical codes raise `subagent_error_loop`; count empty
      responses so three consecutive ones raise `subagent_no_progress`.
- [x] 1.4 Handle `SubagentFailsafeError` in the run's failure handling: record
      the `failure` event and `failed` job status with the failsafe error code
      and `retryable: false`, and terminate the child session.
- [x] 1.5 Map the three failsafe error codes onto their reasons in the child
      monitor's `subagent_failed` event, so the parent job's timeline names
      `timeout`, `error_loop` or `no_progress` instead of a generic `failed`.
- [x] 1.6 Unit-test the failsafe module itself: the timeout raises after the
      deadline, the error loop raises after three identical codes and resets on
      a different code, and the empty-response counter raises after three
      empties and resets on progress.
- [x] 1.7 Unit-test the worker-loop wiring: a hanging model call fails the child
      with `subagent_timeout`, three identical `BifrostError`s fail it with
      `subagent_error_loop`, three empty responses fail it with
      `subagent_no_progress`, a parent waiting on the failed child sees the
      failure, and the child monitor records a `subagent_failed` event on the
      parent naming the failsafe reason.
- [x] 1.8 Update the `agent-orchestrator` spec with the new requirements and
      scenarios, and archive the change.
