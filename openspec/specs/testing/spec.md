# Testing Spec

## Purpose

This spec defines the requirements for the Game Service test suite. Tests are organized into two layers — unit and integration — each with distinct dependencies and coverage goals. The test suite uses pytest with asyncio support.

## Requirements

### Requirement: Unit test isolation
Unit tests SHALL run without any network access, running DragnCards instance, or external services. All external dependencies SHALL be replaced with in-process fakes or mocks.

#### Scenario: Unit tests run offline
- **WHEN** the unit test suite is executed with no DragnCards or network available
- **THEN** all unit tests SHALL pass

#### Scenario: No fixture overhead
- **WHEN** unit tests are collected and run
- **THEN** no async fixtures requiring network I/O SHALL be used, and no session setup time SHALL be incurred

### Requirement: Phoenix protocol unit coverage
The `PhxMessage` encode/decode contract and `PhoenixClient` configuration logic SHALL be verified by unit tests without network I/O.

#### Scenario: PhxMessage round-trip encoding
- **WHEN** a `PhxMessage` is encoded to JSON and decoded back
- **THEN** all five fields (`join_ref`, `ref`, `topic`, `event`, `payload`) SHALL round-trip without loss, including `None` refs and non-dict payload types (list, string)

#### Scenario: URL construction
- **WHEN** a `PhoenixClient` is constructed with a base socket URL and an optional `auth_token`
- **THEN** the resulting `_url` SHALL include `/websocket`, `vsn=2.0.0`, and `authToken=<token>` when a token is provided, and SHALL omit the `authToken` param when no token is provided

#### Scenario: Ref counter
- **WHEN** `_next_ref()` is called repeatedly on a `PhoenixClient`
- **THEN** it SHALL return monotonically increasing string integers starting at `"1"`

#### Scenario: Channel event dispatch
- **WHEN** a `PhxMessage` arrives for a registered event on a `Channel`
- **THEN** all registered handlers for that event SHALL be called with the message payload, handler exceptions SHALL be suppressed, and state-update events (`current_state`, `state_update`, `send_update`) SHALL be placed on the state queue while other events SHALL not

### Requirement: Action translation unit coverage
Every concrete action type SHALL have unit test coverage for `translate_action()` verifying the exact DragnLang payload structure produced.

#### Scenario: Required payload keys
- **WHEN** `translate_action()` is called with any action
- **THEN** the result SHALL contain exactly the keys `"action"`, `"options"`, and `"timestamp"`, where `"timestamp"` is a current epoch millisecond integer and `"options"` contains a `"description"` string

#### Scenario: NextStepAction and PrevStepAction payloads
- **WHEN** `translate_action(NextStepAction())` or `translate_action(PrevStepAction())` is called
- **THEN** `payload["action"]` SHALL be `["NEXT_STEP"]` or `["PREV_STEP"]` respectively

#### Scenario: DrawCardAction payload
- **WHEN** `translate_action(DrawCardAction(player_n="player1", count=3))` is called
- **THEN** `payload["action"]` SHALL be `["DRAW_CARD", "player1", 3]` and `count` SHALL be validated to be at least 1

#### Scenario: MoveCardAction payload
- **WHEN** `translate_action(MoveCardAction(...))` is called
- **THEN** `payload["action"]` SHALL be `["MOVE_CARD", card_id, dest_group_id, dest_stack_index]` with a fifth element `dest_card_index` appended only when `dest_card_index` is non-zero

#### Scenario: SetCardPropertyAction payload
- **WHEN** `translate_action(SetCardPropertyAction(card_id="c1", property_path="currentSide", value="B"))` is called
- **THEN** `payload["action"]` SHALL be `["SET", "/cardById/c1/currentSide", "B"]`

#### Scenario: RawAction passthrough
- **WHEN** `translate_action(RawAction(action_list=[...], description="..."))` is called
- **THEN** `payload["action"]` SHALL equal the provided `action_list` verbatim

### Requirement: MCP server unit coverage
The MCP server's tool dispatch, state formatting, action deserialization, and tool schema definitions SHALL be verified by unit tests using a mocked `SessionManager`.

#### Scenario: Tool set
- **WHEN** the MCP server's tool list is queried
- **THEN** it SHALL advertise exactly five tools: `create_game`, `list_games`, `get_game_state`, `execute_action`, `delete_game`, each with a non-empty description and a JSON Schema input definition

#### Scenario: _dispatch_tool return type contract
- **WHEN** `_dispatch_tool` is called for any tool name (including unknown names and error paths)
- **THEN** it SHALL always return a `list[TextContent]` with `type == "text"`, never raising an exception

#### Scenario: _action_from_dict deserialization
- **WHEN** `_action_from_dict` is called with a dict containing a known `"type"` key
- **THEN** it SHALL return the corresponding typed action dataclass with all fields populated
- **WHEN** called with an unknown or missing `"type"`
- **THEN** it SHALL raise `ValueError`

#### Scenario: _format_state_for_llm formatting
- **WHEN** `_format_state_for_llm` is called with a `None` state
- **THEN** the result SHALL be a string indicating no state is available
- **WHEN** called with a dict state
- **THEN** the result SHALL include the session ID and the full JSON of the state

#### Scenario: MCP resource URI format
- **WHEN** the MCP resource list is queried with one active session
- **THEN** the resource URI SHALL be `game://<session_id>/state` with MIME type `application/json`

#### Scenario: Error propagation in tool dispatch
- **WHEN** `_dispatch_tool` encounters a `SessionNotFoundError`, `SessionError`, `ValueError`, or unexpected `Exception`
- **THEN** the returned `TextContent.text` SHALL contain a descriptive error prefix (`"Error (not found)"`, `"Error (session)"`, `"Error (invalid input)"`, or `"Error (unexpected)"`)

### Requirement: Integration test structure
Integration tests SHALL require a running DragnCards instance and SHALL be organized to test each layer of the stack independently before testing them together.

#### Scenario: Integration test dependency
- **WHEN** integration tests are run without a reachable DragnCards instance
- **THEN** the tests SHALL fail with a clear connection error (not a silent pass or confusing assertion failure)

#### Scenario: Test isolation via fixture teardown
- **WHEN** any integration test creates a game session
- **THEN** the session SHALL be deleted in a `finally` block or equivalent teardown, ensuring no sessions leak between tests

### Requirement: Phoenix client integration coverage
The `PhoenixClient` SHALL be tested against a live DragnCards WebSocket endpoint to verify connection, heartbeat, and channel operations.

#### Scenario: Connect and disconnect
- **WHEN** `PhoenixClient.connect()` is called with a valid auth token
- **THEN** the connection SHALL be established (`_ws` is not None, `_connected` is set), and `disconnect()` SHALL cleanly close it

#### Scenario: Heartbeat keeps connection alive
- **WHEN** the client is connected with a short heartbeat interval and time passes for at least two heartbeat cycles
- **THEN** the connection SHALL remain alive (`_connected` is still set)

#### Scenario: Join and leave a channel
- **WHEN** `client.join("room_list:lobby")` is called on a connected client
- **THEN** a `Channel` object SHALL be returned with the correct topic, and `leave()` SHALL succeed

### Requirement: Session manager integration coverage
The `SessionManager` and `GameSession` SHALL be tested end-to-end against a live DragnCards instance.

#### Scenario: Create session returns valid metadata
- **WHEN** `manager.create_session("marvel-champions")` is called
- **THEN** the returned `GameSession` SHALL have a non-empty `session_id`, `plugin_name == "marvel-champions"`, and a non-empty `room_slug`

#### Scenario: State available after creation
- **WHEN** `session.get_state()` is called on a newly created session
- **THEN** the result SHALL be a non-None dict containing a `"game"` key

#### Scenario: Session appears in list
- **WHEN** a session is created and `manager.list_sessions()` is called
- **THEN** the session's `session_id` SHALL appear in the returned list

#### Scenario: Delete session removes from pool
- **WHEN** `manager.delete_session(session_id)` is called
- **THEN** the session SHALL no longer appear in `manager.list_sessions()`

#### Scenario: Access non-existent session raises
- **WHEN** `manager.get_session("<unknown-id>")` is called
- **THEN** it SHALL raise `SessionNotFoundError`

#### Scenario: Unknown plugin raises on create
- **WHEN** `manager.create_session("nonexistent-plugin")` is called
- **THEN** it SHALL raise `SessionError` with a message indicating the plugin is not found

### Requirement: HTTP API integration coverage
The FastAPI HTTP endpoints SHALL be tested using `httpx.AsyncClient` with ASGI transport for all endpoints that invoke WebSocket operations.

#### Scenario: Health check
- **WHEN** `GET /health` is called
- **THEN** the response SHALL be HTTP 200 with `{"status": "ok"}`

#### Scenario: List sessions on fresh manager
- **WHEN** `GET /games` is called with no active sessions
- **THEN** the response SHALL be HTTP 200 with `{"sessions": []}`

#### Scenario: Create game session via HTTP
- **WHEN** `POST /games` is called with `{"plugin_name": "marvel-champions"}`
- **THEN** the response SHALL be HTTP 201 with a body containing `session.session_id`, `session.plugin_name`, `session.room_slug`, and `session.created_at`

#### Scenario: Create game with unknown plugin returns 400
- **WHEN** `POST /games` is called with an unknown plugin name
- **THEN** the response SHALL be HTTP 400 with a detail message containing "not found"

#### Scenario: Get game state returns game data
- **WHEN** `GET /games/{id}/state` is called for an active session
- **THEN** the response SHALL be HTTP 200 with `session_id` and a `state` dict containing `"game"`

#### Scenario: Get state for unknown session returns 404
- **WHEN** `GET /games/{id}/state` is called with an unknown session ID
- **THEN** the response SHALL be HTTP 404

#### Scenario: Execute action returns updated state
- **WHEN** `POST /games/{id}/actions` is called with `{"type": "next_step"}`
- **THEN** the response SHALL be HTTP 200 with `session_id` and a non-None `state`

#### Scenario: Execute action on unknown session returns 404
- **WHEN** `POST /games/{id}/actions` is called with an unknown session ID
- **THEN** the response SHALL be HTTP 404

#### Scenario: Delete session returns confirmation
- **WHEN** `DELETE /games/{id}` is called for an active session
- **THEN** the response SHALL be HTTP 200 with `{"session_id": "...", "deleted": true}`, and a subsequent `GET /games/{id}/state` SHALL return 404

#### Scenario: Delete unknown session returns 404
- **WHEN** `DELETE /games/{id}` is called with an unknown session ID
- **THEN** the response SHALL be HTTP 404

### Requirement: End-to-end coverage
The test suite SHALL include end-to-end tests that exercise the complete lifecycle through both interfaces and verify consistent shared state.

#### Scenario: Full lifecycle via HTTP
- **WHEN** a game is created, its state queried, an action executed, and then the session deleted via HTTP
- **THEN** all four operations SHALL succeed, and the session SHALL no longer exist after deletion

#### Scenario: Full lifecycle via MCP
- **WHEN** `create_game`, `get_game_state`, `execute_action`, `list_games`, and `delete_game` are invoked via `_dispatch_tool` in sequence
- **THEN** all operations SHALL succeed with valid text responses, and the session SHALL be gone after `delete_game`

#### Scenario: Concurrent HTTP and MCP access
- **WHEN** both an HTTP client and an MCP tool call query the same session state concurrently via `asyncio.gather`
- **THEN** both SHALL return valid, non-None game state for the same session

#### Scenario: Shared state consistency after action
- **WHEN** an action is executed via HTTP and then the game state is queried via MCP
- **THEN** the MCP response SHALL reflect the post-action state

### Requirement: Test environment configuration
Integration tests SHALL read their connection parameters from environment variables with sensible defaults for local development.

#### Scenario: Environment variable defaults
- **WHEN** environment variables `DRAGNCARDS_HTTP_URL`, `DRAGNCARDS_WS_URL`, `DEV_USER_EMAIL`, and `DEV_USER_PASSWORD` are not set
- **THEN** tests SHALL default to `http://localhost:4000`, `ws://localhost:4000/socket`, `dev_user@example.com`, and `password` respectively

#### Scenario: Plugin registry configuration
- **WHEN** `MC_PLUGIN_ID` and `MC_PLUGIN_VERSION` environment variables are not set
- **THEN** the integration test plugin registry SHALL default to plugin ID `1` and version `3` for `"marvel-champions"`
