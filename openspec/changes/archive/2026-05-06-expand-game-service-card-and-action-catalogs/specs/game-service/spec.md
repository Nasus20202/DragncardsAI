## ADDED Requirements

### Requirement: Card catalog responses expose relevant provider metadata
The Game Service SHALL expose card search responses that include the relevant gameplay, identification, and printing metadata available from the registered provider's source data, using a documented normalized response shape.

#### Scenario: Marvel Champions card search returns expanded metadata
- **WHEN** a client sends `GET /cards/marvel-champions`
- **THEN** each returned card SHALL include the existing loading identifiers and SHALL also include the relevant optional metadata available for that card, such as card source identifiers, type/classification, uniqueness, gameplay stats, text/resource fields, author or official status, traits, and printing metadata

#### Scenario: Missing provider fields remain optional
- **WHEN** a provider cannot supply a normalized card field for a given card
- **THEN** the Game Service SHALL omit that field or return it as `null` according to the documented response model rather than failing the request

#### Scenario: Card catalog remains provider-defined
- **WHEN** a new plugin provider is registered with its own card metadata mapping
- **THEN** the Game Service SHALL expose that provider's normalized card metadata through the same card search contract without requiring router-specific behavior

### Requirement: Global action catalog exposes generic DragnCards actions
The Game Service SHALL make `GET /actions` return only the generic action surface supported by the game-service and `@external/dragncards/`, independent of any specific plugin session.

#### Scenario: Global action catalog excludes plugin-defined actions
- **WHEN** a client sends `GET /actions`
- **THEN** the response SHALL include the typed execute-action schemas and generic DragnLang operation catalog, and SHALL NOT require plugin-specific metadata to be present

#### Scenario: Global action catalog remains stable without a session
- **WHEN** no active session exists
- **THEN** `GET /actions` SHALL still return the generic action catalog successfully

### Requirement: Session action catalog exposes plugin-specific metadata
The Game Service SHALL make `GET /games/{session_id}/actions` return the global action catalog plus plugin-specific action metadata and affordances for the session's plugin.

#### Scenario: Session action catalog includes plugin-defined action metadata
- **WHEN** a client sends `GET /games/{session_id}/actions` for a Marvel Champions session
- **THEN** the response SHALL include plugin-specific metadata for the session's plugin, including the relevant named action lists, hotkeys, touch-bar entries, default actions, player-count layouts, and load-group information that the provider can derive

#### Scenario: Session action catalog preserves generic execute-action schemas
- **WHEN** a client sends `GET /games/{session_id}/actions`
- **THEN** the response SHALL still include the same generic typed action schemas and generic DragnLang operation catalog returned by `GET /actions`

#### Scenario: Unknown plugin yields only generic catalog
- **WHEN** a session's plugin has no registered provider metadata
- **THEN** the Game Service SHALL return the generic action catalog and empty plugin-specific metadata collections instead of failing the request
