## ADDED Requirements

### Requirement: The subagent list is bounded, scrollable, and filterable by status
The Play workspace SHALL present a session's subagents in a list floating over the transcript, and that list SHALL keep its entries inside a container with a maximum height and its own vertical overflow. The list SHALL therefore never extend past the height of that container regardless of how many subagents a session has spawned, and the entries beyond the visible height SHALL be reachable by scrolling within the list rather than by scrolling the page. Scrolling past the end of the list SHALL NOT continue into the transcript underneath it.

Collapsed, the list SHALL show the subagents that are still running and the ones that failed, and SHALL state how many failed. Expanded, the list SHALL offer a status filter over All, running, completed and failed, SHALL label each status with how many subagents currently hold it, and SHALL show all subagents until the reader chooses otherwise. Choosing a status SHALL show only the subagents holding it. Choosing a status that nothing holds SHALL say so rather than presenting an empty list.

The filter SHALL be the reader's current view state and SHALL NOT be persisted anywhere.

Each entry SHALL show its subagent's name, SHALL make the whole name available when the row is too narrow for it, and SHALL fall back to a short form of the child job id for a subagent that has no name. Selecting an entry SHALL open the subagent output view on that child job.

The list SHALL keep the existing appearance of the workspace: the header, the entry rows, the status marks and the failure tooltip are unchanged, and the filter control SHALL be sized to the list it sits in.

#### Scenario: The entries are held in a bounded box that scrolls itself
- **WHEN** the subagent list is shown for a session with more subagents than fit
- **THEN** the entries SHALL be inside a container with a maximum height and its own vertical scrolling
- **AND** the page SHALL NOT grow to fit the list

#### Scenario: Every entry is reachable
- **WHEN** a session has far more subagents than the container's height allows
- **THEN** every entry SHALL be present inside the scrolling container

#### Scenario: A collapsed list shows what needs attention
- **WHEN** the list is collapsed for a session with running, completed and failed subagents
- **THEN** the running and failed subagents SHALL be shown and the completed ones SHALL NOT
- **AND** the number that failed SHALL be stated

#### Scenario: The filter appears with the expanded list
- **WHEN** the list is collapsed
- **THEN** no status filter SHALL be offered
- **WHEN** the reader expands the list
- **THEN** a status filter SHALL be offered

#### Scenario: Each status is labelled with its count
- **WHEN** the expanded list is shown for a session with two completed, one running and one failed subagent
- **THEN** the filter SHALL label the statuses with those counts and the total

#### Scenario: Choosing a status narrows the list
- **WHEN** the reader chooses the failed status
- **THEN** only failed subagents SHALL be shown
- **WHEN** the reader chooses the running status
- **THEN** only running subagents SHALL be shown, and completed and failed ones SHALL NOT

#### Scenario: Choosing All restores the whole list
- **WHEN** the reader has narrowed the list and then chooses All
- **THEN** every subagent SHALL be shown again

#### Scenario: An empty status says so
- **WHEN** the reader chooses a status that no subagent currently holds
- **THEN** the list SHALL state that nothing holds that status

#### Scenario: An entry with no name falls back to its job id
- **WHEN** a subagent entry carries no name
- **THEN** the entry SHALL show a short form of its child job id

#### Scenario: Selecting an entry opens that subagent
- **WHEN** the reader selects an entry
- **THEN** the subagent output view SHALL open on that entry's child job

### Requirement: Displayed subagent names and failure reasons are redacted
The dashboard SHALL redact credential-shaped text from a subagent's name and from its failure reason wherever it displays them, including in the subagent list and in the header of the subagent output view, using the same redaction the transcript's tool cards apply.

This is required because a subagent name recorded before names were generated is a slice of a model-written prompt, and a failure reason is a server-supplied message that can carry a provider error body. Both are replayed from stored events for as long as the session exists, so neither can be assumed safe to display verbatim.

#### Scenario: A credential in a stored subagent name is not shown
- **WHEN** a subagent entry's name carries credential-shaped text
- **THEN** the list SHALL show the name with the credential replaced
- **AND** the credential SHALL NOT appear anywhere in the rendered list

#### Scenario: The subagent output view redacts its title
- **WHEN** the subagent output view is opened on a subagent whose name carries credential-shaped text
- **THEN** its header SHALL show that name with the credential replaced

## MODIFIED Requirements

### Requirement: Agent session management
The dashboard SHALL allow users to create, select, inspect, update, and terminate agent sessions through agent-orchestrator APIs.

A session the dashboard creates SHALL be created without a name, because the agent-orchestrator names an unnamed session from its first prompt and a name generated in one place and stored is a name every client agrees on. The dashboard SHALL NOT derive a session name of its own — neither at creation nor from a prompt — and saving a session's configuration with an empty name field SHALL leave the session unnamed rather than inventing one. A name the user types SHALL be sent as given and SHALL NOT be overwritten.

A session with no name SHALL be presented under a placeholder in the sidebar, so an unprompted session is still selectable and removable.

#### Scenario: Create session without a name
- **WHEN** a user creates a new Play session
- **THEN** the dashboard SHALL submit it to the agent-orchestrator with no name of its own and display the created session in the sidebar
- **AND** the sidebar SHALL show a placeholder for it until it has a name

#### Scenario: A typed name is kept
- **WHEN** a user types a session name and saves the configuration
- **THEN** the dashboard SHALL send that name
- **AND** SHALL NOT replace it with a generated or derived one

#### Scenario: Saving settings does not name an unnamed session
- **WHEN** a user saves the configuration of a session that has no name, leaving the name field empty
- **THEN** the dashboard SHALL leave the session unnamed, so its first prompt can still name it

#### Scenario: Inspect selected session
- **WHEN** a user selects a session from the sidebar
- **THEN** the dashboard SHALL show the session status, model/provider configuration, assigned MCPs, assigned skills, and job history in the transcript

#### Scenario: Terminate session
- **WHEN** a user terminates an active session from the dashboard
- **THEN** the dashboard SHALL call the agent-orchestrator termination API and update the session status in the UI

### Requirement: Live chat and orchestration event rendering
The dashboard SHALL provide a ChatGPT-like prompt and transcript interface backed by agent-orchestrator prompt jobs and streaming events, rendered with markdown support.

The dashboard SHALL expose a stable browser automation path for the Play workspace that allows an end-to-end test to create or select a session, submit a prompt, and observe when the resulting job reaches a terminal state.

The automation path SHALL rely on stable labels, roles, or explicit test selectors for the controls required by that smoke flow rather than incidental DOM structure.

Submitting a prompt SHALL NOT patch the session's name. Naming an unnamed session from its first prompt belongs to the agent-orchestrator and happens inside the same request, so the dashboard SHALL refresh the session list after submitting and display whatever name came back.

#### Scenario: Submit prompt
- **WHEN** a user submits a prompt for an active session
- **THEN** the dashboard SHALL create a prompt job through the agent-orchestrator and append the user prompt to the transcript

#### Scenario: Browser test can create a new session
- **WHEN** a browser automation client opens the Play workspace
- **THEN** it SHALL be able to locate and activate the new-session control through a stable selector or label

#### Scenario: Browser test can submit a prompt
- **WHEN** a browser automation client opens the Play workspace and creates or selects a session
- **THEN** it SHALL be able to locate the prompt input and submit control through stable automation-facing selectors or accessible labels

#### Scenario: The dashboard does not name the session it prompts
- **WHEN** the user submits the first prompt in a session
- **THEN** the dashboard SHALL NOT call `PATCH /sessions/{id}` to set the session's name
- **AND** SHALL refresh the session list so the name the agent-orchestrator generated is shown

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

## REMOVED Requirements

### Requirement: Subagent cards rendered inline in the chat area
**Reason**: The component this described — a column of expandable subagent cards between the main transcript and the composer, each rendering the child job's own event stream inline — was superseded by the floating subagent list plus the subagent output view, and the code implementing it had become unreferenced. Keeping the requirement meant the spec described one subagent view while the workspace shipped another, and left two competing implementations for the next change to pick from.

**Migration**: The behaviour that survives is specified by "The subagent list is bounded, scrollable, and filterable by status" (which subagents are listed, and how the list is reached) together with DRA-22's "System tools get purpose-built cards through a renderer registry" (opening a subagent from the call that started it). A child job's transcript is read in the subagent output view rather than inline in the parent thread; the config sidebar still contains no subagent panel.
