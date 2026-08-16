# A stuck subagent must fail its job instead of hanging forever

## Why

DRA-51 reports: "Sometime the subagent crashes without error - we should have a
timeout for that. It should be big, but if no response is sent, we fail. Also
please add some other failsafe mechanisms."

A subagent (child job) is executed by the same worker loop as a top-level job.
That loop only ends when the model produces a terminal state or the tool-round
limit is hit. A subagent whose provider call never returns, whose model keeps
failing with the same transport error, or whose model keeps returning empty
responses (no tool calls, no content) stays `running` indefinitely. The parent
blocks in `wait_for_subagent` for its own 600s budget, then gives up with a
`wait_timeout` — but the child keeps running and spending tokens for as long as
nothing else stops it. The worker's `worker_crash` guard only fires when an
exception escapes the loop; a hang is not an exception.

Three concrete failure modes are in scope, each detected inside the worker loop
and each ending the child's run with a definite failure instead of a silent
stall:

| Mode | Detection | Job error code |
| --- | --- | --- |
| Timeout | No terminal event within `SUBAGENT_TIMEOUT_SECONDS` (default 30 minutes, configurable) | `subagent_timeout` |
| Error loop | The same model-call `error_code` on three consecutive calls (e.g. a transport failure repeating) | `subagent_error_loop` |
| No progress | An empty response (no tool calls, no content) on three consecutive model calls | `subagent_no_progress` |

The cancellation must reach the parent. `wait_for_subagent` already resolves a
child's outcome from its persisted status, so a child that ends `failed` with a
failsafe error code is returned to the parent as a failure naming that code.
The child monitor already appends a `subagent_failed` event to the parent job;
that event now carries the failsafe's reason (`timeout`, `error_loop`,
`no_progress`) as well as the error code, so the session timeline and the
dashboard show what actually happened rather than a generic failure.

## What Changes

- **agent-orchestrator (new module)** — `runtime/subagent_failsafes.py` owns
  the three checks as one per-run object: an absolute deadline (`timeout`),
  a consecutive-identical-error counter (`error_loop`), and a
  consecutive-empty-response counter (`no_progress`). All three raise one
  `SubagentFailsafeError` carrying the job error code, the parent-side reason,
  and a message naming what was observed.
- **agent-orchestrator (worker loop)** — `PromptRunService.run` creates a
  failsafe object for subagent jobs (`parent_job_id` set) and consults it on
  every tool round: the deadline is checked at the top of each round and bounds
  the model call itself (a provider that hangs is cancelled when the budget is
  spent); a model-call failure is counted by error code instead of ending the
  run, so three identical codes fail it with `subagent_error_loop`; an empty
  non-truncated response is not a completion for a subagent, so three in a row
  fail it with `subagent_no_progress`. Top-level jobs are untouched — all three
  checks are gated on the failsafe object existing.
- **agent-orchestrator (failure handling)** — a failsafe failure is recorded
  through the existing `record_failure` path: a `failure` job event and a
  `failed` job status carrying the failsafe error code, with `retryable:
  false` so `mark_job_failed` never re-queues the child (children are enqueued
  with `max_attempts=1` anyway; the failsafe is a definitive stop, not a
  transient blip). The child session is terminated as for any other failure.
- **agent-orchestrator (child monitor)** — the `subagent_failed` event the
  monitor appends to the parent job maps the three failsafe error codes onto
  their reasons (`timeout`, `error_loop`, `no_progress`); every other outcome
  keeps its existing `reason` (the terminal status). The existing
  `wait_for_subagent` rendering already names the child and its
  `error_code:error_message`, so no prompt-visible change is needed there.
- **agent-orchestrator (config)** — new `SUBAGENT_TIMEOUT_SECONDS` (default
  1800, must be positive), `SUBAGENT_FAILSAFE_MAX_CONSECUTIVE_ERRORS` and
  `SUBAGENT_FAILSAFE_MAX_EMPTY_RESPONSES` (defaults 3, at least 1).

## Non-goals

- **Reclaiming a job orphaned by a hard process kill** (SIGKILL, OOM, node
  loss). The row still stays `running`; the parent-side wait still bounds
  itself as it does today. The failsafe is a per-run watchdog, not a reaper.
- **Changing the parent-side wait budget** (`subagent_wait_timeout_seconds`,
  600s default). It is independent of the child-side failsafe and keeps its
  existing meaning: how long a parent blocks on one wait. A parent whose wait
  gives up at 600s before the child's 30-minute timeout fires still sees the
  child's real failure if it waits again later.
- **Cancelling the child when the parent gives up waiting.** Unchanged; the
  parent may still want the child's eventual result.
- **Retrying a failed subagent automatically.** The failsafe failures are
  non-retryable; the parent agent may re-spawn, bounded by its own run's
  tool-round budget — the existing `spawn_subagent` path.
- **Applying the failsafes to top-level jobs.** The ticket is about subagents;
  top-level jobs keep their current behaviour exactly.

## Impact

- Affected specs: `agent-orchestrator` (new requirements: subagent run is
  bounded by a timeout; repeated identical model-call failures fail the
  subagent; repeated empty responses fail the subagent; the child monitor
  reports the failsafe reason).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py`,
  `services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py`,
  `services/agent-orchestrator/src/agent_orchestrator/config.py`,
  `services/agent-orchestrator/.env.example`.
- No API, schema, or migration changes. No new event type: the failsafe
  outcome is a normal `failure` on the child job and a `subagent_failed` on
  the parent job, both of which already exist.
