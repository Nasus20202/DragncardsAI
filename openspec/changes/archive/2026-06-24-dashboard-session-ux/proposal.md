## Why

The Play workspace accumulates stale terminated sessions in the sidebar with no way to remove them, resets every setting to config defaults whenever a new session is created, yanks the chat transcript to the bottom while the user is reading, and fails the entire dashboard load when a single provider call is slow or unavailable. These four rough edges make the Play feature frustrating for day-to-day use.

## What Changes

- **Session list cleanup**: add a per-session terminate/remove control to the session list and hide terminated sessions from the sidebar by default, reusing the existing terminate flow.
- **Preserve settings on new session**: carry the last-used settings (provider, model, reasoning, skills, replay limits, MCP/advanced options) forward when creating a new session instead of resetting to config defaults.
- **Transcript scroll lock**: auto-scroll the transcript only while the user is at/near the bottom; when the user scrolls up, stop auto-scrolling and show a "Jump to latest" control that re-locks and scrolls to bottom.
- **Resilient provider/model loading**: degrade gracefully when some providers are slow or unavailable so the rest of the dashboard still loads and the user can select models on working providers.

## Capabilities

### New Capabilities
<!-- None - all changes modify the existing `dashboard` capability -->

### Modified Capabilities
- `dashboard` — session list, session creation defaults, transcript scrolling, and initial provider/model loading behavior.

## Impact

- **Affected code**:
  - `services/dashboard/features/play/components/play-session-list.tsx`
  - `services/dashboard/features/play/components/play-workspace.tsx`
  - `services/dashboard/features/play/lib/session-draft.ts`
  - `services/dashboard/features/play/lib/use-play-session-actions.ts`
  - `services/dashboard/features/play/components/play-transcript.tsx`
  - `services/dashboard/features/play/lib/use-play-session-loader.ts`
  - `services/dashboard/features/play/lib/use-play-session.ts`
- **Tests**: existing Vitest unit suite; lint/typecheck/build.
- **Dependencies**: none — pure frontend changes reusing existing agent-orchestrator APIs.
