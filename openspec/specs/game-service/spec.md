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

#### Scenario: Export session state for setup automation
- **WHEN** a client sends an HTTP export request for an active session
- **THEN** the Game Service SHALL return a versioned snapshot document containing the session plugin identity and the game payload required to restore that state later

#### Scenario: Load exported state into a compatible session
- **WHEN** a client sends an HTTP import request with a supported snapshot document whose plugin identity matches the target session
- **THEN** the Game Service SHALL load the snapshot into the target session and return the updated game state

#### Scenario: Reject incompatible imported state
- **WHEN** a client sends an HTTP import request with an unsupported snapshot version or a snapshot for a different plugin than the target session
- **THEN** the Game Service SHALL reject the request with a descriptive client error and SHALL NOT mutate the session

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

#### Scenario: Setup import and export excluded from MCP
- **WHEN** an MCP client requests the list of available tools or resources
- **THEN** the Game Service SHALL NOT expose game-state export or load-state operations through MCP discovery

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

### Requirement: Room control operations
The Game Service SHALL support room control operations (reset, seat assignment, spectator toggle, close room, send alert, save replay, set player count) via DragnCards room channel events.

### Requirement: Game reset
The Game Service SHALL support resetting a game session's state via the DragnCards `reset_game` channel event, with an optional save-before-reset flag.

#### Scenario: Reset game without saving
- **WHEN** a client sends `POST /games/{id}/reset` with `{"save": false}`
- **THEN** the Game Service SHALL push `reset_game` on the room channel with `{"options": {"save?": false}}` and return the updated game state after the reset

#### Scenario: Reset game with save
- **WHEN** a client sends `POST /games/{id}/reset` with `{"save": true}`
- **THEN** the Game Service SHALL push `reset_game` with `{"options": {"save?": true}}`, triggering a replay save before reset, and return the updated game state

#### Scenario: Reset and reload plugin
- **WHEN** a client sends `POST /games/{id}/reset` with `{"reload_plugin": true}`
- **THEN** the Game Service SHALL push `reset_and_reload` (instead of `reset_game`) on the room channel and return the updated game state

#### Scenario: Reset non-existent session
- **WHEN** a client sends `POST /games/{id}/reset` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404

### Requirement: Seat assignment
The Game Service SHALL support assigning a user to a player seat in a game room via the DragnCards `set_seat` channel event.

#### Scenario: Assign bot to seat
- **WHEN** a client sends `POST /games/{id}/seat` with `{"player_index": 0, "user_id": <int>}`
- **THEN** the Game Service SHALL push `set_seat` on the room channel with `{player_i, new_user_id, timestamp}` and return HTTP 204

#### Scenario: Seat assignment for non-existent session
- **WHEN** a client sends `POST /games/{id}/seat` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404

### Requirement: Spectator mode
The Game Service SHALL support toggling omniscient spectator mode for a user via the DragnCards `set_spectator` channel event.

#### Scenario: Enable spectator mode
- **WHEN** a client sends `POST /games/{id}/spectator` with `{"user_id": <int>, "spectating": true}`
- **THEN** the Game Service SHALL push `set_spectator` on the room channel with `{user_id, value: true}` and return HTTP 204

#### Scenario: Disable spectator mode
- **WHEN** a client sends `POST /games/{id}/spectator` with `{"user_id": <int>, "spectating": false}`
- **THEN** the Game Service SHALL push `set_spectator` on the room channel with `{user_id, value: false}` and return HTTP 204

### Requirement: Close room
The Game Service SHALL support closing a DragnCards game room via the `close_room` channel event, saving the game before teardown.

#### Scenario: Close and save room
- **WHEN** a client sends `DELETE /games/{id}?close_room=true`
- **THEN** the Game Service SHALL push `close_room` on the room channel, wait for the push acknowledgement, remove the session from the pool, and return HTTP 204

#### Scenario: Close non-existent session
- **WHEN** a client sends `DELETE /games/{id}?close_room=true` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404

### Requirement: Send alert to room
The Game Service SHALL support broadcasting an alert message to all participants in a room via the DragnCards `send_alert` channel event.

#### Scenario: Send alert message
- **WHEN** a client sends `POST /games/{id}/alert` with `{"message": "<text>"}`
- **THEN** the Game Service SHALL push `send_alert` on the room channel with `{message: "<text>"}` and return HTTP 204

### Requirement: Save replay
The Game Service SHALL support manually saving the current replay for a game session via the DragnCards `save_replay` channel event.

#### Scenario: Save replay for active session
- **WHEN** a client sends `POST /games/{id}/replay`
- **THEN** the Game Service SHALL push `save_replay` on the room channel with a current timestamp and return HTTP 204

### Requirement: Set player count
The Game Service SHALL support setting the number of players for a game room, optionally with a plugin-specific layout.

#### Scenario: Set player count
- **WHEN** a client sends `POST /games/{id}/player-count` with `{"num_players": 2}`
- **THEN** the Game Service SHALL push a game action to set `/numPlayers` to 2, wait for state update, and return the updated game state

#### Scenario: Set player count with layout
- **WHEN** a client sends `POST /games/{id}/player-count` with `{"num_players": 2, "layout_id": "standard2Player"}`
- **THEN** the Game Service SHALL push game actions to set `/numPlayers` to 2 and set the layout, wait for state update, and return the updated game state

#### Scenario: Set player count for non-existent session
- **WHEN** a client sends `POST /games/{id}/player-count` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404

### Requirement: Room event observation
The Game Service SHALL observe and surface events broadcast by the DragnCards room channel.

### Requirement: Alert event handling
The Game Service SHALL capture `send_alert` broadcast events from the DragnCards room channel and store them in a bounded per-session alert buffer.

#### Scenario: Alert received and buffered
- **WHEN** the DragnCards backend broadcasts a `send_alert` event on a joined room channel
- **THEN** the Game Service SHALL append the alert payload `{level, text}` to the session's alert buffer (capped at 50 entries, oldest evicted first)

#### Scenario: Retrieve buffered alerts via HTTP
- **WHEN** a client sends `GET /games/{id}/alerts`
- **THEN** the Game Service SHALL return the current alert buffer as a JSON array, in the order received

#### Scenario: Alert buffer for non-existent session
- **WHEN** a client sends `GET /games/{id}/alerts` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404

### Requirement: Bad game state detection
The Game Service SHALL detect `bad_game_state` broadcasts from the DragnCards room channel and surface them as errors on subsequent session operations.

#### Scenario: Bad state raises error on next operation
- **WHEN** the DragnCards backend broadcasts `bad_game_state` on a session's room channel
- **THEN** the next call to `get_state()` or `execute_action()` on that session SHALL raise a `BadGameStateError` with a descriptive message

#### Scenario: Bad state reflected in HTTP response
- **WHEN** a `bad_game_state` event has been received for a session and a client sends `GET /games/{id}/state`
- **THEN** the Game Service SHALL return HTTP 409 with `{"detail": "game state is corrupted or unavailable"}`

### Requirement: State unavailable error handling
The Game Service SHALL detect `unable_to_get_state_on_join` and `unable_to_get_state_on_request` events and surface them as errors rather than silently timing out.

#### Scenario: Unable to get state on join
- **WHEN** the DragnCards backend sends `unable_to_get_state_on_join` after the Game Service joins a room channel
- **THEN** the `create_session` call SHALL raise a `StateUnavailableError` and the session SHALL NOT be stored in the pool

#### Scenario: Unable to get state on request
- **WHEN** the DragnCards backend sends `unable_to_get_state_on_request` in response to a `request_state` push
- **THEN** `get_state()` SHALL raise a `StateUnavailableError` instead of timing out

#### Scenario: State unavailable reflected in HTTP response
- **WHEN** `get_state()` raises `StateUnavailableError` during a `GET /games/{id}/state` request
- **THEN** the Game Service SHALL return HTTP 503 with `{"detail": "game state is temporarily unavailable"}`

### Requirement: GUI update observation
The Game Service SHALL capture `gui_update` events from the DragnCards room channel and expose the latest per-player GUI hints via the API.

#### Scenario: GUI update stored per player
- **WHEN** the DragnCards backend sends a `gui_update` event for a specific `player_n`
- **THEN** the Game Service SHALL store the payload as the latest GUI hint for that player, overwriting any previous value

#### Scenario: Retrieve GUI update via HTTP
- **WHEN** a client sends `GET /games/{id}/gui-update`
- **THEN** the Game Service SHALL return a JSON object keyed by `player_n` with the latest GUI hint payload for each player

### Requirement: Room control MCP tools
The Game Service SHALL expose each room-control operation as an MCP tool.

#### Scenario: MCP reset_game tool
- **WHEN** an MCP client invokes `reset_game` with `session_id` and optional `save` / `reload_plugin` flags
- **THEN** the Game Service SHALL perform the reset and return the updated state as text content

#### Scenario: MCP set_seat tool
- **WHEN** an MCP client invokes `set_seat` with `session_id`, `player_index`, and `user_id`
- **THEN** the Game Service SHALL push `set_seat` and return a confirmation message

#### Scenario: MCP set_spectator tool
- **WHEN** an MCP client invokes `set_spectator` with `session_id`, `user_id`, and `spectating`
- **THEN** the Game Service SHALL push `set_spectator` and return a confirmation message

#### Scenario: MCP send_alert tool
- **WHEN** an MCP client invokes `send_alert` with `session_id` and `message`
- **THEN** the Game Service SHALL push `send_alert` on the room channel and return a confirmation message

#### Scenario: MCP save_replay tool
- **WHEN** an MCP client invokes `save_replay` with `session_id`
- **THEN** the Game Service SHALL push `save_replay` and return a confirmation message

#### Scenario: MCP set_player_count tool
- **WHEN** an MCP client invokes `set_player_count` with `session_id`, `num_players`, and optional `layout_id`
- **THEN** the Game Service SHALL push the game actions and return the updated state as text content

### Requirement: Room event MCP resources
The Game Service SHALL expose room event observations as MCP resources.

#### Scenario: Alert buffer as MCP resource
- **WHEN** an MCP client reads the resource `game://{session_id}/alerts`
- **THEN** the Game Service SHALL return the alert buffer as formatted text content

#### Scenario: GUI update as MCP resource
- **WHEN** an MCP client reads the resource `game://{session_id}/gui-update`
- **THEN** the Game Service SHALL return the latest GUI hints formatted as text content suitable for LLM consumption
