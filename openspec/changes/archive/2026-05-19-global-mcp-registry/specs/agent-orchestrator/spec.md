## MODIFIED Requirements

### Requirement: MCP assignment
The system SHALL maintain a global registry of MCP servers accessible to all sessions. Sessions SHALL enable/disable MCPs from this registry to make them available for tool calls.

#### Scenario: Assign game-service MCP
- **WHEN** a client enables the game-service MCP for an agent session
- **THEN** prompt jobs for that session SHALL be able to call the game-service MCP tools during orchestration

#### Scenario: Inspect MCP assignments
- **WHEN** a client retrieves an agent session
- **THEN** the response SHALL include all registered MCPs with their enabled/disabled state for that session

#### Scenario: Default MCP available immediately
- **WHEN** a client creates or later loads an agent session
- **THEN** non-custom default MCPs such as `game-service` SHALL already be enabled for that session

#### Scenario: SSE transport supported
- **WHEN** an MCP is configured with transport "sse"
- **THEN** the system SHALL connect using SSE transport rather than streamable-http

## ADDED Requirements

### Requirement: Global MCP registry management
The system SHALL expose CRUD endpoints for managing the global MCP registry.

#### Scenario: List all registered MCPs
- **WHEN** a client requests GET /mcps
- **THEN** the system SHALL return all MCPs in the global registry

#### Scenario: Add new MCP to registry
- **WHEN** a client submits POST /mcps with valid name, transport, and server_url
- **THEN** the system SHALL create the MCP entry and return its details

#### Scenario: Remove MCP from registry
- **WHEN** a client submits DELETE /mcps/{mcp_name}
- **THEN** the system SHALL remove the MCP from the registry

#### Scenario: Non-custom MCP registry cannot be removed
- **WHEN** a client submits DELETE /mcps/{mcp_name} for a non-custom default MCP
- **THEN** the system SHALL reject the request instead of deleting that registry entry

### Requirement: Default game-service MCP
The system SHALL auto-create a default game-service MCP entry on startup using the configured URL.

#### Scenario: Default MCP exists after startup
- **WHEN** the agent-orchestrator starts
- **THEN** a game-service MCP entry SHALL exist in the registry with the URL from game_service_mcp_url config

### Requirement: Session MCP enablement
Sessions SHALL see all registered MCPs. Custom registries SHALL require explicit enablement, while non-custom default registries SHALL be enabled automatically.

#### Scenario: Session lists MCPs with enablement state
- **WHEN** a client requests GET /sessions/{session_id}/mcps
- **THEN** the response SHALL include all registered MCPs with their enabled/disabled state for that session

#### Scenario: Enable MCP for session
- **WHEN** a client submits PATCH /sessions/{session_id}/mcps/{mcp_name} with {"enabled": true}
- **THEN** the system SHALL enable the MCP for that session

#### Scenario: Session-scoped MCP add remains supported
- **WHEN** a client submits POST /sessions/{session_id}/mcps with a valid MCP payload
- **THEN** the system SHALL upsert that MCP in the global registry and enable it for the session

#### Scenario: Session-scoped MCP delete disables assignment
- **WHEN** a client submits DELETE /sessions/{session_id}/mcps/{mcp_name}
- **THEN** the system SHALL disable that MCP for the session without removing the global registry entry

#### Scenario: Disabled MCP tools not available
- **WHEN** a session has an MCP disabled
- **THEN** the MCP tools SHALL NOT be included in tool definitions for that session

### Requirement: Child session MCP inheritance
When spawning a subagent, the child session SHALL inherit enabled MCPs from the parent.

#### Scenario: Spawn subagent copies enabled MCPs
- **WHEN** spawn_subagent is called
- **THEN** the child session SHALL have the same MCPs enabled as the parent
