## ADDED Requirements

### Requirement: Session persona picker
The session settings panel SHALL let a user choose which persona the session's **own** agent runs as, with an explicit option meaning "no persona". It SHALL be a separate control from the picker choosing the persona the session's subagents are started from, because what an agent is and what it may delegate to are different choices.

The picker SHALL be populated from the personas the agent-orchestrator reports, SHALL show the currently persisted choice when a session is selected, and SHALL submit the choice as part of the session configuration. It SHALL NOT be narrowed by the session's subagent allowlist, which governs delegation only. A deployment with no personas SHALL NOT render it.

The picker SHALL reuse the existing persona control rather than introducing a second one, and SHALL NOT restyle or re-theme any other control in the panel.

#### Scenario: The picker offers the catalogue and reports the choice
- **WHEN** a user opens the settings panel and personas are defined
- **THEN** the panel SHALL offer each persona plus an explicit no-persona option for the session's own agent
- **AND** picking one SHALL record it on the session configuration being edited

#### Scenario: The persisted session persona is shown
- **WHEN** a user selects a session that already records a persona of its own
- **THEN** the panel SHALL show that persona as the current choice

#### Scenario: The choice survives a save and a reload
- **WHEN** a user picks a session persona, saves, and reloads the dashboard
- **THEN** the panel SHALL still show that persona for that session

#### Scenario: The subagent allowlist does not narrow it
- **WHEN** a session allows no subagent persona and personas are defined
- **THEN** the session persona picker SHALL still offer the full catalogue

### Requirement: Allowed subagents control
The session settings panel SHALL let a user choose which personas the session's agent may start a subagent from, as a list of the personas that exist with a toggle for each — the same shape as the panel's skill selection, because it is the same kind of choice.

The control SHALL always state in words which of two states the session is in: that no personas are allowed, or how many of the available personas are allowed. It SHALL NOT leave that to be inferred from which toggles are on, because an all-off list reads equally well as "unrestricted", and a control that silently permits everything is worse than no control at all. The statement SHALL say that a persona outside the list is refused by the server.

The control SHALL submit the whole selection with the session configuration, in the same request as the default-subagent choice it constrains, so a save that both withdraws a persona and clears a default naming it is one accepted change.

A deployment with no personas SHALL NOT render the control. It SHALL be a new component built from the panel's existing toggle row, and SHALL NOT restyle any other control.

#### Scenario: An empty allowlist is stated as such
- **WHEN** a user opens the settings panel for a session that allows no subagent persona
- **THEN** the control SHALL state that no personas are allowed and that naming one is refused by the server

#### Scenario: A non-empty allowlist is stated as such
- **WHEN** a session allows some but not all of the available personas
- **THEN** the control SHALL state how many of how many are allowed

#### Scenario: A persona is allowed
- **WHEN** a user switches a persona on in the control
- **THEN** it SHALL be recorded as allowed on the session configuration being edited

#### Scenario: The selection survives a save and a reload
- **WHEN** a user allows a persona, saves, and reloads the dashboard
- **THEN** the control SHALL still show that persona as allowed for that session

#### Scenario: No personas means no control
- **WHEN** a user opens the settings panel and no personas are defined
- **THEN** the panel SHALL NOT render the allowed-subagents control

## MODIFIED Requirements

### Requirement: Session default subagent persona picker
The session settings panel SHALL let a user choose which persona the session's subagents are started from by default, with an explicit option meaning "no persona". The picker SHALL be populated from the personas the agent-orchestrator reports, SHALL show the currently persisted choice when a session is selected, and SHALL submit the choice as part of the session configuration. A deployment with no personas SHALL NOT render the picker, so a feature nobody has configured does not add an empty control to the panel.

The picker SHALL offer only the personas the session's subagent allowlist permits, because a default the session may not spawn is a setting whose only effect is a refusal. A session that allows no persona SHALL therefore be offered no default, and withdrawing the persona a session currently defaults to SHALL clear that default at the same time, so the panel cannot produce a configuration the orchestrator refuses.

Adding the picker SHALL NOT restyle or re-theme any other control in the panel.

#### Scenario: Picker offers the allowed personas and no-persona
- **WHEN** a user opens the settings panel for a session that allows some of the defined personas
- **THEN** the panel SHALL offer each allowed persona plus an explicit no-persona option
- **AND** SHALL NOT offer a persona the session does not allow

#### Scenario: Persisted choice is shown
- **WHEN** a user selects a session that already records a default subagent persona
- **THEN** the panel SHALL show that persona as the current choice

#### Scenario: Choice is saved with the session
- **WHEN** a user picks a persona and saves the session configuration
- **THEN** the dashboard SHALL submit the chosen persona as the session's default subagent persona

#### Scenario: Choice is clearable
- **WHEN** a user picks the no-persona option and saves
- **THEN** the dashboard SHALL submit a cleared default, and the session's subagents SHALL again inherit the session's own configuration

#### Scenario: Withdrawing the default persona clears the default
- **WHEN** a user switches off the persona that is the session's current default
- **THEN** the panel SHALL clear the default as part of the same change

#### Scenario: No personas means no picker
- **WHEN** a user opens the settings panel and no personas are defined
- **THEN** the panel SHALL NOT render the persona picker
