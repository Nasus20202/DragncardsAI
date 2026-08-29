## Context

`usePlaySession` owns the selected session and context metadata state. It already refreshes metadata when loading a session, after configuration saves, and through the streaming hook when a compaction or terminal event is observed. `streamingJobId` is the dashboard's existing generation-active signal: it is set when the job stream starts and cleared when streaming finishes or is stopped.

The context endpoint is deliberately read through the existing `getContextMetadata` client function. The dashboard must add no endpoint or orchestrator behavior; this change only controls when the existing function is called.

## Goals / Non-Goals

**Goals:**

- Make context metadata update immediately when a job stream becomes active.
- Keep refreshing during active streaming at a bounded five-second cadence.
- Prevent a slow metadata request from overlapping a later poll or another same-session refresh trigger.
- Tear down timers on generation/session lifecycle changes and unmount.
- Preserve the existing best-effort error handling and terminal refresh path.

**Non-goals:**

- Changing token calculation, response fields, or agent-orchestrator context semantics.
- Moving presentation logic into the polling hook or changing the widget UI.
- Replacing the existing EventSource stream or adding browser-only polling behavior.

## Decisions

### Poll from a dedicated Play hook

Add `useContextMetadataPolling` beside the existing Play session hooks. The hook receives the selected session id, the existing `streamingJobId`-derived active flag, and a refresh callback. It performs one immediate refresh when active, then self-schedules a timeout after each settled refresh. A self-scheduling timeout is used instead of `setInterval`, so the next request cannot start until the previous one settles.

The hook stores the latest callback in a ref and uses a cancellation flag plus timeout cleanup in the effect cleanup. This keeps dependency changes from leaving a timer attached to an old session and avoids stale callback captures. The hook does not own loading or error state.

### Serialize refreshes at the existing context callback

`refreshContextMetadata` remains the single callback used by session loading, saves, streaming compactions/terminal events, manual compaction, and polling. It keeps a per-session state containing the in-flight promise and whether another trigger arrived while that request was running. A new trigger for a session coalesces with the current request and schedules one trailing refresh after it settles, while requests for newly selected sessions proceed independently. This protects polling from racing the completion or compaction refresh without dropping a lifecycle refresh, and preserves the callback's current non-fatal catch behavior.

### Retain terminal refresh in streaming

`useJobStreaming` already invokes `refreshContextMetadata` as soon as the terminal event stops streaming. That behavior remains the authoritative completion/failure/cancellation refresh. The new polling hook handles the generation-start refresh and active-period polls; it stops as soon as `streamingJobId` is cleared.

## Risks / Trade-offs

- A five-second cadence adds a small amount of read traffic only while a generation is active; self-scheduling and per-session serialization bound that traffic and prevent request pileups.
- A request already in flight when streaming stops is allowed to settle, but its timer is never re-armed and no new poll is scheduled.
- The existing callback's state update behavior is preserved, including its best-effort handling of endpoint errors.

## Verification

Run the focused polling hook test file from the dashboard package. It uses fake timers and a deferred refresh promise to prove immediate active refresh, periodic settled polling, no overlap, stop-on-inactive behavior, dependency cleanup, and unmount cleanup. Full dashboard tests and browser verification are intentionally outside this batch's scope.
