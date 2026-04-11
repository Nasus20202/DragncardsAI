# Room Control Spec

## Purpose

Defines how the Game Service exposes DragnCards room-control channel events (reset, seat assignment, spectator mode, close room, alert, replay) as HTTP endpoints and MCP tools.

## Requirements

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

### Requirement: Room control MCP tools
The Game Service SHALL expose each room-control operation as an MCP tool in addition to the HTTP endpoint.

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
