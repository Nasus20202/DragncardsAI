## Context

The seat-session database update already uses a conditional `UPDATE` so only one concurrent child session can claim an unclaimed seat. The launch callback currently discards the boolean result, allowing a losing child to continue through model setup and job scheduling. Seat identity resolution then rejects that child, but the child still has inherited game-service tools and is no longer protected by the seat guard.

## Goals / Non-Goals

**Goals:**

- Make a failed first-session claim terminal for the losing child launch.
- Ensure no losing child job is persisted, monitored, or scheduled.
- Leave the winning roster mapping unchanged.
- Give the coordinator a retryable error result.

**Non-Goals:**

- Changing the atomic database claim semantics.
- Serializing all prompts for an already-owned seat.
- Changing generic subagent ownership or wait behavior.

## Decisions

1. **Propagate the claim result through the child-launch callback.**
   - The seat-specific callback returns whether it installed the child session.
   - The shared launcher handles the result immediately after child creation.
   - Alternative rejected: keep logging only, because it leaves an unauthorized child runnable.

2. **Terminate and reject the losing child before configuration or enqueue.**
   - The launcher marks the losing session terminated and returns an MCP error result.
   - No child job, monitor, or scheduler callback is invoked.
   - Alternative rejected: enqueue first and reject in the worker, because the worker can begin before authorization is re-evaluated and the job would still pollute the parent timeline.

3. **Ask the coordinator to retry rather than redirect inside the launcher.**
   - The error tells the coordinator that another prompt won the claim and that it should retry the seat prompt. A retry re-reads the persisted owner through the existing path.
   - Alternative rejected: fetch and enqueue against the winner from the losing invocation, because that couples the claim callback to prompt construction and can duplicate a still-running seat job.

## Risks / Trade-offs

- A concurrent losing prompt receives an error and needs one model retry; this is safer than executing an unregistered child.
- Termination is a repository update after child creation. If termination itself fails, the launcher still refuses to enqueue the child and logs the failure, so no unauthorized child job is started.
- The DragnCards WebSocket/game-service protocol is not changed; the fix prevents an unauthorized child from reaching that protocol at all.
