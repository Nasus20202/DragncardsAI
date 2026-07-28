## ADDED Requirements

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
