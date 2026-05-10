## ADDED Requirements

### Requirement: Dashboard game session metadata
The Game Service SHALL expose game session metadata that allows a dashboard to associate agent activity with the corresponding DragnCards room and frontend URL context.

#### Scenario: Return room metadata for active game
- **WHEN** the dashboard requests metadata for an active game session
- **THEN** the Game Service SHALL provide the session identifier, plugin identifier, room slug or room identifier, and any available frontend URL metadata needed to open the DragnCards UI

#### Scenario: Metadata for unknown game session
- **WHEN** the dashboard requests metadata for an unknown game session
- **THEN** the Game Service SHALL return a clear not-found error and SHALL NOT create a new game session implicitly

### Requirement: Game Service OpenAPI availability
The Game Service SHALL expose an OpenAPI document suitable for dashboard aggregation and playground execution.

#### Scenario: Fetch game-service OpenAPI
- **WHEN** the dashboard requests the Game Service OpenAPI document from the configured endpoint
- **THEN** the Game Service SHALL return a valid OpenAPI document for its HTTP API

### Requirement: Dashboard-safe HTTP playground behavior
The Game Service SHALL support dashboard-proxied HTTP requests using the same validation and error semantics as direct HTTP clients.

#### Scenario: Execute proxied game-service request
- **WHEN** the dashboard proxies a valid playground request to the Game Service
- **THEN** the Game Service SHALL process the request as a normal HTTP API request and return the same response shape

#### Scenario: Reject invalid proxied game-service request
- **WHEN** the dashboard proxies an invalid or unauthorized game-service request
- **THEN** the Game Service SHALL return the same validation or authorization error it would return to a direct client
