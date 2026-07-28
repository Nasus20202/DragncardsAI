# A crashed subagent must end its parent's wait

## Why

A parent agent spawns a child with `spawn_subagent` (or `prompt_player_agent`)
and blocks in `wait_for_subagent`. When the child crashes, the parent hangs.

`wait_for_subagent` read the child's status once, then waited on the child's live
event stream. Live events are the wrong authority: they are not written on every
terminal transition, and they are ephemeral.

Reproduced, with the parent already waiting:

| Crash mode | Before |
| --- | --- |
| Exception / `TimeoutError` / `ExceptionGroup` in the run | wait ends, but told only `Subagent ended with: failure` — no cause |
| Crash inside the child's own failure handling | **hangs**: the `worker_crash` guard calls `mark_job_failed` and publishes nothing, so the child is `failed` in the database while its stream stays silent |
| Child hit its tool round limit (`interrupted`) | **hangs**: `interrupted` was missing from the terminal statuses the one database check recognised |
| Child orphaned by a hard worker kill (`running`) | **hangs**: nothing publishes and nothing reclaims it |
| Child streams continuously while stuck | **unbounded**: the 600s timeout was per event, so every `reasoning` chunk renewed it |

Giving up produced `Subagent ended with: timeout` — naming neither child nor
cause — and was recorded nowhere but a log line. The same event-only logic backs
`_monitor_child`, so the `subagent_failed` event the dashboard renders reported
`reason: "timeout"` ten minutes after a crash instead of the crash itself.
Per-player agents reuse this lifecycle, so one stuck wait stalls a whole game.

## What Changes

- **agent-orchestrator (builtin tools)** — one shared `resolve_child_outcome`
  now backs both `wait_for_subagent` and the child monitor. The child's
  persisted status is the authority and is re-read whenever the child falls
  silent for a poll interval; live events are still consumed so a normal finish
  returns immediately rather than on the next poll. `interrupted` is recognised
  as terminal and returns the child's partial work.
- **agent-orchestrator (builtin tools)** — the wait budget becomes absolute
  rather than per event, and configurable
  (`SUBAGENT_WAIT_TIMEOUT_SECONDS`, `SUBAGENT_WAIT_POLL_INTERVAL_SECONDS`).
- **agent-orchestrator (builtin tools)** — every non-success outcome is rendered
  as one actionable line naming the child and its cause
  (`Subagent <id> failed — execution_error: <message>`). Giving up says what the
  child's last recorded status was and tells the agent not to wait again.
- **agent-orchestrator (builtin tools)** — abandoning a wait is recorded on the
  parent job as a `subagent_failed` event with `reason: "wait_timeout"`, so a
  stalled wait is visible in the session timeline instead of only in the log.
  An existing event type is reused deliberately: the dashboard already renders
  it, and from the parent's point of view a child it can no longer hear from has
  failed.
- **agent-orchestrator (builtin tools)** — a wait ends when the parent job's own
  cancellation is requested, so cancelling a parent no longer leaves it blocked
  on a child that has not noticed yet.
- **agent-orchestrator (worker)** — the `worker_crash` guard now *announces* the
  failure as well as persisting it: a `failure` job event, a `failure` live
  event, and termination of the crashed child's session. This is what turns the
  reported hang into an immediate answer; the database backstop above covers the
  case where even announcing fails.

No new state is introduced. The authority is the existing `jobs` row in
PostgreSQL; the live bus stays exactly as ephemeral as it was.

## Non-goals

- **Reclaiming a job orphaned by a hard process kill** (SIGKILL, OOM, node
  loss). Those rows still stay `running`. Requeueing them needs a lease or
  heartbeat with expiry that is safe across worker replicas — a naive startup
  sweep would abort another replica's in-flight jobs — and that is a larger
  change than this bug needs. What changes here is that the orphan can no longer
  hold a parent hostage: the wait bounds itself, reports the child's last
  recorded status, and tells the agent to stop waiting. Deliberately deferred so
  the wait side is correct first; the reaper remains open work.
- Cancelling the child when the parent gives up waiting. The parent may still
  want the child's eventual result, and `request_cancel` remains the explicit
  way to stop it. Only the *waiting* is abandoned.
- Changing retry classification, or how failures are classified.
- Changing the child monitor's contract: it still emits
  `subagent_completed` / `subagent_failed` on the parent job. Only the accuracy
  of `reason` changes.

## Impact

- Affected specs: `agent-orchestrator` (new requirement: `wait_for_subagent`
  always terminates; modified: the child monitor reports the real outcome).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py`,
  `services/agent-orchestrator/src/agent_orchestrator/runtime/worker.py`,
  `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py`,
  `services/agent-orchestrator/src/agent_orchestrator/config.py`.
- No API, schema, or migration changes. The text `wait_for_subagent` returns to
  the LLM changes shape, which is a prompt-visible but not contract-visible
  change.
