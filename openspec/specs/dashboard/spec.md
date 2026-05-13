# Dashboard Spec

## Purpose

This spec describes the Next.js dashboard application for DragnCardsAI, including the application shell, Play workspace, session management, live chat and streaming event rendering, Swagger playground, and service configuration.

## Requirements

### Requirement: Dashboard application shell
The system SHALL provide a Next.js dashboard application with a dark-mode-capable HeroUI interface and top-level navigation for `Play` and `Swagger` sections.

#### Scenario: Navigate between dashboard sections
- **WHEN** a user opens the dashboard in a browser
- **THEN** the system SHALL display a top navbar with `Play` and `Swagger` navigation entries

#### Scenario: Use dark mode
- **WHEN** the user enables dark mode or the browser prefers dark mode
- **THEN** the dashboard SHALL render the application shell and main content using dark-compatible HeroUI styling

### Requirement: Play session workspace
The system SHALL provide a Play workspace with a left session sidebar, centre chat transcript, right inline settings panel, and bottom prompt input — all filling the full viewport height without page-level scrolling.

#### Scenario: View play layout
- **WHEN** a user opens the Play section on a desktop viewport
- **THEN** the dashboard SHALL show a session list on the left, live chat transcript in the centre, a settings panel on the right, and a prompt input at the bottom

#### Scenario: Session selection persisted across reloads
- **WHEN** a user selects a session and reloads the page
- **THEN** the dashboard SHALL restore the previously selected session from local storage

### Requirement: Agent session management
The dashboard SHALL allow users to create, select, inspect, update, and terminate agent sessions through agent-orchestrator APIs.

#### Scenario: Create session with defaults
- **WHEN** a user creates a new Play session
- **THEN** the dashboard SHALL name it with the current date and time, submit it to the agent-orchestrator, and display the created session in the sidebar

#### Scenario: Inspect selected session
- **WHEN** a user selects a session from the sidebar
- **THEN** the dashboard SHALL show the session status, model/provider configuration, assigned MCPs, assigned skills, and job history in the transcript

#### Scenario: Terminate session
- **WHEN** a user terminates an active session from the dashboard
- **THEN** the dashboard SHALL call the agent-orchestrator termination API and update the session status in the UI

### Requirement: Play workspace orchestration is owned by one play session Module
The dashboard SHALL concentrate selected-session loading, configuration sync, prompt submission, cancellation, transcript loading, and context refresh behind one play session Module Interface.

React view Modules in the Play workspace SHALL act as Adapters over that Interface rather than owning orchestration behavior directly.

#### Scenario: Play workspace delegates session lifecycle behavior
- **WHEN** the user creates, selects, updates, compacts, submits a prompt for, or cancels execution in a session
- **THEN** the Play workspace SHALL delegate that orchestration behavior through the same play session Module Interface

#### Scenario: Play session Module reconciles history load and stream attachment
- **WHEN** a selected session reloads while its newest job is queued or running
- **THEN** the play session Module SHALL reconcile transcript history loading and stream attachment
- **AND** SHALL preserve one sorted jobs view for the session

### Requirement: Session configuration controls
The dashboard SHALL expose HeroUI controls for model/provider selection, MCP assignments, skill assignments, reasoning toggle, and other session defaults in an inline settings panel.

The same settings panel SHALL expose structured controls for session memory replay behavior, including whether replay remains unbounded or is limited by recent conversational message count and recent tool-exchange count.

#### Scenario: Configure model and provider
- **WHEN** a user edits the model/provider configuration for a session
- **THEN** the dashboard SHALL provide a filterable ComboBox for model selection and a Select for provider, and SHALL submit changes to the agent-orchestrator

#### Scenario: Model auto-corrects on provider change
- **WHEN** a user changes the provider and the current model is not valid for the new provider
- **THEN** the dashboard SHALL automatically select the first valid model for the new provider

#### Scenario: Configure MCPs and skills
- **WHEN** a user edits MCP or skill assignments for a session
- **THEN** the dashboard SHALL submit the requested assignments to the agent-orchestrator and display validation errors clearly if any assignment is rejected

#### Scenario: Configure replay limits
- **WHEN** a user edits the session replay controls in the settings panel
- **THEN** the dashboard SHALL validate numeric replay limits before saving
- **AND** SHALL submit the resulting replay settings as part of the session configuration shown for that session

### Requirement: Replay settings are visible in session details
The dashboard SHALL display the active session's replay settings in the same configuration flow used to inspect and edit model and memory behavior.

#### Scenario: Existing session loads replay settings
- **WHEN** a user selects a session that already has replay limits configured
- **THEN** the dashboard SHALL populate the replay controls with the persisted values returned by the agent-orchestrator

#### Scenario: Unlimited replay settings shown clearly
- **WHEN** a session has no replay limits configured
- **THEN** the dashboard SHALL render an explicit unlimited or empty-state value rather than implying a hidden default count

### Requirement: Context health indicator
The dashboard UI SHALL display a context health indicator for the active session. The indicator SHALL show: a token usage progress bar, usage percentage, `tokens_used` / `context_window_size`, compaction count, and last-compacted timestamp (or "Never").

The dashboard SHALL present context usage as an estimate of the next orchestrator model request envelope, not as cumulative historical job usage.

The indicator SHALL update by re-fetching `GET /sessions/{session_id}/context` after each of the following events:
- A job completes, fails, or is cancelled
- A compaction fires
- The user saves session configuration, including model, skill, MCP, or replay-limit changes

The progress bar SHALL change color based on usage ratio:
- Below 70%: neutral
- 70-85%: amber
- Above 85%: red

#### Scenario: Indicator shown for active session
- **WHEN** a session is active in the dashboard
- **THEN** the context health indicator SHALL be visible with all fields populated

#### Scenario: Indicator color reflects usage level
- **WHEN** `usage_ratio` exceeds 0.85
- **THEN** the progress bar SHALL render in red

#### Scenario: Indicator updates after compaction
- **WHEN** a compaction completes (manual or auto)
- **THEN** the indicator SHALL refresh and reflect reduced `tokens_used` and incremented `compaction_count`

#### Scenario: Indicator refreshes after configuration save
- **WHEN** the user saves session configuration
- **THEN** the context health indicator SHALL re-fetch `GET /sessions/{session_id}/context` immediately after the save completes successfully
- **THEN** the displayed token estimate SHALL reflect the updated system prompt, tool definitions, and replay window resulting from the new configuration

#### Scenario: Multi-turn memory disabled
- **WHEN** `multi_turn_memory` is `false` for the active session
- **THEN** the indicator SHALL display a "Memory off" state and the Compact button SHALL be disabled

#### Scenario: Context usage includes active prompt and tool scaffolding
- **WHEN** the dashboard displays context usage for an active session
- **THEN** the displayed estimate SHALL account for the active system prompt content, retained replay history, and active tool definitions returned by the agent-orchestrator

#### Scenario: Context usage respects replay limits
- **WHEN** replay-window settings exclude older history from the next request
- **THEN** the dashboard SHALL reflect the bounded estimate returned by the agent-orchestrator instead of implying that all prior messages still count equally

### Requirement: Compact button
The dashboard UI SHALL display a `Compact` button within the context health indicator widget. Clicking it SHALL send `POST /sessions/{session_id}/compact` and refresh the indicator on success.

#### Scenario: Compact button triggers compaction
- **WHEN** a user clicks the Compact button for an active session
- **THEN** the dashboard SHALL POST to `/sessions/{session_id}/compact`
- **AND** the indicator SHALL refresh with updated context metadata on success

#### Scenario: Compact button disabled during job
- **WHEN** a job is currently running for the session
- **THEN** the Compact button SHALL be disabled until the job completes

### Requirement: Live chat and orchestration event rendering
The dashboard SHALL provide a ChatGPT-like prompt and transcript interface backed by agent-orchestrator prompt jobs and streaming events, rendered with markdown support.

#### Scenario: Submit prompt
- **WHEN** a user submits a prompt for an active session
- **THEN** the dashboard SHALL create a prompt job through the agent-orchestrator and append the user prompt to the transcript

#### Scenario: First prompt auto-generates session title
- **WHEN** the user submits the first prompt and no non-timestamp name has been set on the session
- **THEN** the dashboard SHALL call `PATCH /sessions/{id}` with the session name set to the first 60 characters of the prompt text
- **THEN** the session list and any visible title area SHALL update to reflect the new name

#### Scenario: Subsequent prompts leave session title unchanged
- **WHEN** the user submits a second or later prompt in the same session
- **THEN** the dashboard SHALL NOT patch the session name

#### Scenario: Render streaming output
- **WHEN** the agent-orchestrator streams job events
- **THEN** the dashboard SHALL render model output as markdown, display reasoning in a collapsible block that auto-collapses when output arrives, and show tool calls and completion state in the transcript

#### Scenario: Suppress script tags in markdown
- **WHEN** model output contains a script tag
- **THEN** the dashboard SHALL suppress it and SHALL NOT execute or render it

#### Scenario: Resume event stream after reconnect
- **WHEN** a user reconnects to an in-progress or completed job
- **THEN** the dashboard SHALL replay all DB events from cursor 0, deduplicate by event ID, and extend in-progress snapshot text with live stream chunks — producing no duplicates and no gaps

#### Scenario: Streaming job tracked atomically
- **WHEN** multiple jobs exist for a session
- **THEN** the dashboard SHALL maintain a single sorted jobs array and a streaming job ID ref to avoid race conditions between history load and live stream state

### Requirement: Dashboard transcript rendering consumes one shared event interpretation Module
The dashboard SHALL interpret streamed and persisted orchestrator job events through one shared transcript/event Module rather than reimplementing terminal, chunk-merge, and subagent reconciliation rules across multiple helpers.

#### Scenario: Transcript helpers share one interpretation path
- **WHEN** job events update model output, reasoning, tool calls, tool results, compaction state, or subagent state
- **THEN** the dashboard SHALL apply those event types through one shared transcript/event interpretation Module

#### Scenario: Reconnect behavior matches orchestrator stream semantics
- **WHEN** the dashboard reconnects to an in-progress job
- **THEN** the dashboard transcript/event Module SHALL reuse orchestrator-compatible cursor and snapshot rules
- **AND** SHALL render the transcript without duplicate or missing events

### Requirement: Subagent cards rendered inline in the chat area
The dashboard SHALL render each spawned subagent as an expandable card in the main chat column, positioned above the context health widget and below the main job thread. The card SHALL use the same `JobThread` / `AggEventRow` transcript rendering as the parent thread. There SHALL be no subagent panel in the config sidebar.

#### Scenario: Subagent card appears on subagent_started
- **WHEN** the parent job's SSE stream emits `subagent_started`
- **THEN** a subagent card is inserted in the chat area with the subagent's `name` as its header title
- **THEN** the card immediately opens an SSE connection to the child job's event stream and begins rendering events live

#### Scenario: Subagent card stops streaming on terminal event
- **WHEN** the child job's SSE stream emits a terminal event
- **THEN** the card closes its SSE connection and switches to static display

#### Scenario: Multiple subagent cards stack in order
- **WHEN** multiple `subagent_started` events are received
- **THEN** each gets its own card stacked below the previous one in chronological order

#### Scenario: Subagent card collapses and expands
- **WHEN** the user clicks the subagent card header
- **THEN** the card body toggles collapsed or expanded

#### Scenario: Config sidebar has no subagent panel
- **WHEN** subagent activity exists for the active session
- **THEN** the config sidebar SHALL NOT contain a subagent panel or subagent list

### Requirement: Merged Swagger playground
The dashboard SHALL provide a Swagger section that displays a merged OpenAPI document for agent-orchestrator and game-service and routes playground calls through dashboard proxy routes.

#### Scenario: View merged OpenAPI document
- **WHEN** a user opens the Swagger section
- **THEN** the dashboard SHALL fetch or serve a merged OpenAPI document containing the configured agent-orchestrator and game-service APIs

#### Scenario: Proxy playground request
- **WHEN** a user executes an API request from the Swagger playground
- **THEN** the dashboard SHALL proxy the request to the matching upstream service and return the upstream response to the playground

#### Scenario: Upstream spec unavailable
- **WHEN** one configured service OpenAPI document cannot be fetched
- **THEN** the dashboard SHALL still report the error clearly and SHALL render any available service specs when possible

### Requirement: Proxy and merged OpenAPI remain thin Adapters
The dashboard SHALL keep proxy forwarding and merged OpenAPI generation independent from Play workspace orchestration state.

#### Scenario: Proxy behavior ignores play session state
- **WHEN** a Play session is selected, running, cancelled, or terminated
- **THEN** proxy request forwarding SHALL continue to depend only on configured upstream service settings and the incoming request

#### Scenario: Merged OpenAPI generation ignores play session state
- **WHEN** the dashboard builds or serves the merged OpenAPI document
- **THEN** the merged document and any upstream fetch errors SHALL be derived only from configured upstream documents
- **AND** SHALL NOT depend on Play workspace state

### Requirement: Dashboard service configuration
The dashboard SHALL use non-secret environment configuration for service base URLs, OpenAPI source paths, and default session settings.

#### Scenario: Load service endpoints from environment
- **WHEN** the dashboard starts
- **THEN** it SHALL read agent-orchestrator and game-service base URLs from environment-backed configuration

#### Scenario: Missing required service configuration
- **WHEN** required dashboard service URLs are missing
- **THEN** the dashboard SHALL show a clear configuration error instead of silently sending requests to an invalid target

### Requirement: Dashboard code quality
The dashboard SHALL pass ESLint and TypeScript checks with no errors, using HeroUI components for all controls, ES module imports at the top of each file only, and no inline type imports.

#### Scenario: Lint and typecheck pass
- **WHEN** `pnpm lint` and `pnpm typecheck` are run against the dashboard source
- **THEN** both SHALL exit with no errors
