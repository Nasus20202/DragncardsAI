# DragnCards Integration Contract Spec

## Purpose

This spec defines the integration contract between the Game Service and the DragnCards backend. It describes the external APIs, protocols, and behaviors that the Game Service depends on — written from the perspective of the Game Service as a client.

DragnCards is an Elixir/Phoenix application running as a Docker service. The Game Service treats it as a dependency and communicates with it via two interfaces: an HTTP REST API and a Phoenix Channels WebSocket connection.

## Requirements

### Requirement: HTTP authentication
The DragnCards backend SHALL expose an HTTP endpoint for session-based authentication that issues a bearer token usable for subsequent API and WebSocket calls.

#### Scenario: Successful authentication
- **WHEN** the Game Service sends `POST /api/v1/session` with `{"user": {"email": "<email>", "password": "<password>"}}`
- **THEN** the DragnCards backend SHALL respond with HTTP 200 and a JSON body containing `{"data": {"token": "<bearer-token>"}}`

#### Scenario: Failed authentication
- **WHEN** the Game Service sends `POST /api/v1/session` with invalid credentials
- **THEN** the DragnCards backend SHALL respond with a non-200 status code

### Requirement: User profile retrieval
The DragnCards backend SHALL expose an HTTP endpoint to retrieve the authenticated user's profile, including their numeric user ID.

#### Scenario: Retrieve own profile
- **WHEN** the Game Service sends `GET /api/v1/profile` with the bearer token in the `authorization` header
- **THEN** the DragnCards backend SHALL respond with HTTP 200 and a JSON body containing `{"user_profile": {"id": <integer>, ...}}`

### Requirement: Game room creation
The DragnCards backend SHALL expose an HTTP endpoint to create a new game room associated with a specific plugin.

#### Scenario: Create a room with a valid plugin
- **WHEN** the Game Service sends `POST /api/v1/games` with the bearer token and a JSON body specifying a `room` (with `user` ID and `privacy_type`) and `game_options` (with `plugin_id`, `plugin_version`, and `plugin_name`)
- **THEN** the DragnCards backend SHALL create the room and respond with HTTP 200 and a JSON body containing `{"success": {"room": {"slug": "<room-slug>", ...}}}`

#### Scenario: Room slug is unique and URL-safe
- **WHEN** a room is created
- **THEN** the returned `slug` SHALL be unique, non-empty, and suitable for use as a WebSocket channel topic in the format `room:<slug>`

### Requirement: Phoenix Channels WebSocket endpoint
The DragnCards backend SHALL expose a Phoenix Channels WebSocket endpoint that the Game Service uses for real-time game communication.

#### Scenario: WebSocket connection with authentication
- **WHEN** the Game Service connects to `<ws_url>/websocket?vsn=2.0.0&authToken=<token>`
- **THEN** the DragnCards backend SHALL accept the WebSocket connection and begin the Phoenix Channels session

#### Scenario: Phoenix message format
- **WHEN** messages are exchanged over the WebSocket
- **THEN** all messages SHALL conform to the Phoenix Channels wire format: a JSON array `[join_ref, ref, topic, event, payload]`

#### Scenario: Heartbeat acknowledgment
- **WHEN** the Game Service sends a heartbeat message (`topic: "phoenix"`, `event: "heartbeat"`, `payload: {}`)
- **THEN** the DragnCards backend SHALL respond with a `phx_reply` with `status: "ok"` within a reasonable timeout

### Requirement: Game room channel
The DragnCards backend SHALL expose a Phoenix channel per game room, joinable via the topic `room:<slug>`.

#### Scenario: Join a room channel
- **WHEN** the Game Service sends a `phx_join` message for topic `room:<slug>` with a valid auth token
- **THEN** the DragnCards backend SHALL acknowledge with `phx_reply` status `"ok"`

#### Scenario: Initial state broadcast on join
- **WHEN** the Game Service joins a room channel
- **THEN** the DragnCards backend SHALL broadcast a `current_state` event on that channel containing the full game state as its payload

#### Scenario: Leave a room channel
- **WHEN** the Game Service sends a `phx_leave` message for a joined room channel
- **THEN** the DragnCards backend SHALL acknowledge with `phx_reply` status `"ok"` and stop sending broadcasts for that topic

### Requirement: Game action execution
The DragnCards backend SHALL accept game actions submitted via the room channel and apply them to the game state.

#### Scenario: Submit a valid game action
- **WHEN** the Game Service pushes a `game_action` event on the room channel with a DragnLang payload `{"action": [...], "options": {"description": "..."}, "timestamp": <ms>}`
- **THEN** the DragnCards backend SHALL apply the action to the game state and reply with `phx_reply` status `"ok"`

#### Scenario: State update broadcast after action
- **WHEN** a game action is applied
- **THEN** the DragnCards backend SHALL broadcast a `state_update` event on the room channel indicating the game state has changed

#### Scenario: Invalid or rejected action
- **WHEN** the Game Service pushes a `game_action` event that the DragnCards engine cannot apply
- **THEN** the DragnCards backend SHALL reply with `phx_reply` status `"error"` and a response payload describing the failure

### Requirement: Game state retrieval
The DragnCards backend SHALL support explicit full-state requests on the room channel.

#### Scenario: Request full state
- **WHEN** the Game Service pushes a `request_state` event on the room channel with an empty payload
- **THEN** the DragnCards backend SHALL broadcast a `current_state` event containing the full current game state

#### Scenario: Game state shape
- **WHEN** a `current_state` payload is received
- **THEN** the payload SHALL be a JSON object containing at minimum a `"game"` key with the game state data, including `stepId` and other game-specific fields

### Requirement: Plugin availability
The DragnCards backend SHALL have plugins installed and accessible for use when creating game rooms.

#### Scenario: Marvel Champions plugin available
- **WHEN** the DragnCards backend is started with the Marvel Champions plugin volume mounted at `/plugin`
- **THEN** the plugin SHALL be registered and its `plugin_id` and `plugin_version` SHALL be known to the Game Service via environment-injected configuration

#### Scenario: Plugin loaded on room creation
- **WHEN** a room is created with a valid `plugin_id` and `plugin_version`
- **THEN** the DragnCards backend SHALL load the plugin into the room, and the initial `current_state` broadcast SHALL reflect an initialized game
