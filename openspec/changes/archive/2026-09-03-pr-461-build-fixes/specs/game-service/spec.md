## MODIFIED Requirements

### Requirement: Game session lifecycle management

The Game Service SHALL provide HTTP endpoints and MCP tools to create, query, and destroy game sessions. Each session corresponds to a single DragnCards game room with a persistent WebSocket connection.

#### Scenario: Session creation timestamp is UTC-aware
- **WHEN** the Game Service creates a session without an explicitly supplied creation timestamp
- **THEN** the session SHALL use a timezone-aware timestamp representing UTC
