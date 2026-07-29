# Dashboard Spec

## Purpose

This spec describes the Next.js dashboard application for DragnCardsAI, including the application shell, Play workspace, session management, live chat and streaming event rendering, Swagger playground, and service configuration.
## Requirements
### Requirement: Dashboard application shell
The system SHALL provide a Next.js dashboard application with a dark-mode-capable HeroUI interface and top-level navigation for `Play`, `Games`, `History`, and `Swagger` sections, plus an entry linking out to the Bifrost gateway UI.

#### Scenario: Navigate between dashboard sections
- **WHEN** a user opens the dashboard in a browser
- **THEN** the system SHALL display a top navbar with `Play`, `Games`, `History`, and `Swagger` navigation entries

#### Scenario: Use dark mode
- **WHEN** the user enables dark mode or the browser prefers dark mode
- **THEN** the dashboard SHALL render the application shell and main content using dark-compatible HeroUI styling

### Requirement: Bifrost gateway UI link
The dashboard navigation SHALL include a `Bifrost` entry that opens the Bifrost AI gateway's own web UI. Because Bifrost is a separate application rather than a dashboard route, the entry SHALL open in a new browsing context using `target="_blank"` together with `rel="noopener noreferrer"`, SHALL carry a marker indicating it leaves the dashboard, and SHALL never be rendered in the active-route state. The entry SHALL render with the same typography, spacing, and hover treatment as the internal navigation entries.

The gateway UI address SHALL be read from the `BIFROST_UI_URL` environment variable and exposed on the public dashboard configuration. This address is the browser-reachable one and SHALL be configured independently of the services' Docker-internal `BIFROST_URL`.

#### Scenario: Bifrost entry opens the gateway UI in a new tab
- **WHEN** a user views the dashboard navigation
- **THEN** the dashboard SHALL render a `Bifrost` entry whose href is the configured Bifrost UI URL, with `target="_blank"` and `rel="noopener noreferrer"`

#### Scenario: Bifrost entry matches the internal navigation styling
- **WHEN** the `Bifrost` entry is rendered
- **THEN** it SHALL use the same idle navigation styling as the internal entries and SHALL NOT be highlighted as the active route

#### Scenario: Missing Bifrost UI URL uses local development default
- **WHEN** the `BIFROST_UI_URL` environment variable is not set
- **THEN** the dashboard SHALL fall back to `http://localhost:4003` as the Bifrost UI target

#### Scenario: Configured Bifrost UI URL is honoured
- **WHEN** `BIFROST_UI_URL` is set to a deployment-specific address
- **THEN** the dashboard SHALL use that address as the Bifrost UI target

### Requirement: Play session workspace
The system SHALL provide a Play workspace with a left session sidebar, centre chat transcript, right inline settings panel, and bottom prompt input — all filling the full viewport height without page-level scrolling.

#### Scenario: View play layout
- **WHEN** a user opens the Play section on a desktop viewport
- **THEN** the dashboard SHALL show a session list on the left, live chat transcript in the centre, a settings panel on the right, and a prompt input at the bottom

#### Scenario: Session selection persisted across reloads
- **WHEN** a user selects a session and reloads the page
- **THEN** the dashboard SHALL restore the previously selected session from local storage

### Requirement: Games session workspace
The dashboard SHALL provide a Games workspace with a left session sidebar and centre embedded iframe viewer, filling the full viewport height without page-level scrolling.

#### Scenario: View games layout
- **WHEN** a user opens the Games section on a desktop viewport
- **THEN** the dashboard SHALL show a game list on the left and an iframe viewer in the centre

### Requirement: Game session list
The dashboard SHALL fetch and display a list of active game sessions from the game-service `/games` endpoint.

#### Scenario: Games list shows active sessions
- **WHEN** a user opens the Games view
- **THEN** the dashboard SHALL fetch games from the game-service and display each session's room slug and plugin name

#### Scenario: Games list ordered by newest first
- **WHEN** multiple game sessions are active
- **THEN** the dashboard SHALL sort them by `created_at` descending before rendering the list

#### Scenario: Empty games list shown when no active sessions
- **WHEN** no game sessions are active
- **THEN** the dashboard SHALL display an empty state message

### Requirement: Embedded DragnCards iframe
The dashboard SHALL embed the DragnCards frontend in an iframe, showing the selected game room.

#### Scenario: Iframe loads selected game
- **WHEN** a game is selected in the Games view
- **THEN** the dashboard SHALL render an iframe pointing to the DragnCards frontend URL using the `/room/{room_slug}` path

#### Scenario: Placeholder shown when no game selected
- **WHEN** no game is selected
- **THEN** the dashboard SHALL display a placeholder in the iframe area indicating no game is selected

### Requirement: DragnCards frontend URL configuration
The dashboard SHALL read the DragnCards frontend URL from the `DRAGNCARDS_FRONTEND_URL` environment variable.

#### Scenario: Missing frontend URL uses local development default
- **WHEN** the DRAGNCARDS_FRONTEND_URL environment variable is not set
- **THEN** the dashboard SHALL fall back to `http://localhost:3000` for the embedded iframe target

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

Each toggle control SHALL be fully clickable: clicking the visual switch (its track or thumb) SHALL flip the toggle, not only clicking the adjacent text label.

Model selection SHALL use one shared searchable picker component, so that every place in the dashboard that chooses a model from the provider catalog filters that catalog the same way. The picker SHALL retain what the user has typed across re-renders of the panel that owns it, so an unrelated state change elsewhere in that panel does not discard an in-progress search.

The labelled field wrappers used by this panel — the field label, text input, textarea, select, searchable select, toggle row, and skills toggle list — SHALL live in one shared component module rather than inside a single feature's panel, so any other panel that configures a provider, model, reasoning, prompt, or skill set renders the same controls instead of hand-rolling equivalents. A panel in one feature SHALL NOT import these controls from another feature's directory. Sharing these wrappers SHALL NOT change what this settings panel renders.

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

#### Scenario: Clicking the toggle control flips the switch
- **WHEN** a user clicks directly on a session-config toggle's switch control (its track or thumb), not the text label
- **THEN** the dashboard SHALL flip that toggle, because the switch control is rendered inside the clickable switch content rather than as a sibling of it

#### Scenario: Field wrappers are shared, not per-feature
- **WHEN** another dashboard panel needs a labelled provider select, model picker, reasoning toggle, numeric or text field, prompt textarea, or skills toggle list
- **THEN** it SHALL render the shared field components used by this settings panel, and this settings panel's own rendered output SHALL be unaffected by that reuse

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

The dashboard SHALL expose a stable browser automation path for the Play workspace that allows an end-to-end test to create or select a session, submit a prompt, and observe when the resulting job reaches a terminal state.

The automation path SHALL rely on stable labels, roles, or explicit test selectors for the controls required by that smoke flow rather than incidental DOM structure.

#### Scenario: Submit prompt
- **WHEN** a user submits a prompt for an active session
- **THEN** the dashboard SHALL create a prompt job through the agent-orchestrator and append the user prompt to the transcript

#### Scenario: Browser test can create a new session
- **WHEN** a browser automation client opens the Play workspace
- **THEN** it SHALL be able to locate and activate the new-session control through a stable selector or label

#### Scenario: Browser test can submit a prompt
- **WHEN** a browser automation client opens the Play workspace and creates or selects a session
- **THEN** it SHALL be able to locate the prompt input and submit control through stable automation-facing selectors or accessible labels

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

#### Scenario: Browser test can observe streaming progress
- **WHEN** a submitted prompt job begins streaming
- **THEN** the Play workspace SHALL expose a stable visible state that indicates the job is streaming

#### Scenario: Browser test can observe terminal job state
- **WHEN** a submitted prompt job completes, fails, or is cancelled
- **THEN** the Play workspace SHALL expose a stable visible state that allows browser automation to detect that the job is no longer streaming

#### Scenario: Suppress script tags in markdown
- **WHEN** model output contains a script tag
- **THEN** the dashboard SHALL suppress it and SHALL NOT execute or render it

#### Scenario: Resume event stream after reconnect
- **WHEN** a user reconnects to an in-progress or completed job
- **THEN** the dashboard SHALL replay all DB events from cursor 0, deduplicate by event ID, and extend in-progress snapshot text with live stream chunks — producing no duplicates and no gaps

#### Scenario: Streaming job tracked atomically
- **WHEN** multiple jobs exist for a session
- **THEN** the dashboard SHALL maintain a single sorted jobs array and a streaming job ID ref to avoid race conditions between history load and live stream state

### Requirement: Attach session skills from the chat composer
The dashboard SHALL let the user attach a skill to the selected Play session from the chat composer, without opening the settings panel. Typing the mention trigger `@` in the prompt input SHALL open a picker listing the skills available to that session, and choosing one SHALL attach that skill to the session.

The picker SHALL narrow its list as the user types after the `@`, using the same case-insensitive substring match the shared searchable model picker uses, so the two filter alike. It SHALL offer every skill available to the session, including skills already attached to it, because a mention loads that skill into the message being written — worth doing again on a later turn even when the session attachment is already in place. It SHALL be dismissable with `Escape`, and while it is open `Enter` SHALL choose the highlighted skill instead of submitting the message.

An `@` SHALL only start a mention at the beginning of the message or after whitespace, and a mention SHALL end at the first whitespace, so an email address or an `@` inside a word does not open the picker.

Choosing a skill SHALL complete the partial `@…` token into the full `@<skill-name>` token followed by a single space, leaving the caret after it. The mention SHALL remain in the message text and in the message the user sends, because the mention is what loads that skill into the turn.

#### Scenario: Typing the mention trigger opens the skill picker
- **WHEN** a user with an active session types `@` in the prompt input
- **THEN** the dashboard SHALL show a picker listing the skills available to that session

#### Scenario: Mention query filters the picker
- **WHEN** the user continues typing after the `@`
- **THEN** the picker SHALL list only skills whose name contains the typed text, case-insensitively

#### Scenario: Choosing a skill attaches it and completes the token
- **WHEN** the user chooses a skill from the picker
- **THEN** the dashboard SHALL attach that skill to the selected session
- **AND** SHALL replace the partial `@…` token with `@<skill-name>` followed by a space
- **AND** SHALL leave the caret directly after the completed token

#### Scenario: Enter chooses from the picker instead of sending
- **WHEN** the picker is open and the user presses `Enter`
- **THEN** the dashboard SHALL attach the highlighted skill and SHALL NOT submit the message

#### Scenario: Escape dismisses the picker
- **WHEN** the picker is open and the user presses `Escape`
- **THEN** the dashboard SHALL close the picker and leave the prompt text unchanged

#### Scenario: An @ inside a word does not open the picker
- **WHEN** the prompt text contains an `@` that is neither at the start of the message nor preceded by whitespace
- **THEN** the dashboard SHALL NOT open the picker

#### Scenario: An already-attached skill is still offered
- **WHEN** the picker opens for a session that already has a skill attached
- **THEN** that skill SHALL still appear among the picker's options, so it can be loaded into this message

#### Scenario: No picker without an active session
- **WHEN** no session is selected, or the selected session is not active
- **THEN** typing `@` SHALL NOT open the picker

### Requirement: Attached skills are shown and removable on the composer
The composer SHALL display the skills currently attached to the selected session as chips, each carrying a control that detaches that skill from the session. Detaching from a chip SHALL use the same session skill assignment that the settings panel's skill toggles use.

The chip row SHALL render only when at least one skill is attached, so a session with no skills shows an unchanged composer.

#### Scenario: Attached skill appears as a chip
- **WHEN** a session has a skill attached
- **THEN** the composer SHALL render a chip naming that skill

#### Scenario: Chip detaches the skill
- **WHEN** the user activates a chip's remove control
- **THEN** the dashboard SHALL detach that skill from the session

#### Scenario: No chip row without attached skills
- **WHEN** the selected session has no skills attached
- **THEN** the composer SHALL NOT render a chip row

### Requirement: Composer and settings panel share one skill assignment
The composer's skill chips and the settings panel's skill toggles SHALL read the same session skill value, so a skill attached from the composer is shown as enabled in the settings panel and a skill enabled in the settings panel is shown as a chip on the composer, with no separate composer-only state.

Attaching or detaching from the composer SHALL persist through the agent-orchestrator's session skill endpoints immediately, in the way MCP toggles already do, rather than waiting for the settings panel's Save. A subsequent Save from the settings panel SHALL therefore find nothing to change for that skill.

Attaching or detaching one skill from the composer SHALL NOT discard unsaved skill edits made in the settings panel for other skills, because only the mentioned skill's membership changes.

#### Scenario: Skill attached from chat shows as enabled in settings
- **WHEN** the user attaches a skill through the composer's mention picker
- **THEN** the settings panel SHALL show that skill's toggle as enabled

#### Scenario: Skill enabled in settings shows as a composer chip
- **WHEN** the user enables a skill in the settings panel's skill toggle list
- **THEN** the composer SHALL render a chip for that skill

#### Scenario: Attaching from chat persists immediately
- **WHEN** the user attaches a skill through the composer
- **THEN** the dashboard SHALL call the agent-orchestrator's add-skill endpoint for that session without waiting for a Save

#### Scenario: Detaching from chat persists immediately
- **WHEN** the user detaches a skill from a composer chip
- **THEN** the dashboard SHALL call the agent-orchestrator's remove-skill endpoint for that session without waiting for a Save

#### Scenario: Composer attachment reports failures
- **WHEN** the agent-orchestrator rejects an attach or detach requested from the composer
- **THEN** the dashboard SHALL surface the error and SHALL NOT show the skill as attached

### Requirement: A mentioned skill is loaded into the message it was typed in
Submitting a prompt SHALL name the skills the message mentions, so the agent-orchestrator loads their instructions into that turn. A name SHALL be sent only when the message contains it as a mention token — an `@` at the start of the message or after whitespace, ending at the first whitespace — and only when it matches a skill currently assigned to the selected session, so ordinary text containing an `@` never loads anything.

The same skill mentioned more than once in one message SHALL be named once.

The message text sent SHALL be exactly what the user typed, mention tokens included. The dashboard SHALL NOT expand skill content into the message text itself, because skill content stays server-side.

A message with no mentions SHALL submit exactly as it did before, naming no skills.

#### Scenario: Mentioned skill is named on submission
- **WHEN** the user sends a message containing `@<skill-name>` for a skill assigned to the session
- **THEN** the dashboard SHALL submit the prompt naming that skill as loaded into the message
- **AND** the submitted prompt text SHALL still contain the mention token

#### Scenario: Text that only looks like a mention loads nothing
- **WHEN** the message contains an `@` token that matches no skill assigned to the session
- **THEN** the dashboard SHALL submit the prompt naming no skills

#### Scenario: A repeated mention is named once
- **WHEN** the message mentions the same skill twice
- **THEN** the dashboard SHALL name that skill exactly once on submission

#### Scenario: A message without mentions is unchanged
- **WHEN** the user sends a message containing no mention token
- **THEN** the dashboard SHALL submit the prompt with no skills named

### Requirement: Tool invocations render as readable invocations
The Play transcript SHALL present a tool invocation as one card describing what was called, with what, and what came back — not as a serialised event payload.

A `tool_call` event and the `tool_result` event that answers it SHALL be paired by `tool_call_id` and rendered as a single item, so that calls issued in parallel and events interleaved between a call and its result still pair correctly. A call whose result has not arrived SHALL be shown as still running. A result with no call to pair to SHALL still be shown rather than dropped.

A collapsed card SHALL name the tool and SHALL summarise its arguments on one line. Arguments that are scalars SHALL be summarised by name and value; an argument that is an object or a list SHALL be summarised by its shape rather than by its contents, so the line stays readable regardless of what was passed. A call that failed SHALL be marked as failed without being expanded.

An expanded card SHALL list each argument by name beside its value, SHALL show the result, and SHALL state which server answered and which call it was. A call that carries no structured arguments — an older event, or the invalid-tool-call path — SHALL fall back to its recorded body text rather than showing nothing.

The cards SHALL reuse the transcript's existing card styling, so a tool card is visually of a piece with the reasoning and compaction blocks beside it.

#### Scenario: A call and its result are one card
- **WHEN** a job records a `tool_call` and the `tool_result` answering the same `tool_call_id`
- **THEN** the transcript SHALL render one card for the pair
- **AND** that card SHALL name the tool and summarise the call's arguments without being expanded

#### Scenario: Arguments are named, not serialised
- **WHEN** the reader expands a tool card
- **THEN** the transcript SHALL show each argument's name beside its value
- **AND** SHALL show the tool's result and which server answered the call

#### Scenario: An unanswered call reads as running
- **WHEN** a `tool_call` has been recorded and no matching `tool_result` has arrived
- **THEN** the transcript SHALL present the invocation as still running

#### Scenario: A failed call is visible without expanding
- **WHEN** a `tool_result` arrives with `is_error` set
- **THEN** the transcript SHALL mark the collapsed card as an error

#### Scenario: A result with no call is still shown
- **WHEN** a `tool_result` is present whose `tool_call` is not in the loaded events
- **THEN** the transcript SHALL still render that result

### Requirement: System tools get purpose-built cards through a renderer registry
The dashboard SHALL map a tool name to a presentation through a registry, and SHALL render every tool absent from that registry with the generic readable card. Adding a bespoke presentation SHALL therefore be an entry in that table plus one renderer, and SHALL NOT require changing how any other tool renders.

`spawn_subagent` and `prompt_player_agent` SHALL name the child agent they started and SHALL offer a control that opens the existing subagent output view on that child job. `prompt_player_agent` SHALL additionally name the seat it prompted. Where the child job cannot be identified — the launch failed, or its result was not the expected shape — the control SHALL be omitted rather than opening nothing.

`wait_for_subagent` SHALL show a running animation while the wait is outstanding, together with the child it is waiting on, and SHALL announce that state to assistive technology. Once the wait ends the animation SHALL be replaced by its outcome, distinguishing a collected report from an abandoned wait.

`load_skill` and `load_skill_reference` SHALL put the skill name — and the reference name where there is one — on the card header, and SHALL keep the loaded document behind the collapse with an indication of its size.

The control that opens a subagent SHALL be offered only where there is somewhere to open it, so a transcript rendered outside the Play workspace shows the card without a dead control.

#### Scenario: A spawn offers a way into the subagent it started
- **WHEN** a `spawn_subagent` call has returned a child job id
- **THEN** the card SHALL name that child
- **AND** SHALL offer a control that opens the subagent output view on that child job

#### Scenario: A player prompt names its seat
- **WHEN** a `prompt_player_agent` call has been recorded for a seat
- **THEN** the card SHALL name that seat alongside the child agent it started

#### Scenario: An outstanding wait animates
- **WHEN** a `wait_for_subagent` call has no result yet
- **THEN** the card SHALL show a running animation naming the child being waited on
- **AND** SHALL expose that state as a live status to assistive technology

#### Scenario: A finished wait shows its outcome
- **WHEN** the `tool_result` for a `wait_for_subagent` call arrives
- **THEN** the card SHALL replace the animation with the outcome of the wait

#### Scenario: A skill load is named by its skill
- **WHEN** a `load_skill` call has been recorded
- **THEN** the card header SHALL show the skill's name and the size of the loaded document
- **AND** the document itself SHALL NOT be rendered until the card is expanded

#### Scenario: An unregistered tool still reads well
- **WHEN** a tool with no registry entry is called
- **THEN** the transcript SHALL render it with the generic readable card

### Requirement: Displayed tool arguments and results are redacted
The dashboard SHALL redact credential-shaped text from every tool argument value, every tool result string, and every provenance value it displays, using the same shapes the eval service redacts from stored error detail: named credential fields and headers with a `:` or `=` separator, bare bearer tokens, and bare provider key literals. Redaction SHALL happen before any length cap is applied, and a value cut short SHALL NOT expose the leading part of a credential the cap fell inside.

Because a card displays an argument's name and its value as two separate pieces of text, a pattern that recognises a credential by the field name in front of it cannot fire on the value. An argument whose own *name* names a credential SHALL therefore have its value replaced entirely, in the collapsed summary, in the expanded row, and in the full text behind "show all" — there SHALL be no path from such an argument to its value.

The MCP server a call was routed to SHALL be redacted before being displayed, because a registered server URL can carry a token in its path or query.

Every argument and result SHALL be rendered as text. The dashboard SHALL NOT interpret model-supplied or server-supplied tool content as markup, and SHALL NOT interpolate it into anything executable.

A child job id read out of a tool argument SHALL be accepted only when it is shaped like a job identifier, because it is written by the model and the view it opens interpolates it into a request path. An identifier that is not SHALL be treated as no reference at all, so no control is offered.

#### Scenario: A credential in an error result is not shown
- **WHEN** a tool result carries a gateway error whose text contains an API key
- **THEN** the transcript SHALL show the error with the credential replaced
- **AND** the credential SHALL NOT appear anywhere in the rendered document

#### Scenario: A credential past the displayed window is still redacted
- **WHEN** a displayed value is capped and a credential sits beyond the cap but within the redaction window
- **THEN** the credential SHALL be replaced rather than partially shown

#### Scenario: Prose mentioning a secret is left intact
- **WHEN** a tool result contains the word "secret" in ordinary prose with no credential after it
- **THEN** the text SHALL be shown unchanged

#### Scenario: An argument named as a credential never shows its value
- **WHEN** a tool is called with an argument named `api_key`, `password`, `token` or any other credential name
- **THEN** the value SHALL be shown as redacted in the collapsed summary and in the expanded row
- **AND** no control SHALL be offered that reveals the value

#### Scenario: A token in a registered server URL is not shown
- **WHEN** a call was routed to an MCP server whose URL carries a credential
- **THEN** the card's provenance line SHALL show that URL with the credential replaced

#### Scenario: A forged child job id offers no control
- **WHEN** a `wait_for_subagent` argument names a child job id containing path or query syntax
- **THEN** the dashboard SHALL treat it as identifying no subagent
- **AND** SHALL NOT offer a control that would request it

### Requirement: Dashboard transcript rendering consumes one shared event interpretation Module
The dashboard SHALL interpret streamed and persisted orchestrator job events through one shared transcript/event Module rather than reimplementing terminal, chunk-merge, and subagent reconciliation rules across multiple helpers.

#### Scenario: Transcript helpers share one interpretation path
- **WHEN** job events update model output, reasoning, tool calls, tool results, compaction state, or subagent state
- **THEN** the dashboard SHALL apply those event types through one shared transcript/event interpretation Module

#### Scenario: Reconnect behavior matches orchestrator stream semantics
- **WHEN** the dashboard reconnects to an in-progress job
- **THEN** the dashboard transcript/event Module SHALL reuse orchestrator-compatible cursor and snapshot rules
- **AND** SHALL render the transcript without duplicate or missing events

### Requirement: Transcript re-render cost is bounded by what changed
Both dashboard transcripts SHALL bound the work of an update by what actually changed rather than by the length of the transcript, so the cost of one streamed token, one selection, or one search keystroke does not grow with the size of the session's history.

In the Play transcript, an arriving job event SHALL re-render only the job thread that event belongs to and, within it, only the blocks whose content changed. A settled response SHALL NOT be re-rendered — and in particular its markdown SHALL NOT be re-parsed — because a later job received a token. An update that changes no job SHALL re-render no block at all.

In the History transcript, moving the selection SHALL re-render only the row losing the selection and the row gaining it. A refresh that changes no event SHALL re-render no row. Every value handed to a row SHALL be referentially stable across renders that did not change it, including the empty verdict list, the default expand and reveal pulses, the restore callback and the board-action bundle; a row SHALL receive the current selection only when that selection is one of the row's own verdicts.

The cost of one transcript block SHALL likewise be bounded by what that block displays rather than by the size of the payload behind it. A collapsed tool card SHALL NOT serialise the call's arguments or the result's body: every value it shows SHALL be produced by a formatter that stops reading the payload once it has enough characters for the line, so a call carrying a full board state or a card list costs the same to present as a two-argument call. The full text of an argument or a result SHALL be produced only inside an expanded card, and only when the reader asks for the whole of it; an expanded card SHALL cap what it renders and offer the remainder on request, so opening one cannot stretch the transcript to the height of its payload.

Achieving this containment SHALL NOT change what a transcript renders: any given transcript SHALL render identically with the containment applied and without it, and the transcript's scroll container SHALL keep mounting the full transcript so that the follow lock continues to work against real scroll geometry.

#### Scenario: A streamed token leaves settled responses alone
- **WHEN** a job event arrives for the streaming job in a session that already holds several completed jobs
- **THEN** the dashboard SHALL re-render only that job's thread
- **AND** SHALL NOT re-render or re-parse the markdown of any earlier completed response

#### Scenario: An update that changed nothing renders nothing
- **WHEN** the Play transcript re-renders with a job list whose jobs are all unchanged
- **THEN** the dashboard SHALL NOT re-render any transcript block

#### Scenario: Moving the History selection touches two rows
- **WHEN** the selected event changes in the History transcript
- **THEN** the dashboard SHALL re-render only the previously selected row and the newly selected row

#### Scenario: A History refresh that changed nothing renders no rows
- **WHEN** the History transcript re-renders with the same events and the same selection
- **THEN** the dashboard SHALL NOT re-render any event row

#### Scenario: Rendered output is unchanged
- **WHEN** a transcript is rendered for a session with and without this containment
- **THEN** the rendered output SHALL be identical

#### Scenario: A huge tool payload does not reach a collapsed card
- **WHEN** a tool call carries a large argument or its result carries a large body
- **THEN** the collapsed card SHALL remain the size of a header line
- **AND** SHALL NOT contain the payload

#### Scenario: A streamed token rebuilds no settled tool card
- **WHEN** a job event arrives for the streaming job in a session whose earlier jobs hold completed tool exchanges
- **THEN** the dashboard SHALL NOT rebuild the presentation of any of those earlier tool exchanges

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
The dashboard SHALL provide a Swagger section that displays a merged OpenAPI document for
**every** first-party service it proxies — agent-orchestrator, game-service, history-service and
eval-service — and routes playground calls through dashboard proxy routes.

The set of services the merged document covers SHALL be derived from the same single declaration
that determines which services the proxy route accepts, so a service cannot be reachable through
the proxy while being absent from the index. The merge SHALL NOT iterate a separate literal list
of service names.

Each service's document SHALL be fetched from that service's own configured base URL and its own
configured OpenAPI source path. Resolution SHALL be exhaustive over the declared service set, so
a declared service without a configured base URL or OpenAPI path is a build-time failure rather
than a request that silently retrieves another service's document.

Merged endpoints SHALL be namespaced per service — path prefix, operation ids, tags, and
component names — so two services publishing the same path or schema name cannot collide, and
the path prefix SHALL be the same service segment the proxy route accepts.

#### Scenario: Every proxied service appears in the merged document
- **WHEN** a user opens the Swagger section
- **THEN** the dashboard SHALL fetch or serve a merged OpenAPI document containing the endpoints
  of every service the dashboard proxies, each under that service's own path prefix

#### Scenario: A newly declared service is covered without editing the merge
- **WHEN** a service is added to the single declaration of services the dashboard fronts
- **THEN** the merged OpenAPI document SHALL include that service's endpoints once its base URL
  and OpenAPI source path are configured, without any change to the merging logic itself

#### Scenario: Each service is read from its own upstream
- **WHEN** the dashboard fetches the upstream OpenAPI documents
- **THEN** it SHALL request each service's document from that service's configured base URL and
  OpenAPI source path
- **AND** SHALL NOT resolve one service's document against another service's base URL or path

#### Scenario: Proxy playground request
- **WHEN** a user executes an API request from the Swagger playground
- **THEN** the dashboard SHALL proxy the request to the matching upstream service and return the
  upstream response to the playground

#### Scenario: Upstream spec unavailable
- **WHEN** one configured service OpenAPI document cannot be fetched
- **THEN** the dashboard SHALL still report the error clearly, naming the service that failed,
  and SHALL render the available service specs

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
The dashboard SHALL use non-secret environment configuration for service base URLs, OpenAPI
source paths, and default session settings. Every service the dashboard proxies SHALL have both a
base URL and an OpenAPI source path available from that configuration, each overridable by its own
environment variable and each defaulting to the value that works against the local stack.

#### Scenario: Load service endpoints from environment
- **WHEN** the dashboard starts
- **THEN** it SHALL read the base URL of every service it proxies from environment-backed
  configuration

#### Scenario: Per-service OpenAPI source path override
- **WHEN** a service serves its OpenAPI document somewhere other than the default path and the
  corresponding environment variable is set
- **THEN** the dashboard SHALL fetch that service's document from the overridden path and leave
  the other services' paths unchanged

#### Scenario: Missing required service configuration
- **WHEN** required dashboard service URLs are missing
- **THEN** the dashboard SHALL show a clear configuration error instead of silently sending
  requests to an invalid target

### Requirement: Dashboard code quality
The dashboard SHALL pass ESLint and TypeScript checks with no errors, using HeroUI components for all controls, ES module imports at the top of each file only, and no inline type imports.

#### Scenario: Lint and typecheck pass
- **WHEN** `pnpm lint` and `pnpm typecheck` are run against the dashboard source
- **THEN** both SHALL exit with no errors

### Requirement: Session list removal and terminated-session hiding
The dashboard SHALL provide a per-session removal control in the Play session list that permanently deletes the session through the agent-orchestrator session deletion endpoint, and SHALL hide terminated sessions from the session list by default.

Removal SHALL delete rather than terminate: the session and everything recorded under it are gone afterwards, so a removed session SHALL NOT reappear in the session list on a later load.

The removal control SHALL require an explicit confirmation before deleting. That confirmation SHALL be presented as an in-application modal dialog rather than a browser-native confirmation prompt. The dialog SHALL name the session being deleted, SHALL describe what deletion actually does — the session's settings and full transcript are removed permanently, and any running work is cancelled first — SHALL offer a cancel action alongside a danger-styled confirm action, and SHALL leave the removal trigger in the session list unchanged.

After a successful deletion the dashboard SHALL drop the session from the list and, when the deleted session was the selected one, SHALL select the next session the list shows, or no session when none remain.

#### Scenario: Remove a session from the list
- **WHEN** a user activates the per-session removal control for a session in the Play session list and confirms the action
- **THEN** the dashboard SHALL delete that session through the agent-orchestrator session deletion endpoint
- **AND** the deleted session SHALL no longer appear in the session list

#### Scenario: Deleted sessions do not come back
- **WHEN** the session list is reloaded after a session was deleted
- **THEN** that session SHALL NOT be listed, because it no longer exists rather than being hidden

#### Scenario: Terminated sessions hidden by default
- **WHEN** the Play session list renders sessions whose status is terminated
- **THEN** the dashboard SHALL exclude those terminated sessions from the list by default

#### Scenario: Removal requires confirmation
- **WHEN** a user activates the removal control but does not confirm the destructive action
- **THEN** the dashboard SHALL NOT delete the session

#### Scenario: Confirmation dialog names the session at risk
- **WHEN** a user activates the removal control for a session
- **THEN** the dashboard SHALL open a modal confirmation dialog that names that session, states that its settings and transcript are deleted permanently, and warns the action cannot be undone
- **AND** SHALL NOT have deleted the session at the point the dialog appears

#### Scenario: Dismissing the confirmation cancels the removal
- **WHEN** a user cancels or dismisses the removal confirmation dialog
- **THEN** the dialog SHALL close, the session SHALL remain in the session list, and no deletion request SHALL be sent

#### Scenario: Selection moves on after deleting the selected session
- **WHEN** the deleted session was the selected one
- **THEN** the dashboard SHALL select the next session the list shows, or no session at all when the list is empty

### Requirement: New sessions preserve last-used settings
The dashboard SHALL create new Play sessions seeded with the user's last-used settings — provider, model, reasoning enabled state and effort, selected skills, recent message and tool-exchange limits, and advanced/MCP option selections — instead of resetting every field to configuration defaults.

Those settings SHALL survive a page reload: the configuration the user last committed SHALL be remembered client-side, per browser, and used to seed the draft on a later visit. Only committed configurations SHALL be remembered — creating a session, saving a session's configuration, or changing the provider/model that is committed immediately — so that a partially edited field is never carried forward. The session name SHALL never be carried forward; each new session gets a freshly generated one.

The remembered configuration SHALL NOT override the settings of a session the user opens: loading a session SHALL replace the draft with that session's own configuration.

The dashboard SHALL fall back to configuration defaults only when there is no prior draft, remembered configuration, or session to copy settings from, and SHALL treat an unreadable or unwritable client-side store as having no remembered configuration rather than as an error.

#### Scenario: New session inherits previous settings
- **WHEN** a user has configured a session's provider, model, reasoning, skills, and replay limits and then creates a new session
- **THEN** the dashboard SHALL seed the new session with those last-used settings rather than the configuration defaults

#### Scenario: Settings survive a reload
- **WHEN** a user reloads the dashboard with no session selected after having committed a configuration earlier
- **THEN** the draft SHALL be seeded from that remembered configuration rather than from the configuration defaults, with a freshly generated session name

#### Scenario: An opened session keeps its own settings
- **WHEN** a user opens an existing session while a different configuration is remembered
- **THEN** the draft SHALL show that session's own provider, model, reasoning, and skills

#### Scenario: First session falls back to defaults
- **WHEN** a user creates a new session and there is no prior draft, remembered configuration, or session to copy settings from
- **THEN** the dashboard SHALL seed the new session from the configuration defaults

### Requirement: Transcript scroll lock
The dashboard transcript SHALL follow new content only while the scroll lock is engaged, and SHALL start engaged so that the newest output is visible by default. Following SHALL scroll to the true bottom of the transcript rather than to a position short of it.

A user gesture that moves away from the newest output SHALL release the lock immediately, even while output is streaming: an upward wheel, a key that scrolls upwards, or a touch drag away from the bottom. Releasing SHALL NOT be defeated by the dashboard's own auto-follow scrolling; a release SHALL cancel any in-flight programmatic scroll and leave the viewport where the user put it, and subsequent content SHALL NOT move it.

While the lock is released the dashboard SHALL present a control that re-engages the lock and scrolls to the newest content. Scrolling back to the bottom SHALL also re-engage it.

The dashboard SHALL keep the lock honest as the transcript resizes for reasons the arriving content does not describe: while engaged, content that grows after the fact SHALL still be followed; while released, content that shrinks until it fits within one viewport SHALL re-engage the lock, so the re-engage control is never offered when there is nothing to scroll.

#### Scenario: Follow new content by default
- **WHEN** new transcript content arrives and the user has not scrolled away from the bottom
- **THEN** the dashboard SHALL scroll the transcript to the newest content, and SHALL NOT offer the re-engage control

#### Scenario: Scrolling up during streaming releases the follow
- **WHEN** the user scrolls the transcript upwards with the wheel, keyboard, or a touch drag while the agent is still writing
- **THEN** the dashboard SHALL stop following, SHALL leave the viewport where the user scrolled to as further content arrives, and SHALL display the re-engage control

#### Scenario: The re-engage control resumes following
- **WHEN** the user activates the re-engage control
- **THEN** the dashboard SHALL scroll the transcript to the newest content and follow new content again

#### Scenario: Returning to the bottom resumes following
- **WHEN** the user scrolls the transcript back to the bottom
- **THEN** the dashboard SHALL follow new content again and SHALL withdraw the re-engage control

#### Scenario: Nothing to scroll withdraws the control
- **WHEN** the transcript shrinks until it fits within one viewport while the lock is released
- **THEN** the dashboard SHALL re-engage the lock rather than leaving the re-engage control on screen

### Requirement: Resilient provider and model loading
The dashboard initial load SHALL tolerate a slow or failed providers fetch and unusable providers without blocking or breaking the rest of the dashboard. A failure in any single initial-load call SHALL degrade gracefully rather than failing the whole dashboard.

The provider catalog SHALL be loaded off the dashboard's blocking initial-load path. The workspace SHALL render as soon as the dashboard configuration, skills, and sessions have resolved, and SHALL NOT wait for the provider catalog before its first paint. The dashboard configuration SHALL remain the only initial-load call whose failure is fatal.

A provider SHALL be treated as usable only when it both reports itself available and offers at least one model, because a provider whose credentials are missing answers the model listing successfully with an empty list. The non-blocking notice SHALL name every provider that is not usable by that measure, and SHALL make clear that the remaining providers still work.

A provider that offers no models SHALL be labelled as offering none in the provider selector and SHALL NOT be selectable, so that selecting it cannot leave the user on a disabled model selector holding a model from a different provider. A session already configured for such a provider SHALL still display that provider and SHALL remain able to move to a usable one.

When the provider catalog arrives, the dashboard SHALL point the selectors at a provider the user can actually use, clamping the model to one that provider offers. This SHALL NOT overwrite a provider/model selection that a loaded session has committed. An empty catalog SHALL be treated as no information about the drafted provider, and SHALL NOT reset a carried provider or model.

#### Scenario: Workspace renders before the provider catalog resolves
- **WHEN** the dashboard loads and the providers fetch is still in flight
- **THEN** the dashboard SHALL render the workspace and report a ready status without waiting for the providers fetch to complete

#### Scenario: Late-arriving catalog is applied
- **WHEN** the providers fetch resolves after the workspace has already rendered
- **THEN** the dashboard SHALL apply the catalog, pointing the provider and model selectors at a usable provider and updating the notice

#### Scenario: Late-arriving catalog does not clobber a session's selection
- **WHEN** the providers fetch resolves after a loaded session has committed its own model
- **THEN** the dashboard SHALL leave that selection unchanged

#### Scenario: One failed load call degrades gracefully
- **WHEN** the providers fetch (or any single initial-load call) fails or is slow during dashboard load
- **THEN** the dashboard SHALL still load the remaining data and SHALL NOT present a single fatal error that blocks the workspace

#### Scenario: Providers without models are named and not selectable
- **WHEN** one or more providers report themselves available but offer no models
- **THEN** the dashboard SHALL name them in a non-blocking notice, SHALL label them as offering no models in the provider selector, and SHALL NOT allow them to be selected

#### Scenario: Model selection keeps working on usable providers
- **WHEN** some providers offer no models but at least one provider does
- **THEN** the dashboard SHALL point the selectors at a usable provider and SHALL allow the user to change the model on it

#### Scenario: A degraded catalog does not reset a carried selection
- **WHEN** a new session is created while the provider catalog is empty because it failed to load
- **THEN** the dashboard SHALL carry the last-used provider and model forward rather than resetting them to the configuration defaults

### Requirement: Persona editor
The dashboard SHALL provide a dedicated page for authoring agent personas, reachable from the application shell's navigation, listing the personas that exist and letting a user create, edit, and delete one. The editor SHALL expose every field a persona carries: name, display name, description, system prompt, provider, model, reasoning, skill selection, and tool allowlist.

The editor SHALL be built from the shared field components the existing configuration panels use, so a new surface renders the same controls rather than hand-rolled equivalents, and SHALL NOT change the appearance of any existing panel.

The editor SHALL show the persona prompt's length against its limit while the user types, and SHALL prevent a save that would be rejected for exceeding it, so the bound is visible before the request rather than only in an error.

An empty persona list SHALL be stated as such rather than rendering an empty container, and a failed load or save SHALL surface the orchestrator's message rather than failing silently.

#### Scenario: Personas are listed
- **WHEN** a user opens the personas page and personas exist
- **THEN** the dashboard SHALL list them by name with their descriptions

#### Scenario: Empty state is explicit
- **WHEN** a user opens the personas page and no personas exist
- **THEN** the dashboard SHALL state that no personas are defined

#### Scenario: A persona is created
- **WHEN** a user fills in a name and a system prompt and saves
- **THEN** the dashboard SHALL submit the persona to the agent-orchestrator and show it in the list

#### Scenario: A persona is edited
- **WHEN** a user selects an existing persona
- **THEN** the form SHALL be populated from the stored persona
- **AND** saving SHALL submit the edited values under the same name

#### Scenario: A persona is deleted
- **WHEN** a user deletes a persona
- **THEN** the dashboard SHALL submit the deletion and remove it from the list

#### Scenario: Prompt length is bounded in the UI
- **WHEN** a user types a system prompt longer than the permitted length
- **THEN** the dashboard SHALL show that the limit is exceeded and SHALL NOT allow the save

#### Scenario: A rejected save is reported
- **WHEN** the agent-orchestrator rejects a persona — for instance because it names an unknown skill
- **THEN** the dashboard SHALL display the returned message rather than discarding it

### Requirement: Session default subagent persona picker
The session settings panel SHALL let a user choose which persona the session's subagents are started from by default, with an explicit option meaning "no persona". The picker SHALL be populated from the personas the agent-orchestrator reports, SHALL show the currently persisted choice when a session is selected, and SHALL submit the choice as part of the session configuration. A deployment with no personas SHALL NOT render the picker, so a feature nobody has configured does not add an empty control to the panel.

Adding the picker SHALL NOT restyle or re-theme any other control in the panel.

#### Scenario: Picker offers the defined personas and no-persona
- **WHEN** a user opens the settings panel for a session and personas are defined
- **THEN** the panel SHALL offer each persona plus an explicit no-persona option

#### Scenario: Persisted choice is shown
- **WHEN** a user selects a session that already records a default subagent persona
- **THEN** the panel SHALL show that persona as the current choice

#### Scenario: Choice is saved with the session
- **WHEN** a user picks a persona and saves the session configuration
- **THEN** the dashboard SHALL submit the chosen persona as the session's default subagent persona

#### Scenario: Choice is clearable
- **WHEN** a user picks the no-persona option and saves
- **THEN** the dashboard SHALL submit a cleared default, and the session's subagents SHALL again inherit the session's own configuration

#### Scenario: No personas means no picker
- **WHEN** a user opens the settings panel and no personas are defined
- **THEN** the panel SHALL NOT render the persona picker

### Requirement: A question from the agent is answered by clicking
When a job's event timeline carries a question from the agent, the transcript SHALL render it as its own surface showing the question and one clickable control per offered choice, rather than as a generic tool-call block. Activating a control SHALL submit that choice as the answer without the user typing anything.

When the question permits a free-text answer, the surface SHALL additionally offer a text field and a way to submit it. When it does not, no text field SHALL be offered, so the surface never invites an answer the orchestrator will refuse.

While an answer is being submitted, every control on the surface SHALL be disabled, so one user cannot submit two answers by clicking twice.

The surface SHALL be a new component and SHALL follow the transcript's existing visual language. No existing transcript, composer, or tool-call rendering SHALL be restyled by this change.

#### Scenario: Clicking a choice answers the question
- **WHEN** the transcript shows a question awaiting an answer with two offered choices
- **THEN** it SHALL render one control per choice
- **AND WHEN** the user activates one
- **THEN** the dashboard SHALL submit that choice's value as the answer for that question

#### Scenario: Free text is offered only when permitted
- **WHEN** a question that does not permit free text is awaiting an answer
- **THEN** the surface SHALL NOT offer a text field

#### Scenario: Controls are disabled while submitting
- **WHEN** the user has activated a choice and the submission has not yet resolved
- **THEN** every control on the surface SHALL be disabled

### Requirement: A question's state survives a reload
The dashboard SHALL derive each question's state from the job's persisted event timeline, which it already replays on load and on reconnect, and SHALL NOT hold pending-question state anywhere else. Reloading the page or losing and re-establishing the event stream SHALL therefore restore what the user was looking at.

A question that is still awaiting an answer SHALL come back with its controls live. A question that has been answered SHALL come back showing the answer that was recorded, with no controls, because answering again is impossible. A question that was closed without an answer SHALL come back saying so, distinguishing a question nobody answered in time from one ended by cancellation.

The events that resolve a question SHALL resolve the question's own surface rather than appearing as separate entries in the transcript, so a question and its answer read as one exchange.

#### Scenario: An answered question comes back answered
- **WHEN** a job's replayed timeline contains a question followed by its answer
- **THEN** the transcript SHALL show the recorded answer and SHALL NOT render any answering controls

#### Scenario: A closed question comes back closed
- **WHEN** a job's replayed timeline contains a question followed by its closure
- **THEN** the transcript SHALL say the question is no longer awaiting an answer, naming whether it timed out or was cancelled, and SHALL NOT render any answering controls

#### Scenario: An answer is not a separate transcript entry
- **WHEN** a job's replayed timeline contains a question and its answer
- **THEN** the answer SHALL be shown on the question's own surface and SHALL NOT appear as an additional transcript entry

### Requirement: A question that can no longer be answered offers no controls
When the job that asked a question has reached a terminal status while the question is still awaiting an answer, the surface SHALL disable its controls and explain that the question can no longer be answered. This is the case where the run that was waiting is gone, and offering a control that the orchestrator will refuse would be misleading.

When a submission is refused because the question is no longer awaiting an answer, the surface SHALL show the reason the orchestrator gave and SHALL leave its controls disabled rather than inviting a retry.

#### Scenario: A finished job's pending question is inert
- **WHEN** a question is still awaiting an answer but its job has reached a terminal status
- **THEN** the surface SHALL disable its controls and SHALL explain that the question can no longer be answered

#### Scenario: A refused answer is explained, not retried
- **WHEN** submitting an answer is refused because the question is no longer awaiting one
- **THEN** the surface SHALL show the reason given and SHALL leave its controls disabled

### Requirement: Model-authored question text is rendered as text
The question text and each choice's label, value, and description are authored by the model. The dashboard SHALL render them as plain text only. It SHALL NOT render them as markup or markdown, and SHALL NOT interpolate them into an attribute, a style, or anything else that is executed or resolved as a reference.

#### Scenario: Markup in a choice label stays literal
- **WHEN** a choice label contains characters that would form an HTML element
- **THEN** the transcript SHALL display those characters as text
- **AND** no element described by that text SHALL exist in the rendered output

