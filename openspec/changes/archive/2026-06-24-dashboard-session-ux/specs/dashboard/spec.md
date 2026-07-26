## ADDED Requirements

### Requirement: Session list removal and terminated-session hiding
The dashboard SHALL provide a per-session removal control in the Play session list that terminates the session through the existing agent-orchestrator termination flow, and SHALL hide terminated sessions from the session list by default.

The removal control SHALL require an explicit confirmation before terminating, and SHALL NOT introduce a new backend endpoint.

#### Scenario: Remove a session from the list
- **WHEN** a user activates the per-session removal control for a session in the Play session list and confirms the action
- **THEN** the dashboard SHALL terminate that session through the existing agent-orchestrator termination flow
- **AND** the terminated session SHALL no longer appear in the session list

#### Scenario: Terminated sessions hidden by default
- **WHEN** the Play session list renders sessions whose status is terminated
- **THEN** the dashboard SHALL exclude those terminated sessions from the list by default

#### Scenario: Removal requires confirmation
- **WHEN** a user activates the removal control but does not confirm the destructive action
- **THEN** the dashboard SHALL NOT terminate the session

### Requirement: New sessions preserve last-used settings
The dashboard SHALL create new Play sessions seeded with the user's last-used settings — provider, model, reasoning enabled state and effort, selected skills, recent message and tool-exchange limits, and advanced/MCP option selections — instead of resetting every field to configuration defaults.

The dashboard SHALL fall back to configuration defaults only when there is no prior draft or session to copy settings from.

#### Scenario: New session inherits previous settings
- **WHEN** a user has configured a session's provider, model, reasoning, skills, and replay limits and then creates a new session
- **THEN** the dashboard SHALL seed the new session with those last-used settings rather than the configuration defaults

#### Scenario: First session falls back to defaults
- **WHEN** a user creates a new session and there is no prior draft or session to copy settings from
- **THEN** the dashboard SHALL seed the new session from the configuration defaults

### Requirement: Transcript scroll lock
The dashboard transcript SHALL auto-scroll to the newest content only while the view is locked to the bottom, where locked means the scroll position is at or near the bottom of the scrollable transcript container.

When the user scrolls up away from the bottom, the dashboard SHALL unlock and stop auto-scrolling, and SHALL present a control to jump back to the latest content that re-locks the view and scrolls to the bottom when activated.

#### Scenario: Auto-scroll while locked
- **WHEN** new transcript content arrives and the user is at or near the bottom of the transcript
- **THEN** the dashboard SHALL scroll the transcript to the newest content

#### Scenario: Scrolling up unlocks auto-scroll
- **WHEN** the user scrolls up away from the bottom of the transcript and new content arrives
- **THEN** the dashboard SHALL NOT auto-scroll the transcript to the newest content
- **AND** SHALL display a control to jump to the latest content

#### Scenario: Jump to latest re-locks the view
- **WHEN** the user activates the jump-to-latest control
- **THEN** the dashboard SHALL scroll the transcript to the newest content and re-lock auto-scrolling

### Requirement: Resilient provider and model loading
The dashboard initial load SHALL tolerate a slow or failed providers fetch and unavailable providers without blocking or breaking the rest of the dashboard. A failure in any single initial-load call SHALL degrade gracefully rather than failing the whole dashboard.

The dashboard SHALL surface unavailable or failed providers as a non-blocking notice, and SHALL default the provider and model selectors to a working provider so that model selection remains available on providers that work.

#### Scenario: One failed load call degrades gracefully
- **WHEN** the providers fetch (or any single initial-load call) fails or is slow during dashboard load
- **THEN** the dashboard SHALL still load the remaining data and SHALL NOT present a single fatal error that blocks the workspace

#### Scenario: Unavailable providers surfaced non-blockingly
- **WHEN** one or more providers report that they are unavailable
- **THEN** the dashboard SHALL surface those providers as a non-blocking notice rather than a fatal error

#### Scenario: Selectors default to a working provider
- **WHEN** some providers are unavailable but at least one provider works
- **THEN** the dashboard SHALL default the provider and model selectors to a working provider and SHALL allow the user to select a model on it
