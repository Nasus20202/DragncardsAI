## ADDED Requirements

### Requirement: Prebuilt set catalog discovery
The Game Service SHALL expose a read-only prebuilt set catalog for the Marvel Champions plugin through MCP.

#### Scenario: List all prebuilt sets
- **WHEN** an MCP client requests the prebuilt set catalog without filters
- **THEN** the Game Service SHALL return the available prebuilt sets sourced from the plugin's `sets.json`
- **AND** each returned set SHALL include at least its `id`, `name`, and `type`

#### Scenario: Filter prebuilt sets by name
- **WHEN** an MCP client requests the prebuilt set catalog with a name filter
- **THEN** the Game Service SHALL return only sets whose names match the requested filter according to the documented search behavior

#### Scenario: Filter prebuilt sets by type
- **WHEN** an MCP client requests the prebuilt set catalog with a type filter
- **THEN** the Game Service SHALL return only sets whose type matches the requested filter

#### Scenario: Empty result set
- **WHEN** no prebuilt sets match the requested filters
- **THEN** the Game Service SHALL return an empty list instead of an error

### Requirement: Prebuilt set catalog is read-only
The Game Service SHALL treat the prebuilt set catalog as discovery data only and SHALL NOT mutate DragnCards state when serving it.

#### Scenario: Catalog request does not change game state
- **WHEN** an MCP client requests the prebuilt set catalog for any plugin
- **THEN** the Game Service SHALL not create, modify, or destroy any game session
- **AND** SHALL not send any DragnCards room events
