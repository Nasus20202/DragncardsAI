## MODIFIED Requirements

### Requirement: Game session lifecycle management
The Game Service SHALL provide HTTP endpoints and MCP tools to create, query, and destroy game sessions. Each session corresponds to a single DragnCards game room with a persistent WebSocket connection.

Deleting an EPHEMERAL session SHALL close its DragnCards room as part of the teardown. An ephemeral (view-only reconstruction) session created the room solely to view a past moment and owns it outright, so detaching from the channel is not enough — the room itself must go, otherwise every reconstruction leaks a room. Room closing is best-effort: a failure SHALL be logged and SHALL NOT abort the rest of the teardown. Deleting a kept (non-ephemeral) session SHALL leave its room open, because that room belongs to the user and only this client detaches from it.

#### Scenario: Create a new game session via HTTP
- **WHEN** a client sends `POST /games` with a plugin identifier (e.g., `marvel-champions`)
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, initialize the game, and return a session ID with initial game metadata

#### Scenario: Create a new game session via MCP
- **WHEN** an MCP client invokes the `create_game` tool with a plugin name parameter
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, assign the model to the first available player seat, and return the session ID and initial game info

#### Scenario: Attach to an existing game session via MCP
- **WHEN** an MCP client invokes the `attach_game` tool with a room slug parameter
- **THEN** the Game Service SHALL join the existing room via WebSocket, assign the model to the first available player seat, and return the session ID and initial game info

#### Scenario: Delete a game session
- **WHEN** a client sends `DELETE /games/{id}` or invokes the `delete_game` MCP tool
- **THEN** the Game Service SHALL close the WebSocket connection to the DragnCards room, clean up session state, and return a confirmation

#### Scenario: Delete an ephemeral reconstruction session
- **WHEN** an ephemeral session is deleted, whether by an explicit client teardown or by the TTL reaper
- **THEN** the Game Service SHALL close its DragnCards room in addition to leaving the channel and removing the session record, leaving no orphaned room behind

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
