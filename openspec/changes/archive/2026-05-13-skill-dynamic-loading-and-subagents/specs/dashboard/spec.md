<!-- Scope: this delta covers dashboard behaviour changes introduced by this change.
     See openspec/specs/dashboard/spec.md for the full dashboard spec. -->

## MODIFIED Requirements

### Requirement: Context health indicator
The dashboard UI SHALL display a context health indicator for the active session. The indicator
SHALL show: a token usage progress bar, usage percentage, `tokens_used` / `context_window_size`,
compaction count, and last-compacted timestamp (or "Never").

The dashboard SHALL present context usage as an estimate of the next orchestrator model request
envelope, not as cumulative historical job usage.

The indicator SHALL update by re-fetching `GET /sessions/{session_id}/context` after each of the
following events:
- A job completes, fails, or is cancelled (SSE terminal event)
- A compaction fires (SSE `compaction` event)
- The user saves session configuration (model, skills, MCPs, or replay limits)

#### Scenario: Context indicator refreshes after job completes
- **WHEN** a job reaches a terminal state
- **THEN** the context health indicator re-fetches and updates to reflect the new token estimate

#### Scenario: Context indicator refreshes after compaction
- **WHEN** a compaction event is received over SSE
- **THEN** the context health indicator re-fetches and reflects reduced `tokens_used` and
  incremented `compaction_count`

#### Scenario: Context indicator refreshes after configuration save
- **WHEN** the user saves session configuration (any combination of model config, skill
  assignments, MCP assignments, or replay limit changes)
- **THEN** the context health indicator re-fetches `GET /sessions/{session_id}/context`
  immediately after the save completes successfully
- **THEN** the displayed token estimate reflects the updated system prompt, tool definitions,
  and replay window resulting from the new configuration

## ADDED Requirements

### Requirement: Session title auto-generated from first prompt
When the user submits the first prompt to a newly created session the dashboard SHALL PATCH the
session name to the first 60 characters of the prompt text, replacing the default timestamp name.
Subsequent prompts SHALL NOT overwrite the name. A name already set by the user SHALL NOT be
overwritten.

#### Scenario: Name set on first prompt
- **WHEN** the user submits a prompt and no non-timestamp name has been set on the session
- **THEN** the dashboard calls `PATCH /sessions/{id}` with `name = prompt.slice(0, 60)`
- **THEN** the session list label updates to the new name

#### Scenario: Subsequent prompts leave name unchanged
- **WHEN** the user submits a second or later prompt in the same session
- **THEN** no PATCH is sent for the session name

### Requirement: Subagent cards rendered inline in the chat area
The dashboard SHALL render each spawned subagent as an expandable card in the main chat column,
positioned above the context health widget and below the main job thread. The card SHALL use the
same `JobThread` / `AggEventRow` transcript rendering as the parent thread. There SHALL be no
subagent panel in the config sidebar.

#### Scenario: Subagent card appears on subagent_started
- **WHEN** the parent job's SSE stream emits `subagent_started`
- **THEN** a subagent card is inserted in the chat area with the subagent's `name` (from the event
  payload) as its header title
- **THEN** the card immediately opens an SSE connection to the child job's event stream and begins
  rendering events live

#### Scenario: Subagent card stops streaming on terminal event
- **WHEN** the child job's SSE stream emits a terminal event (`completion` or `failure`)
- **THEN** the card closes its SSE connection and switches to static display

#### Scenario: Multiple subagent cards stack in order
- **WHEN** multiple `subagent_started` events are received
- **THEN** each gets its own card stacked below the previous one in chronological order

#### Scenario: Subagent card collapses / expands
- **WHEN** the user clicks the subagent card header
- **THEN** the card body (transcript) toggles collapsed / expanded

#### Scenario: Config sidebar has no subagent panel
- **THEN** the config sidebar does NOT contain a SubagentPanel component or any subagent list
