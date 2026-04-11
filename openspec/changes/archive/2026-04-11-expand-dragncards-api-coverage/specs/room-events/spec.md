## ADDED Requirements

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

#### Scenario: Alert buffer as MCP resource
- **WHEN** an MCP client reads the resource `game://{session_id}/alerts`
- **THEN** the Game Service SHALL return the alert buffer as formatted text content

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

#### Scenario: GUI update as MCP resource
- **WHEN** an MCP client reads the resource `game://{session_id}/gui-update`
- **THEN** the Game Service SHALL return the latest GUI hints formatted as text content suitable for LLM consumption
