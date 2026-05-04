## MODIFIED Requirements

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

#### Scenario: Export session state for setup automation
- **WHEN** a client sends an HTTP export request for an active session
- **THEN** the Game Service SHALL return a versioned snapshot document containing the session plugin identity and the game payload required to restore that state later

#### Scenario: Load exported state into a compatible session
- **WHEN** a client sends an HTTP import request with a supported snapshot document whose plugin identity matches the target session
- **THEN** the Game Service SHALL load the snapshot into the target session and return the updated game state

#### Scenario: Reject incompatible imported state
- **WHEN** a client sends an HTTP import request with an unsupported snapshot version or a snapshot for a different plugin than the target session
- **THEN** the Game Service SHALL reject the request with a descriptive client error and SHALL NOT mutate the session

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

#### Scenario: Setup import and export excluded from MCP
- **WHEN** an MCP client requests the list of available tools or resources
- **THEN** the Game Service SHALL NOT expose game-state export or load-state operations through MCP discovery
