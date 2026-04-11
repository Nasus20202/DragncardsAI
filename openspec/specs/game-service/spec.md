# Game Service Spec

## Purpose

The Game Service is a Python backend that bridges AI/MCP clients with the DragnCards game engine. It exposes game capabilities via both an HTTP REST API (FastAPI) and a Model Context Protocol (MCP) server, both sharing the same session pool within a single process. It manages persistent WebSocket connections to the DragnCards backend using the Phoenix Channels protocol.

## Requirements

### Requirement: Game session lifecycle management
The Game Service SHALL provide HTTP endpoints and MCP tools to create, query, and destroy game sessions. Each session corresponds to a single DragnCards game room with a persistent WebSocket connection.

#### Scenario: Create a new game session via HTTP
- **WHEN** a client sends `POST /games` with a plugin identifier (e.g., `marvel-champions`)
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, initialize the game, and return a session ID with initial game metadata

#### Scenario: Create a new game session via MCP
- **WHEN** an MCP client invokes the `create_game` tool with a plugin name parameter
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, and return the session ID and initial game info

#### Scenario: Delete a game session
- **WHEN** a client sends `DELETE /games/{id}` or invokes the `delete_game` MCP tool
- **THEN** the Game Service SHALL close the WebSocket connection to the DragnCards room, clean up session state, and return a confirmation

#### Scenario: Create session with invalid plugin
- **WHEN** a client requests a game with an unknown plugin identifier
- **THEN** the Game Service SHALL return an error response indicating the plugin is not available

#### Scenario: List active game sessions
- **WHEN** a client sends `GET /games` or invokes the `list_games` MCP tool
- **THEN** the Game Service SHALL return a list of all active game sessions with their IDs, plugin names, and creation timestamps

### Requirement: Game state observation
The Game Service SHALL provide endpoints and MCP tools to query the current game state for a given session.

#### Scenario: Get current game state via HTTP
- **WHEN** a client sends `GET /games/{id}/state`
- **THEN** the Game Service SHALL return the current game state including all card groups (hand, deck, play area, discard, etc.), card properties, player state, round/phase information, and any game counters

#### Scenario: Get current game state via MCP
- **WHEN** an MCP client invokes the `get_game_state` tool with a session ID
- **THEN** the Game Service SHALL return the game state formatted as structured text suitable for LLM consumption, clearly describing the board state including card names, locations, and properties

#### Scenario: Get state for non-existent session
- **WHEN** a client requests state for an invalid session ID
- **THEN** the Game Service SHALL return a 404 error (HTTP) or an MCP error with a descriptive message

#### Scenario: State reflects latest game changes
- **WHEN** an action is executed on a session and then the state is queried
- **THEN** the returned state SHALL reflect the result of the most recent action, including any automated effects triggered by the DragnCards engine

### Requirement: Game action execution
The Game Service SHALL provide endpoints and MCP tools to execute game actions within a session.

#### Scenario: Execute a card movement action
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to move a card from one group to another (e.g., play a card from hand to the play area)
- **THEN** the Game Service SHALL translate the action into the appropriate DragnCards WebSocket message, execute it, wait for the state update, and return the resulting game state

#### Scenario: Execute a game phase action
- **WHEN** a client requests a phase-related action (e.g., end the player phase, advance to the next round)
- **THEN** the Game Service SHALL execute the phase transition via WebSocket and return the updated game state

#### Scenario: Execute action on non-existent session
- **WHEN** a client requests an action on an invalid session ID
- **THEN** the Game Service SHALL return a 404 error (HTTP) or an MCP error with a descriptive message

#### Scenario: Execute an invalid action
- **WHEN** a client requests an action that is not valid in the current game state
- **THEN** the Game Service SHALL return an error indicating the action could not be performed

### Requirement: WebSocket connection to DragnCards
The Game Service SHALL maintain persistent WebSocket connections to the DragnCards backend using the Phoenix Channels protocol.

#### Scenario: Establish connection on session creation
- **WHEN** a new game session is created
- **THEN** the Game Service SHALL open a WebSocket connection to the DragnCards backend, authenticate, and join the appropriate game channel

#### Scenario: Handle connection loss
- **WHEN** the WebSocket connection to DragnCards is lost
- **THEN** the Game Service SHALL attempt to reconnect and rejoin the game channel, and SHALL report the session as degraded if reconnection fails

#### Scenario: Phoenix heartbeat maintenance
- **WHEN** a WebSocket connection is active
- **THEN** the Game Service SHALL send periodic heartbeat messages as required by the Phoenix Channels protocol to keep the connection alive

### Requirement: MCP protocol compliance
The Game Service SHALL implement the Model Context Protocol, exposing game capabilities as MCP tools and resources accessible to any MCP-compatible client.

#### Scenario: MCP client connection
- **WHEN** an MCP client connects to the Game Service
- **THEN** the server SHALL complete the MCP handshake and advertise available tools and resources

#### Scenario: Tool discovery
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL return tool definitions for game session management (`create_game`, `list_games`, `delete_game`), state observation (`get_game_state`), and action execution (`execute_action`), each with proper JSON Schema parameter descriptions

#### Scenario: Game state as MCP resource
- **WHEN** an MCP client reads the resource `game://{session_id}/state`
- **THEN** the Game Service SHALL return the current game state as a resource with appropriate content type

#### Scenario: MCP error handling
- **WHEN** the Game Service encounters an error processing an MCP tool call
- **THEN** it SHALL return the error as an MCP error response with a descriptive message

### Requirement: Plugin management
The Game Service SHALL support loading DragnCards-compatible plugins for game initialization.

#### Scenario: Marvel Champions plugin available
- **WHEN** the Game Service starts with the Marvel Champions plugin configured
- **THEN** the plugin SHALL be available for use when creating new game sessions

#### Scenario: Plugin configuration
- **WHEN** the Game Service is configured with plugin paths or identifiers
- **THEN** it SHALL validate that the referenced plugins exist and are loadable by the DragnCards backend

### Requirement: Dual interface coexistence
The Game Service SHALL run both the HTTP API (FastAPI) and MCP server in the same Python process, sharing the same session pool.

#### Scenario: Concurrent HTTP and MCP access
- **WHEN** both an HTTP client and an MCP client interact with the same game session
- **THEN** both SHALL observe consistent game state and both interfaces SHALL function correctly

#### Scenario: Service startup
- **WHEN** the Game Service starts
- **THEN** it SHALL initialize both the FastAPI HTTP server and the MCP server, and verify connectivity to the DragnCards backend

### Requirement: Room control endpoints
The Game Service SHALL expose HTTP endpoints for each DragnCards room-control channel event: reset, seat assignment, spectator toggle, close room, send alert, and save replay.

#### Scenario: POST /games/{id}/reset resets game state
- **WHEN** a client sends `POST /games/{id}/reset`
- **THEN** the Game Service SHALL execute the appropriate reset action on the DragnCards backend and return the updated game state or HTTP 204

#### Scenario: POST /games/{id}/seat assigns a player seat
- **WHEN** a client sends `POST /games/{id}/seat` with player index and user ID
- **THEN** the Game Service SHALL push `set_seat` on the room channel and return HTTP 204

#### Scenario: POST /games/{id}/spectator toggles spectator mode
- **WHEN** a client sends `POST /games/{id}/spectator` with user ID and spectating flag
- **THEN** the Game Service SHALL push `set_spectator` on the room channel and return HTTP 204

#### Scenario: DELETE /games/{id} with close_room=true saves and closes room
- **WHEN** a client sends `DELETE /games/{id}?close_room=true`
- **THEN** the Game Service SHALL push `close_room`, clean up the session, and return HTTP 204

#### Scenario: POST /games/{id}/alert broadcasts an alert
- **WHEN** a client sends `POST /games/{id}/alert` with a message
- **THEN** the Game Service SHALL push `send_alert` on the room channel and return HTTP 204

#### Scenario: POST /games/{id}/replay saves a replay
- **WHEN** a client sends `POST /games/{id}/replay`
- **THEN** the Game Service SHALL push `save_replay` on the room channel and return HTTP 204

### Requirement: Room event observation endpoints
The Game Service SHALL expose HTTP endpoints to query buffered alerts and latest GUI update hints for a session.

#### Scenario: GET /games/{id}/alerts returns alert buffer
- **WHEN** a client sends `GET /games/{id}/alerts`
- **THEN** the Game Service SHALL return a JSON array of all buffered alert payloads for the session

#### Scenario: GET /games/{id}/gui-update returns latest GUI hints
- **WHEN** a client sends `GET /games/{id}/gui-update`
- **THEN** the Game Service SHALL return the latest `gui_update` payload per player for the session

### Requirement: Room control and event MCP tools
The Game Service SHALL expose each new room-control operation and event-observation endpoint as an MCP tool or resource.

#### Scenario: New MCP tools discoverable
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL include `reset_game`, `set_seat`, `set_spectator`, `send_alert`, and `save_replay` in the tool list with proper JSON Schema parameter descriptions

#### Scenario: New MCP resources discoverable
- **WHEN** an MCP client lists available resources
- **THEN** the server SHALL include `game://{session_id}/alerts` and `game://{session_id}/gui-update` resources
