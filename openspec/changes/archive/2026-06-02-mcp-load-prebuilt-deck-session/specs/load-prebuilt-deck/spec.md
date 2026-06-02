## ADDED Requirements

### Requirement: Session-scoped prebuilt deck loading
The Game Service SHALL expose a session-scoped deck-loading capability for the Marvel Champions plugin.

#### Scenario: Load a prebuilt deck by deck id
- **WHEN** a client requests that a specific prebuilt deck be loaded into an existing Marvel Champions session
- **THEN** the Game Service SHALL load the requested deck into that session using the deck's id
- **AND** SHALL apply the same loading behavior as the DragnCards frontend's prebuilt deck load flow

#### Scenario: Load targets an existing session
- **WHEN** a client requests prebuilt deck loading without a valid session id
- **THEN** the Game Service SHALL reject the request with a descriptive error

#### Scenario: Unknown deck id is rejected
- **WHEN** a client requests a deck id that does not exist in the prebuilt deck catalog
- **THEN** the Game Service SHALL reject the request with a descriptive error and SHALL NOT mutate the session

#### Scenario: Successful load acknowledges the target session
- **WHEN** the Game Service successfully loads a prebuilt deck into a session
- **THEN** the response SHALL identify the target session and indicate success

### Requirement: Prebuilt deck loading is read-only with respect to the catalog
The Game Service SHALL treat deck loading as a session action and SHALL NOT mutate the underlying prebuilt deck catalog.

#### Scenario: Loading does not change catalog contents
- **WHEN** a client loads a prebuilt deck into a session
- **THEN** the deck catalog SHALL remain unchanged

#### Scenario: Loading may change session state only
- **WHEN** a client loads a prebuilt deck into a session
- **THEN** only the target session's game state SHALL be modified
