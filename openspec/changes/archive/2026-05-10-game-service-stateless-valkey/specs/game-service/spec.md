## MODIFIED Requirements

### Requirement: Game session lifecycle management
The Game Service SHALL provide HTTP endpoints and MCP tools to create, query, and destroy game sessions. Each session corresponds to a single DragnCards game room with a persistent WebSocket connection, and the session coordination data SHALL be stored externally so the service can recover active sessions after restart.

#### Scenario: Create a new game session via HTTP
- **WHEN** a client sends `POST /games` with a plugin identifier (e.g., `marvel-champions`)
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, initialize the game, record the session coordination data in Valkey, and return a session ID with initial game metadata

#### Scenario: Create a new game session via MCP
- **WHEN** an MCP client invokes the `create_game` tool with a plugin name parameter
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, store the coordination record in Valkey, and return the session ID and initial game info

#### Scenario: Delete a game session
- **WHEN** a client sends `DELETE /games/{id}` or invokes the `delete_game` MCP tool
- **THEN** the Game Service SHALL close the WebSocket connection to the DragnCards room, clean up session state, remove the coordination record from Valkey, and return a confirmation

#### Scenario: Create session with invalid plugin
- **WHEN** a client requests a game with an unknown plugin identifier
- **THEN** the Game Service SHALL return an error response indicating the plugin is not available

#### Scenario: List active game sessions
- **WHEN** a client sends `GET /games` or invokes the `list_games` MCP tool
- **THEN** the Game Service SHALL return a list of all active game sessions with their IDs, plugin names, and creation timestamps from the coordination store

#### Scenario: Export session state for setup automation
- **WHEN** a client sends an HTTP export request for an active session
- **THEN** the Game Service SHALL return a versioned snapshot document containing the session plugin identity and the game payload required to restore that state later

#### Scenario: Load exported state into a compatible session
- **WHEN** a client sends an HTTP import request with a supported snapshot document whose plugin identity matches the target session
- **THEN** the Game Service SHALL load the snapshot into the target session and return the updated game state

#### Scenario: Reject incompatible imported state
- **WHEN** a client sends an HTTP import request with an unsupported snapshot version or a snapshot for a different plugin than the target session
- **THEN** the Game Service SHALL reject the request with a descriptive client error and SHALL NOT mutate the session

### Requirement: Session coordination state is stored externally
The Game Service SHALL store session coordination data in Valkey rather than relying on process-local state as the source of truth.

#### Scenario: Session metadata survives service restart
- **WHEN** the Game Service restarts while active sessions exist
- **THEN** it SHALL be able to reload session coordination data from Valkey and continue managing those sessions

#### Scenario: Session lookup uses the external store
- **WHEN** the service needs to resolve an active session by ID
- **THEN** it SHALL retrieve the coordination record from Valkey instead of reading only in-memory state

### Requirement: Session coordination data is updated atomically
The Game Service SHALL update coordination records in Valkey atomically enough to avoid partial session registration or deletion.

#### Scenario: New session is recorded once
- **WHEN** a new session is created
- **THEN** the service SHALL write the session coordination record to Valkey before treating the session as active

#### Scenario: Deleted session is removed from the store
- **WHEN** a session is deleted
- **THEN** the service SHALL remove the session coordination record from Valkey so later lookups fail cleanly

### Requirement: Stored coordination data is limited to runtime metadata
The Game Service SHALL store only coordination metadata needed to manage live sessions and reconnect to DragnCards, not full game state snapshots.

#### Scenario: Live game state remains external
- **WHEN** a client queries current game state after the service reloads coordination data
- **THEN** the Game Service SHALL continue to fetch the authoritative game state from DragnCards rather than Valkey

#### Scenario: Coordination store does not replace DragnCards
- **WHEN** the service processes an action or room event
- **THEN** it SHALL continue to use DragnCards as the source of truth for game state changes

### Requirement: WebSocket connection to DragnCards
The Game Service SHALL maintain persistent WebSocket connections to the DragnCards backend using the Phoenix Channels protocol, and it SHALL be able to restore active session coordination from Valkey after restart.

#### Scenario: Establish connection on session creation
- **WHEN** a new game session is created
- **THEN** the Game Service SHALL open a WebSocket connection to the DragnCards backend, authenticate, join the appropriate game channel, and persist the coordination data in Valkey

#### Scenario: Handle connection loss
- **WHEN** the WebSocket connection to DragnCards is lost
- **THEN** the Game Service SHALL attempt to reconnect and rejoin the game channel, and SHALL report the session as degraded if reconnection fails

#### Scenario: Phoenix heartbeat maintenance
- **WHEN** a WebSocket connection is active
- **THEN** the Game Service SHALL send periodic heartbeat messages as required by the Phoenix Channels protocol to keep the connection alive

### Requirement: Dual interface coexistence
The Game Service SHALL run both the HTTP API (FastAPI) and MCP server in the same Python process, sharing the same session pool derived from the external coordination store.

#### Scenario: Concurrent HTTP and MCP access
- **WHEN** both an HTTP client and an MCP client interact with the same game session
- **THEN** both SHALL observe consistent game state and both interfaces SHALL function correctly

#### Scenario: Service startup
- **WHEN** the Game Service starts
- **THEN** it SHALL initialize both the FastAPI HTTP server and the MCP server, verify connectivity to Valkey, and verify connectivity to the DragnCards backend
