## MODIFIED Requirements

### Requirement: Session configuration controls
The dashboard SHALL expose HeroUI controls for model/provider selection, MCP assignments, skill assignments, reasoning toggle, and other session defaults in an inline settings panel.

The same settings panel SHALL expose structured controls for session memory replay behavior, including whether replay remains unbounded or is limited by recent conversational message count and recent tool-exchange count.

Each toggle control SHALL be fully clickable: clicking the visual switch (its track or thumb) SHALL flip the toggle, not only clicking the adjacent text label.

Model selection SHALL use one shared searchable picker component, so that every place in the dashboard that chooses a model from the provider catalog filters that catalog the same way. The picker SHALL retain what the user has typed across re-renders of the panel that owns it, so an unrelated state change elsewhere in that panel does not discard an in-progress search.

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

### Requirement: Session list removal and terminated-session hiding
The dashboard SHALL provide a per-session removal control in the Play session list that terminates the session through the existing agent-orchestrator termination flow, and SHALL hide terminated sessions from the session list by default.

The removal control SHALL require an explicit confirmation before terminating, and SHALL NOT introduce a new backend endpoint.

That confirmation SHALL be presented as an in-application modal dialog rather than a browser-native confirmation prompt. The dialog SHALL name the session being removed, SHALL offer a cancel action alongside a danger-styled confirm action, and SHALL leave the removal trigger in the session list unchanged.

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

#### Scenario: Confirmation dialog names the session at risk
- **WHEN** a user activates the removal control for a session
- **THEN** the dashboard SHALL open a modal confirmation dialog that names that session and warns the action cannot be undone
- **AND** SHALL NOT have terminated the session at the point the dialog appears

#### Scenario: Dismissing the confirmation cancels the removal
- **WHEN** a user cancels or dismisses the removal confirmation dialog
- **THEN** the dialog SHALL close, the session SHALL remain in the session list, and no termination request SHALL be sent
