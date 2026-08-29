## Why

`wait_for_subagent` currently trusts a caller-supplied job id and can return the persisted result of any job. A built-in caller must be restricted to the child jobs owned by its current parent job and orchestrator session before the wait begins, so another session's agent output cannot cross the job boundary.

## What Changes

- Authorize `wait_for_subagent` requests by requiring the referenced job's persisted `parent_job_id` to name the current parent and the current parent job's persisted session to match the bound orchestrator session, before subscribing, polling, or returning any outcome text.
- Return a generic error for missing ownership without exposing the referenced job's status, result, or failure details.
- Preserve successful waits for an owned child and the existing absolute timeout and parent-cancellation outcomes.
- Add focused regression coverage for owned children, foreign parent/session jobs, and unchanged timeout/cancellation paths.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: restrict subagent wait results to children of the current parent job in the current orchestrator session.

## Non-goals

- Changing which jobs may spawn subagents; that boundary is covered by DRA-67.
- Changing game-tool session or seat binding; that boundary is covered by DRA-79.
- Changing child monitoring, job cancellation propagation, timeout budgets, or result formatting for authorized children.
- Adding a new persistence field or changing the public HTTP API.
