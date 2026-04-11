## ADDED Requirements

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
