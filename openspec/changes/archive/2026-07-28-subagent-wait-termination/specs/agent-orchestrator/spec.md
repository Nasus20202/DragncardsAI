## ADDED Requirements

### Requirement: wait_for_subagent always terminates with an actionable outcome
`wait_for_subagent` SHALL always return a result, and SHALL NOT block indefinitely on a child that crashed, was cancelled, was orphaned by a dead worker, or simply stopped reporting.

The child job's persisted status SHALL be the authority for whether it ended. Live job events are ephemeral (the Valkey stream carrying them expires) and are not published on every terminal transition, so the wait SHALL re-read the child's status while waiting rather than trusting the event stream alone. Terminal statuses are `"completed"`, `"failed"`, `"cancelled"`, and `"interrupted"`. Terminal live events SHALL still end the wait immediately so an ordinary finish is not delayed to the next poll.

The wait budget SHALL be absolute rather than per event, so a child that keeps emitting non-terminal events cannot renew it indefinitely. The budget and the status re-read interval SHALL be configurable through `SUBAGENT_WAIT_TIMEOUT_SECONDS` and `SUBAGENT_WAIT_POLL_INTERVAL_SECONDS`, both of which MUST be positive.

A failed child SHALL be reported with its `error_code` and `error_message` so the parent can reason about the cause rather than only learning that something ended. An `"interrupted"` child SHALL return its partial `result_text` as a successful result, matching how the interrupt is announced on the live bus.

When the budget expires the returned text SHALL name the child job, state its last recorded status, and instruct the agent not to wait on it again. The abandoned wait SHALL also be recorded on the parent job as a `subagent_failed` event with `reason: "wait_timeout"` and published on the parent's live stream, so a stalled wait is visible in the session timeline and not only in the service log.

A wait SHALL end when cancellation has been requested for the parent job, so a cancelled parent is not held by a child that has not observed the cancellation yet. Giving up on a wait SHALL NOT cancel the child: only the waiting is abandoned.

#### Scenario: Child crashes while the parent is waiting
- **WHEN** a child job crashes during its run while its parent is blocked in `wait_for_subagent`
- **THEN** the wait SHALL return an error result naming the child and its failure code
- **AND** SHALL NOT wait for the full budget to expire

#### Scenario: Child crash never reaches the live event stream
- **WHEN** a child job's own failure handling raises, so only the worker's last-resort guard records the outcome
- **THEN** the waiting parent SHALL still be told the child failed with `error_code = "worker_crash"`

#### Scenario: Child reached its tool round limit
- **WHEN** `wait_for_subagent` is called for a child whose status is `"interrupted"`
- **THEN** the wait SHALL return the child's partial `result_text` as a non-error result

#### Scenario: Child orphaned by a dead worker
- **WHEN** a child job stays in status `"running"` because the worker executing it was killed
- **THEN** the wait SHALL end when its budget expires
- **AND** the returned text SHALL state that the child is still recorded as running and that the parent must stop waiting on it

#### Scenario: A child streaming continuously cannot hold the parent forever
- **WHEN** a child keeps publishing non-terminal events for longer than the wait budget
- **THEN** the wait SHALL end at the budget rather than renewing it on each event

#### Scenario: Abandoned wait is recorded on the parent job
- **WHEN** a wait is abandoned because its budget expired
- **THEN** a `subagent_failed` event SHALL be appended to the parent job with `reason: "wait_timeout"`, the `child_job_id`, and the child's last recorded status

#### Scenario: Parent cancellation releases the wait
- **WHEN** cancellation is requested for a parent job that is blocked in `wait_for_subagent`
- **THEN** the wait SHALL return an error result explaining that the job was cancelled

### Requirement: A crashed job announces its failure as well as recording it
When a prompt run crashes out of its own failure handling, the worker SHALL publish a `failure` live event and append a `failure` job event in addition to marking the job `"failed"` with `error_code = "worker_crash"`, and SHALL terminate the session if the crashed job was a child.

Announcing is what a blocked parent, the child monitor, and the dashboard's event stream depend on: a database-only failure leaves every live consumer waiting for an event that never arrives. Each step SHALL be guarded independently, because this is the last line of defence and a second failure here MUST NOT undo the steps that already succeeded.

#### Scenario: Crash guard publishes the failure
- **WHEN** a job crashes outside prompt-run failure handling
- **THEN** a `failure` event with `code = "worker_crash"` SHALL be published on the job's live event stream
- **AND** the same failure SHALL be persisted as a job event

#### Scenario: Crashed child session is released
- **WHEN** the crashed job is a child job
- **THEN** its session SHALL be terminated rather than left active

## MODIFIED Requirements

### Requirement: spawn_subagent creates monitored child jobs without blocking
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, name the child session from the prompt, and return a tool result immediately containing the `child_job_id` and derived `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task SHALL monitor the child job, append the child outcome to the parent job's event log, and terminate the child session when the child reaches a terminal state.

The monitor SHALL resolve the child's outcome the same way `wait_for_subagent` does — from the child's persisted status, with live events short-circuiting the wait — so the reported outcome is the child's actual fate and not a timeout observed because no event was ever published. The `reason` on a `subagent_failed` event SHALL be the terminal status the child reached (`failed`, `cancelled`) or why the monitor stopped observing, and SHALL carry the child's `error_code` and `error_message` when it has them. A child that ended `"interrupted"` produced usable partial work and SHALL be reported as `subagent_completed`.

#### Scenario: Child session created and configured
- **WHEN** `spawn_subagent` is called with a valid prompt
- **THEN** the worker SHALL create a new `AgentSession` via the repository
- **THEN** the worker SHALL name the child session with the first 50 characters of the prompt, truncated without ellipsis
- **THEN** the worker SHALL copy the parent session's model config and skill assignments

#### Scenario: Child job enqueued with parent reference
- **WHEN** the child session is configured
- **THEN** the worker SHALL enqueue a prompt job with `parent_job_id` pointing to the current parent job
- **THEN** the child job SHALL begin running concurrently via `asyncio.create_task`

#### Scenario: spawn_subagent returns immediately
- **WHEN** the child job is enqueued and started
- **THEN** `spawn_subagent` SHALL return a tool result immediately with `child_job_id` and `name` without waiting for the child to finish
- **THEN** the parent agent SHALL continue its own reasoning and may spawn additional subagents

#### Scenario: subagent_started payload includes name
- **WHEN** `spawn_subagent` emits `subagent_started`
- **THEN** the event payload SHALL include `child_job_id`, `child_session_id`, and `name`

#### Scenario: Background task monitors child and emits outcome
- **WHEN** the child job reaches a terminal state
- **THEN** a background coroutine SHALL append `subagent_completed` or `subagent_failed` to the parent job's event log
- **THEN** the background coroutine SHALL terminate the child session

#### Scenario: Monitor reports the child's real failure
- **WHEN** a child job crashes
- **THEN** the `subagent_failed` event on the parent job SHALL carry `reason: "failed"` together with the child's `error_code` and `error_message`
