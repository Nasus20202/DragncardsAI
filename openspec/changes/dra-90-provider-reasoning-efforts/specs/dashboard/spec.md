## MODIFIED Requirements

### Requirement: Session configuration controls

The dashboard SHALL expose HeroUI controls for model/provider selection, MCP assignments, skill assignments, reasoning toggle, and other session defaults in an inline settings panel.

The same settings panel SHALL expose structured controls for session memory replay behavior, including whether replay remains unbounded or is limited by recent conversational message count and recent tool-exchange count.

Model selection SHALL use one shared searchable picker component, so that every place in the dashboard that chooses a model from the provider catalog filters that catalog the same way. The picker SHALL retain what the user has typed across re-renders of the panel that owns it, so an unrelated state change elsewhere in that panel does not discard an in-progress search.

The provider catalog response SHALL retain its existing model identifier list and SHALL expose optional per-model reasoning metadata. For the selected model, the reasoning-effort control SHALL offer the exact non-empty advertised `supported_efforts` values. If the selected model has no reasoning metadata or no advertised effort list, the control SHALL offer legacy `low`, `medium`, and `high` values. If the selected model advertises an explicit empty effort list, the control SHALL offer no effort values, disable reasoning for that model, and omit `reasoning_effort` when assembling the request.

The labelled field wrappers used by this panel — the field label, text input, textarea, select, searchable select, toggle row, and skills toggle list — SHALL live in one shared component module rather than inside a single feature's panel, so any other panel that configures a provider, model, reasoning, prompt, or skill set renders the same controls instead of hand-rolling equivalents. A panel in one feature SHALL NOT import these controls from another feature's directory.

#### Scenario: Configure model and provider
- **WHEN** a user edits the model/provider configuration for a session
- **THEN** the dashboard SHALL provide a filterable ComboBox for model selection and a Select for provider, and SHALL submit changes to the agent-orchestrator

#### Scenario: Model auto-corrects on provider change
- **WHEN** a user changes the provider and the current model is not valid for the new provider
- **THEN** the dashboard SHALL automatically select the first valid model for the new provider

#### Scenario: Advertised efforts appear in the Play controls
- **WHEN** the selected model advertises `supported_efforts` equal to `['minimal', 'high']`
- **THEN** the Play reasoning-effort control SHALL offer exactly `minimal` and `high`

#### Scenario: Missing metadata keeps legacy Play controls
- **WHEN** the selected model has no reasoning metadata or no `supported_efforts` field
- **THEN** the Play reasoning-effort control SHALL offer `low`, `medium`, and `high`

#### Scenario: Explicit empty metadata disables Play effort selection
- **WHEN** the selected model advertises `supported_efforts` equal to `[]`
- **THEN** the Play reasoning-effort control SHALL offer no effort values and SHALL omit `reasoning_effort` from the assembled gateway options

#### Scenario: Evaluate controls use the selected model's efforts
- **WHEN** a user selects a model with non-empty advertised reasoning efforts in the Evaluate panel
- **THEN** the Evaluate reasoning-effort control SHALL offer exactly those advertised values

#### Scenario: Persona controls use the selected model's efforts
- **WHEN** a user selects a model with non-empty advertised reasoning efforts in the persona editor
- **THEN** the persona reasoning-effort control SHALL offer exactly those advertised values

#### Scenario: Configure replay limits
- **WHEN** a user edits the session replay controls in the settings panel
- **THEN** the dashboard SHALL validate numeric replay limits before saving
- **AND** SHALL submit the resulting replay settings as part of the session configuration shown for that session

#### Scenario: Clicking the toggle control flips the switch
- **WHEN** a user clicks directly on a session-config toggle's switch control (its track or thumb), not the text label
- **THEN** the dashboard SHALL flip that toggle, because the switch control is rendered inside the clickable switch content rather than as a sibling of it

#### Scenario: Configure MCPs and skills
- **WHEN** a user edits MCP or skill assignments for a session
- **THEN** the dashboard SHALL submit the selected assignments to the agent-orchestrator

#### Scenario: Field wrappers are shared, not per-feature
- **WHEN** another dashboard panel needs a labelled provider select, model picker, reasoning toggle, numeric or text field, prompt textarea, or skills toggle list
- **THEN** it SHALL render the shared field components used by this settings panel, and this settings panel's own rendered output SHALL be unaffected by that reuse
