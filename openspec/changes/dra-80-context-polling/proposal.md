# Poll context usage during generation

## Why

The Play context health indicator only refreshes after a generation reaches a terminal state, so its usage breakdown stays stale while a model is still producing output. Polling the existing context endpoint during active generation lets the dashboard show the evolving request envelope without changing how the orchestrator calculates context usage.

## What Changes

- Refresh the selected session's context metadata immediately when generation starts.
- Poll the existing `GET /sessions/{session_id}/context` endpoint on a bounded cadence while a generation is active.
- Serialize context refreshes so a slow request cannot overlap the next poll or another refresh trigger.
- Stop and clean up the polling timer when generation ends, the selected session changes, or the Play workspace unmounts; retain the existing immediate terminal refresh.
- Add focused dashboard hook coverage for initial active refresh, periodic polling, overlap prevention, and timer cleanup.

## Capabilities

### Modified Capabilities

- `dashboard`: the context health indicator refreshes during active generation as well as at existing lifecycle boundaries.

## Impact

- Dashboard Play session context-refresh orchestration and a small polling hook.
- Focused Vitest coverage only; no agent-orchestrator context calculation or API changes.

## Non-goals

- Changing the context metadata response, token accounting, or orchestrator calculation semantics.
- Changing the context health widget's visual fields, thresholds, loading behavior, or error presentation.
- Adding browser automation or running the full dashboard test suite for this change.
