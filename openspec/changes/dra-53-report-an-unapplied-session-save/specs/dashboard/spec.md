## ADDED Requirements

### Requirement: A session save reports settings the server did not apply
Saving a session's configuration SHALL compare the settings the request asked the
agent-orchestrator to store against the settings the orchestrator reports
afterwards, and SHALL report the save as incomplete — naming each setting that did
not take effect — rather than reporting success, when any of them differ.

A setting absent from the orchestrator's response SHALL be treated as not applied,
not as cleared. An orchestrator that predates a setting answers `200 OK` and omits
the field entirely, which is indistinguishable from clearing it; treating the two
alike is what allows a discarded write to be reported as a successful one.

The comparison SHALL cover the session persona and the subagent allowlist, and
SHALL compare the allowlist without regard to ordering. It SHALL NOT depend on any
declared version of the orchestrator, because it tests whether the setting took
effect rather than which server answered.

The message SHALL name the settings that did not stick and SHALL state that an
orchestrator older than the dashboard is the likeliest cause, so an operator is
pointed at the deployment rather than left to guess.

The draft SHALL still be re-seeded from what the orchestrator reports. The panel
showing a setting the server does not hold would misreport the session in the
opposite direction; the panel SHALL show what is stored and SHALL say separately
that it is not what was asked for.

#### Scenario: A discarded setting is reported instead of success
- **WHEN** a user allows a subagent persona, picks a session persona, saves, and
  the orchestrator answers successfully with a session carrying neither field
- **THEN** the dashboard SHALL report the save as incomplete
- **AND** SHALL name both the session persona and the allowed subagents as not
  applied
- **AND** SHALL NOT report the configuration as saved

#### Scenario: A save the server applied reports success
- **WHEN** a user saves and the orchestrator reports back the session persona and
  the allowlist the request asked for
- **THEN** the dashboard SHALL report the configuration as saved

#### Scenario: Allowlist ordering is not a mismatch
- **WHEN** the orchestrator reports the requested allowlist in a different order
- **THEN** the dashboard SHALL report the configuration as saved

#### Scenario: The panel keeps showing what the server stored
- **WHEN** a save is reported as incomplete
- **THEN** the settings panel SHALL show the settings the orchestrator reports,
  not the ones the save asked for
