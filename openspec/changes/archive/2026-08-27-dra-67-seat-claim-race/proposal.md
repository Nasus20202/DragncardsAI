## Why

Concurrent first prompts for the same configured player seat can create two child sessions. The database claim correctly selects one owner, but the losing child is still scheduled and reaches game-service without seat authorization. This fix closes that race before the losing child can run.

## What Changes

- Treat a failed persistent seat-session claim as a failed child launch.
- Terminate the losing child session and do not enqueue or schedule its job.
- Return an explicit error from the prompt tool so the orchestrator can retry against the persisted seat owner.
- Add regression coverage for the handler-level race path, including the absence of a scheduled losing job.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: persistent player-seat session claims reject and clean up losing concurrent launches before execution.

## Non-goals

- Changing the existing seat authorization rules.
- Changing generic subagent scheduling or `wait_for_subagent` ownership.
- Reassigning an already-owned seat session.
