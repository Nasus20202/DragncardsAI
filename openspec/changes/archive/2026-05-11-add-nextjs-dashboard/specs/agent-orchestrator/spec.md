## ADDED Requirements

### Requirement: Dashboard-readable session metadata
The agent-orchestrator SHALL expose enough session metadata for a dashboard client to list, select, inspect, and configure sessions without relying on internal storage details.

#### Scenario: Dashboard lists session summaries
- **WHEN** the dashboard requests agent sessions
- **THEN** the agent-orchestrator SHALL return session identifiers, lifecycle status, model/provider summary, assigned MCPs, assigned skills, and recent job summary suitable for display

#### Scenario: Dashboard retrieves session details
- **WHEN** the dashboard requests one agent session
- **THEN** the agent-orchestrator SHALL return the session configuration, assigned MCPs, assigned skills, lifecycle status, and recent orchestration job state

### Requirement: Dashboard session defaults contract
The agent-orchestrator SHALL accept session creation and update requests that include dashboard-provided default model/provider settings, skill assignments, and MCP assignments, including the game-service MCP.

#### Scenario: Create session from dashboard defaults
- **WHEN** the dashboard creates a session with default model/provider, skills, and MCPs
- **THEN** the agent-orchestrator SHALL validate and persist those settings using the same rules as other session creation clients

#### Scenario: Reject invalid dashboard defaults
- **WHEN** the dashboard submits an unknown provider, skill, or MCP assignment
- **THEN** the agent-orchestrator SHALL reject the invalid value with a descriptive validation error and SHALL NOT partially persist the rejected assignment

### Requirement: Dashboard event stream compatibility
The agent-orchestrator SHALL expose streaming job events in a form that allows dashboard clients to render live chat output, progress summaries, tool calls, tool results, errors, and completion state.

#### Scenario: Stream dashboard event types
- **WHEN** a prompt job emits orchestration events
- **THEN** the agent-orchestrator SHALL provide event type, event identifier or cursor, timestamp, job identifier, and payload fields sufficient for the dashboard to render the event

#### Scenario: Resume dashboard event stream
- **WHEN** the dashboard reconnects with a last-seen event cursor
- **THEN** the agent-orchestrator SHALL stream only events after that cursor when the existing streaming API supports resumption

### Requirement: Agent orchestrator OpenAPI availability
The agent-orchestrator SHALL expose an OpenAPI document suitable for dashboard aggregation.

#### Scenario: Fetch orchestrator OpenAPI
- **WHEN** the dashboard requests the agent-orchestrator OpenAPI document from the configured endpoint
- **THEN** the agent-orchestrator SHALL return a valid OpenAPI document for its HTTP API
