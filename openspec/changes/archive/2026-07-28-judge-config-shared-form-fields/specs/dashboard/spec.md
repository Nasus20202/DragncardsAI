## MODIFIED Requirements

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
