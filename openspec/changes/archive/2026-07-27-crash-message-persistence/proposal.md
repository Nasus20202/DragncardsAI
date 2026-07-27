# Crashed prompt runs must keep their message in the session context

## Why

When a prompt run crashes, the user's message disappears from the session
transcript. The next prompt continues as if the message was never sent.

The prompt itself is already durable — `enqueue_prompt_job` writes it to the
`jobs` row before any worker touches it. The loss happens in replay:
`list_completed_jobs_for_replay` only returns jobs whose status is
`completed`, `interrupted`, or `failed`. A job that never reaches one of those
statuses is invisible to every future run.

`PromptRunService.run` only converts a subset of errors into a terminal status:

- The prologue (cancellation check, job load, model-config check, and a
  context-length lookup against Bifrost) ran **outside** the `try`, so any error
  there — including a Valkey/Bifrost failure inside `get_model_context_length` —
  escaped unhandled.
- The `except` list was `(BifrostError, McpClientError, RuntimeError,
  ValueError, InvalidToolInvocationError)`. Common real failures fall outside
  it: `TimeoutError` (an `OSError`, not a `RuntimeError`), and `ExceptionGroup`
  wrappers raised by anyio/`asyncio` task groups — which the worker clearly
  encounters, since `format_execution_error` already unwraps them.

`WorkerService._run_job` is fired as a detached `asyncio.Task` that nobody
awaits, so an escaping exception is silently swallowed. The job row stays at
`status = "running"` forever, no `failure` event is written, and the prompt is
permanently excluded from context replay.

Reproduced: a `TimeoutError` from `chat_completion` leaves the job `running`
and `build_message_history` for the session returns `[]` — the prompt is gone.

## What Changes

- **agent-orchestrator (prompt run)** — the entire run, prologue included, is
  guarded, and the fallback handler catches every `Exception` instead of a
  hand-picked list, so any crash is classified, recorded as a `failure` event,
  and driven to a terminal job status. `asyncio.CancelledError` derives from
  `BaseException` and is deliberately still not caught, so worker shutdown keeps
  cancelling in-flight jobs as before.
- **agent-orchestrator (worker)** — `_run_job` gets a last-resort guard: if the
  prompt run's own failure handling raises, the worker logs it and marks the job
  `failed` with `error_code = "worker_crash"` rather than leaving it `running`.
- Removed a dead `get_model_context_length` call in `run`: its result was never
  used (auto-compaction recomputes it), yet it was an unguarded network call
  ahead of the `try` and therefore one of the crash paths.

No new representation for a failed run is introduced. The existing "failed jobs
are replayed with a synthetic assistant note" contract already restores the
prompt correctly — the bug was only that crashed runs never became `failed`.

## Non-goals

- Recovering jobs orphaned by a hard worker-process kill (SIGKILL, OOM, node
  loss). Those rows also stay `running`, but reclaiming them needs a lease or
  reaper that is safe across worker replicas; a naive startup sweep would abort
  another replica's in-flight jobs.
- Changing retry classification. A timeout is still non-retryable
  (`execution_error`); it now simply fails terminally instead of hanging.
- Changing history-event (`user_prompt`) emission timing.

## Impact

- Affected specs: `agent-orchestrator` (new requirement: crashed prompt runs
  reach a terminal status).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py`,
  `services/agent-orchestrator/src/agent_orchestrator/runtime/worker.py`.
- No API, schema, or migration changes.
