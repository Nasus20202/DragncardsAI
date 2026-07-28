# Real session deletion, inherited settings, a transcript follow lock, and model selection that survives a degraded catalogue

## Why

Four rough edges in the Play workspace, reported together after a play session.

**Old sessions cannot be removed.** The session list's `✕` control looks like a
delete, and its confirmation dialog said the session would be "removed from the
list", but it only called the orchestrator's *terminate* endpoint. Terminated
sessions are hidden from the sidebar, so the session appeared to go — while the
row, its model configuration, its enabled skills and MCPs, its player configs and
its entire transcript stayed in Postgres forever, with no endpoint that could ever
remove them. `DELETE /sessions/{id}` did not exist; the path only matched GET and
PATCH.

**Creating a session throws the configuration away on reload.** The new-session
flow already carried the current draft forward, but nothing outlived a page
reload: after reopening the dashboard with no session selected, the draft reset to
the deployment defaults and the user re-picked provider, model, reasoning and
skills by hand.

**Streaming output fights the reader.** The transcript auto-followed new content,
and scrolling up was supposed to release it — but the release never took while the
agent was writing. Auto-follow re-armed a programmatic-scroll guard on every
token, and that guard swallowed the very scroll events that were meant to signal
"the user took over", so the viewport kept snapping back to the bottom mid-read.

**A provider without an API key breaks model selection for every provider.** A
provider that has no key answers the model listing successfully with an empty
list, so it reports `available: true` and no notice was shown. All such providers
were nevertheless offered in the provider picker, and choosing one left the model
picker disabled showing another provider's model — which the dashboard then
committed to the session. On a deployment where six of seven providers have no key
this reads exactly as reported: "I cannot change the models, even in the correctly
working providers."

## What Changes

- **agent-orchestrator (session deletion)** — the service SHALL expose
  `DELETE /sessions/{session_id}`, returning 204 on success and 404 for an unknown
  session. It is a hard delete with terminate-then-delete semantics: cancellation
  is requested for any queued or running job first, so a worker mid-run observes
  the cancellation flag rather than discovering that its rows vanished, and then
  the session is removed together with its model configuration, enabled skills,
  MCP assignments, player configurations, jobs, transcript events, job outputs and
  compaction records. Terminate is unchanged and remains the way to end a session
  while keeping its history.
- **agent-orchestrator (no orphaned rows)** — every dependent row SHALL be deleted
  explicitly rather than relying on the declared `ON DELETE CASCADE` constraints.
  SQLite (which backs both test suites) does not enforce foreign keys without a
  per-connection pragma, and `compaction_records` has no ORM cascade from
  `AgentSession` at all, so cascade-only deletion would silently orphan transcript
  rows on some backends. Jobs in other sessions that point at a deleted job have
  their `parent_job_id` cleared, matching the constraint's `ON DELETE SET NULL`.
  No schema change and therefore no migration is required.
- **dashboard (deletion wired end to end)** — the session list's removal control
  SHALL call the new delete endpoint instead of terminate, drop the session from
  the list, and reselect the next visible session. The confirmation dialog's
  wording SHALL match what now happens: a permanent deletion of the session with
  its settings and full transcript, with running work cancelled first.
- **dashboard (settings survive a reload)** — the configuration the user last
  committed SHALL be remembered per browser in `localStorage` and used to seed the
  draft on a later visit, so a new session starts from those settings rather than
  the deployment defaults. A session the user opens SHALL keep its own settings;
  the remembered configuration only seeds a draft that has no session behind it,
  and the session name is never carried forward.
- **dashboard (transcript follow lock)** — a user gesture SHALL release the follow
  lock even while output is streaming: an upward wheel, an upward scrolling key,
  or a touch drag away from the bottom releases it immediately, cancels the
  in-flight programmatic scroll and leaves the viewport where the user put it. The
  existing jump-to-latest control re-engages the lock, and so does scrolling back
  to the bottom. Because the transcript resizes for reasons the job list does not
  capture, its content box is observed: while locked, late growth is followed, and
  while released, content shrinking back within one viewport re-engages instead of
  stranding the control with nowhere to scroll.
- **dashboard (usable-provider selection)** — provider usability SHALL be judged
  by whether the provider offers any model, not only by its `available` flag. A
  provider with no models SHALL be labelled as such in the provider picker and
  SHALL NOT be selectable, so the user cannot strand themselves on a disabled model
  picker, while a session already pinned to one still shows its provider and can be
  moved to a working one. The non-blocking notice SHALL name those providers.
  A degraded catalogue SHALL NOT reset a carried provider/model either: an empty
  catalogue is no evidence that the user's provider is broken.

## Non-goals

- Any further HeroUI conversion or restyling of existing dashboard components. The
  existing dashboard is the visual reference; this change alters behaviour, three
  strings, and adds no new visual language.
- Bulk session deletion, an undo window, soft-delete/archive states, or a
  retention policy. Deletion is per session, immediate, and permanent.
- Cascading deletion into the subagent child sessions a parent spawned. Their jobs
  are detached rather than removed, and they remain hidden from the sidebar as
  before.
- Server-side storage of the last-used configuration. It is a per-browser UI
  preference; storing it in a service would leak one operator's last choice into
  every other browser, and services must not hold state of their own.
- Re-probing an unavailable provider from the dashboard. The orchestrator already
  exposes `POST /providers/refresh` for that.

## Impact

- Affected specs: `agent-orchestrator` (new session deletion requirement),
  `dashboard` (session-list removal is now a deletion; new sessions preserve
  last-used settings across reloads; transcript scroll lock; resilient provider and
  model loading).
- Affected code: `services/agent-orchestrator/src/agent_orchestrator/api/routers/sessions.py`,
  `services/agent-orchestrator/src/agent_orchestrator/repositories/sessions.py`,
  `services/dashboard/features/play/lib/client-api.ts`,
  `services/dashboard/features/play/lib/use-play-session-actions.ts`,
  `services/dashboard/features/play/lib/use-play-session.ts`,
  `services/dashboard/features/play/lib/use-play-session-loader.ts`,
  `services/dashboard/features/play/lib/session-draft.ts`,
  `services/dashboard/features/play/lib/last-used-draft.ts` (new),
  `services/dashboard/features/play/components/play-transcript.tsx`,
  `services/dashboard/features/play/components/play-config-panel.tsx`,
  `services/dashboard/features/play/components/remove-session-modal.tsx`,
  `services/dashboard/features/play/components/play-session-list.tsx`.
- No schema, migration, or configuration changes.
