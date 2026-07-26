## Context

All four improvements are frontend-only changes to the Play workspace under `services/dashboard/features/play/`. They reuse existing agent-orchestrator APIs (terminate, providers, sessions) and existing HeroUI patterns. No backend or API contract changes.

## Goals / Non-Goals

**Goals:**
- Let users remove stale sessions from the sidebar without inventing a new backend endpoint.
- Make new sessions inherit the user's last-used settings.
- Stop the transcript from yanking to the bottom while the user reads.
- Keep the dashboard usable when some providers fail or are slow.

**Non-Goals:**
- Hard-deleting sessions (terminate + filter only).
- Adding new orchestrator endpoints.
- Changing streaming/event-interpretation semantics.

## Decisions

**Decision**: Hide terminated sessions by filtering on `status`/`terminated_at` in the workspace rather than deleting them.
- **Rationale**: Terminate is the only available destructive flow and is non-destructive to history; filtering keeps it reversible server-side.

**Decision**: Capture the last-used draft (or the current draft) as the seed for `createDefaultDraft`, falling back to config defaults.
- **Rationale**: The active draft already reflects the user's last edits; reusing it preserves provider/model/reasoning/skills/limits/advanced options without new state.

**Decision**: Track a "locked" flag derived from a near-bottom threshold on the scroll container's scroll event, and only call `scrollIntoView` while locked.
- **Rationale**: Mirrors VSCode/terminal scroll-lock behavior; a small threshold tolerates sub-pixel rounding and smooth-scroll lag.

**Decision**: Replace the load `Promise.all` with `Promise.allSettled` and surface unavailable providers as a non-blocking notice.
- **Rationale**: One slow/failed call must not break the whole dashboard; the provider/model selectors must still default to a working provider.

## Risks / Trade-offs

- **Risk**: Filtering terminated sessions could hide a session the user still wants to inspect. **Mitigation**: terminate is explicit and confirmed; server data is retained.
- **Risk**: Seeding from last-used draft could carry forward an invalid model for a provider. **Mitigation**: existing `normalizeDraft` already corrects model-to-provider mismatches.
- **Risk**: allSettled hides which call failed. **Mitigation**: surface a per-area notice (providers unavailable) rather than a single fatal error.
