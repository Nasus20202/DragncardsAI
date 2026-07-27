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
- **THEN** the Game Service SHALL create a new DragnCards game room via WebSocket, load the specified plugin, assign the model to the first available player seat, and return the session ID and initial game info

#### Scenario: Attach to an existing game session via MCP
- **WHEN** an MCP client invokes the `attach_game` tool with a room slug parameter
- **THEN** the Game Service SHALL join the existing room via WebSocket, assign the model to the first available player seat, and return the session ID and initial game info

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
The Game Service SHALL provide endpoints and MCP tools to query the current game state for a given session, returning a simplified representation for Marvel Champions sessions.

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

#### Scenario: Get simplified state for Marvel Champions via HTTP
- **WHEN** a client sends `GET /games/{id}/state` for a Marvel Champions session
- **THEN** the Game Service SHALL return a flattened representation containing only `roundNumber`, `mode`, `villainHitPoints`, `players` (hitPoints/handSize), and `zones` with visible cards (id, instanceId, name, currentSide, exhausted, tokens)

#### Scenario: Simplified state omits attachment hierarchy
- **WHEN** a client requests state for a Marvel Champions session
- **THEN** the Game Service SHALL exclude cards that are attachments tucked under other cards from zone listings

### Requirement: Game action execution
The Game Service SHALL provide endpoints and MCP tools to execute game actions within a session.

#### Scenario: Execute a card movement action
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to move a card from one group to another (e.g., play a card from hand to the play area)
- **THEN** the Game Service SHALL translate the action into the appropriate DragnCards WebSocket message, execute it, and return a success acknowledgment (`session_id` + `success: true`); the caller must use `get_game_state` to observe the updated state

#### Scenario: Execute a card movement action with instance_id parameter
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to move a card from one group to another (e.g., play a card from hand to the play area)
- **THEN** the Game Service SHALL accept `instance_id` as the parameter name for the card identifier, consistent with the `instanceId` naming in the game state JSON

#### Scenario: Execute card property action with instance_id parameter
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to set a card property
- **THEN** the Game Service SHALL accept `instance_id` as the parameter name for the card identifier, consistent with the `instanceId` naming in the game state JSON

#### Scenario: Execute a game phase action
- **WHEN** a client requests a phase-related action (e.g., end the player phase, advance to the next round)
- **THEN** the Game Service SHALL execute the phase transition via WebSocket and return a success acknowledgment; the caller must use `get_game_state` to observe the updated state

#### Scenario: Execute action on non-existent session
- **WHEN** a client requests an action on an invalid session ID
- **THEN** the Game Service SHALL return a 404 error (HTTP) or an MCP error with a descriptive message

#### Scenario: Execute an invalid action
- **WHEN** a client requests an action that is not valid in the current game state
- **THEN** the Game Service SHALL return an error indicating the action could not be performed

### Requirement: Shuffle-into-deck returns a card to its own deck
The Game Service SHALL, for the `shuffle_into_deck` action, move the named card into the group identified by that card's own `deckGroupId` and then shuffle that group. The caller SHALL NOT name a destination group; the destination is derived from the card.

The emitted DragnLang SHALL read `deckGroupId` as a **value**, using dotted `$GAME.cardById.<instance_id>.deckGroupId` access. It SHALL NOT read it through a `/`-prefixed path literal: DragnCards evaluates a string beginning with `/` to the path list it denotes rather than to the value stored at that path, so such a literal yields a list where a group id is required and the engine rejects the move with `Group not found: cardById<instance_id>deckGroupId`.

`/`-prefixed path literals remain correct as the *target* of a write operation such as `SET` or `INCREASE_VAL`, where the path list is what those operations expect.

The action SHALL accept an optional `player_n` and, when it is supplied, inject `player_ui.playerN` into the DragnCards request, so that plugin automation triggered by deck insertion can resolve `$PLAYER_N`. Without it a card returning to a `playerNDeck` is rejected with `Variable $PLAYER_N is undefined`. `player_n` remains optional because shared decks need no player context.

#### Scenario: Card is moved into its own deck and the deck is shuffled
- **WHEN** a client sends `POST /games/{id}/actions/shuffle_into_deck`, or invokes the `shuffle_into_deck` MCP tool, for a card held in a player's hand, supplying that player as `player_n`
- **THEN** the action SHALL complete with a null `error`
- **AND** the card SHALL afterwards be in the group named by its `deckGroupId`
- **AND** that group SHALL contain one more stack than before
- **AND** that group's stack order SHALL have been shuffled

#### Scenario: Deck group is read as a value, not as a path
- **WHEN** the Game Service translates a `shuffle_into_deck` action
- **THEN** the deck-group expression bound for the subsequent move and shuffle SHALL be a dotted `$GAME.` read
- **AND** it SHALL NOT be a `/`-prefixed path literal

#### Scenario: Player context is forwarded to deck-insertion automation
- **WHEN** a `shuffle_into_deck` action supplies `player_n`
- **THEN** the emitted request SHALL carry `player_ui.playerN` set to that player
- **AND** when `player_n` is omitted the request SHALL carry no `player_ui`

### Requirement: Card catalog responses expose relevant provider metadata
The Game Service SHALL expose card search responses that include the relevant gameplay, identification, and printing metadata available from the registered provider's source data, using a documented normalized response shape.

#### Scenario: Marvel Champions card search returns expanded metadata
- **WHEN** a client sends `GET /cards/marvel-champions`
- **THEN** each returned card SHALL include the existing loading identifiers and SHALL also include the relevant optional metadata available for that card, such as card source identifiers, type/classification, uniqueness, gameplay stats, text/resource fields, author or official status, traits, and printing metadata

#### Scenario: Missing provider fields remain optional
- **WHEN** a provider cannot supply a normalized card field for a given card
- **THEN** the Game Service SHALL omit that field or return it as `null` according to the documented response model rather than failing the request

#### Scenario: Card catalog remains provider-defined
- **WHEN** a new plugin provider is registered with its own card metadata mapping
- **THEN** the Game Service SHALL expose that provider's normalized card metadata through the same card search contract without requiring router-specific behavior

### Requirement: Prebuilt set catalog discovery
The Game Service SHALL expose a read-only prebuilt set catalog for the Marvel Champions plugin through HTTP and MCP.

#### Scenario: List all prebuilt sets via HTTP
- **WHEN** a client sends `GET /prebuilt-sets/marvel-champions` without filters
- **THEN** the Game Service SHALL return all available prebuilt sets sourced from the plugin's `sets.json`
- **AND** each returned set SHALL include at least its `id`, `name`, and `type`

#### Scenario: Filter prebuilt sets by name or type
- **WHEN** a client sends `GET /prebuilt-sets/marvel-champions` with a name or type filter
- **THEN** the Game Service SHALL return only sets matching the requested filter values

#### Scenario: MCP exposes the Marvel Champions set catalog tool
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL expose `search_prebuilt_sets_marvel_champions` as a discovery tool for the Marvel Champions set catalog

#### Scenario: Empty result set
- **WHEN** no prebuilt sets match the requested filters
- **THEN** the Game Service SHALL return an empty list instead of an error

### Requirement: Prebuilt set catalog is read-only
The Game Service SHALL treat the prebuilt set catalog as discovery data only and SHALL NOT mutate DragnCards state when serving it.

#### Scenario: Catalog request does not change game state
- **WHEN** a client requests the prebuilt set catalog for any plugin
- **THEN** the Game Service SHALL not create, modify, or destroy any game session
- **AND** SHALL not send any DragnCards room events

### Requirement: Global action catalog exposes generic DragnCards actions
The Game Service SHALL make `GET /actions` return only the generic action surface supported by the game-service and `@external/dragncards/`, independent of any specific plugin session.

#### Scenario: Global action catalog excludes plugin-defined actions
- **WHEN** a client sends `GET /actions`
- **THEN** the response SHALL include the typed execute-action schemas and generic DragnLang operation catalog, and SHALL NOT require plugin-specific metadata to be present

#### Scenario: Global action catalog remains stable without a session
- **WHEN** no active session exists
- **THEN** `GET /actions` SHALL still return the generic action catalog successfully

### Requirement: Session action catalog exposes plugin-specific metadata
The Game Service SHALL make `GET /games/{session_id}/actions` return the global action catalog plus plugin-specific action metadata and affordances for the session's plugin.

#### Scenario: Session action catalog includes plugin-defined action metadata
- **WHEN** a client sends `GET /games/{session_id}/actions` for a Marvel Champions session
- **THEN** the response SHALL include plugin-specific metadata for the session's plugin, including the relevant named action lists, hotkeys, touch-bar entries, default actions, player-count layouts, and load-group information that the provider can derive

#### Scenario: Session action catalog preserves generic execute-action schemas
- **WHEN** a client sends `GET /games/{session_id}/actions`
- **THEN** the response SHALL still include the same generic typed action schemas and generic DragnLang operation catalog returned by `GET /actions`

#### Scenario: Unknown plugin yields only generic catalog
- **WHEN** a session's plugin has no registered provider metadata
- **THEN** the Game Service SHALL return the generic action catalog and empty plugin-specific metadata collections instead of failing the request

### Requirement: Generic game action definitions have one source of truth
The Game Service SHALL define generic game action typing, translation, and catalog metadata from one concentrated action Module so that generic action behavior is described once and reused across the system.

#### Scenario: Global and session action catalogs share generic definitions
- **WHEN** a client requests `GET /actions` and `GET /games/{session_id}/actions`
- **THEN** the generic action schemas and descriptions in both responses SHALL be derived from the same action definition source

#### Scenario: Generic action execution reuses shared translation logic
- **WHEN** the Game Service executes a generic action that also appears in the action catalog, including player-count changes
- **THEN** the Game Service SHALL route that action through the shared action translation Module
- **AND** SHALL NOT require a second translation Implementation for the same action semantics

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
The Game Service SHALL implement the Model Context Protocol, exposing game capabilities as MCP tools accessible to any MCP-compatible client.

#### Scenario: MCP client connection
- **WHEN** an MCP client connects to the Game Service
- **THEN** the server SHALL complete the MCP handshake and advertise available tools

#### Scenario: Tool discovery
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL return tool definitions for game session management (`create_game`, `list_games`, `delete_game`), state observation (`get_game_state`), action execution (`execute_action`), card catalog discovery (`list_card_providers`, `search_cards_<provider>`), and prebuilt set catalog discovery (`search_prebuilt_sets_marvel_champions`), each with proper JSON Schema parameter descriptions

#### Scenario: Tool discovery excludes room-control operations
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL NOT expose room-control tools including reset, seat assignment, spectator toggles, player-count changes, replay saves, alert broadcasting, or room closure

#### Scenario: Tool discovery excludes debug endpoints
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL NOT expose tools for `get_raw_game_state`, `execute_action` (generic), or `raw_action` endpoints

#### Scenario: MCP error handling
- **WHEN** the Game Service encounters an error processing an MCP tool call
- **THEN** it SHALL return the error as an MCP error response with a descriptive message

#### Scenario: Setup import and export excluded from MCP
- **WHEN** an MCP client requests the list of available tools
- **THEN** the Game Service SHALL NOT expose game-state export or load-state operations through MCP discovery

### Requirement: Debug endpoints are HTTP-only
The Game Service SHALL expose raw state access, generic action execution, and raw DragnLang action execution endpoints as HTTP-only for debugging purposes.

#### Scenario: Raw state endpoint accessible via HTTP
- **WHEN** a client sends `GET /games/{session_id}/state/raw` via HTTP
- **THEN** the Game Service SHALL return the raw, untransformed game state

#### Scenario: Raw state endpoint not exposed via MCP
- **WHEN** an MCP client queries available tools
- **THEN** the Game Service SHALL NOT include a tool for accessing raw game state

#### Scenario: Generic action endpoint accessible via HTTP
- **WHEN** a client sends `POST /games/{session_id}/actions` with an action payload via HTTP
- **THEN** the Game Service SHALL execute the action and return a success acknowledgment

#### Scenario: Generic action endpoint not exposed via MCP
- **WHEN** an MCP client queries available tools
- **THEN** the Game Service SHALL NOT include a tool for generic action execution

#### Scenario: Raw action endpoint accessible via HTTP
- **WHEN** a client sends `POST /games/{session_id}/actions/raw` with a DragnLang action list via HTTP
- **THEN** the Game Service SHALL execute the raw action list and return a success acknowledgment

#### Scenario: Raw action endpoint not exposed via MCP
- **WHEN** an MCP client queries available tools
- **THEN** the Game Service SHALL NOT include a tool for raw DragnLang action execution

#### Scenario: Debug endpoints marked in documentation
- **WHEN** a developer views the OpenAPI schema or API documentation
- **THEN** the three debug endpoints SHALL be annotated with "DEBUG ONLY" markers indicating they are intended for development and debugging purposes

### Requirement: Action helper endpoints have descriptive summaries
The Game Service SHALL provide descriptive summaries for all explicit action handler endpoints to improve MCP tool discoverability.

#### Scenario: Action helper endpoints have summaries
- **WHEN** an MCP client queries available tools
- **THEN** each action tool SHALL include a descriptive summary explaining its purpose and when to use it

#### Scenario: Summaries warn about preferred alternatives
- **WHEN** an agent views tool descriptions in their MCP client
- **THEN** low-level tools SHALL include warnings about better-typed alternatives (e.g., `set_card_property` warns to use `flip_card` instead)

#### Scenario: Summaries describe the behaviour the action actually performs
- **WHEN** an agent reads an action tool's summary
- **THEN** the summary SHALL describe only effects the underlying DragnLang action list performs, and SHALL NOT claim effects the action does not perform

#### Scenario: Drawing to hand limit has clear guidance
- **WHEN** an agent needs to draw cards up to hand limit
- **THEN** the `mulligan_draw_hand` tool description SHALL state that it draws the player up to their hand size, discards nothing, and does nothing when the hand is already full
- **AND** it SHALL clarify it is the preferred tool for this use case over `draw_card`

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

### Requirement: Room semantics are owned by one room Module
The Game Service SHALL concentrate room semantics behind one room Module whose Interface is used by HTTP adapters, MCP adapters, and session-pool orchestration.

That room Module SHALL own state refresh, stale-state recovery, action execution, room control operations, alert buffering, GUI update buffering, and room-side error handling.

Phoenix protocol details such as event names, refs, payload construction, and raw send/wait behavior SHALL live behind a Phoenix Adapter at the Seam and SHALL NOT be required knowledge for callers using room behavior.

#### Scenario: HTTP and MCP adapters share room semantics
- **WHEN** a caller uses HTTP or MCP to observe state, execute an action, or invoke room control for the same session
- **THEN** both adapters SHALL delegate through the same room Module Interface
- **AND** SHALL observe the same state-freshness, recovery, and room-side error semantics

#### Scenario: Phoenix protocol knowledge is hidden behind an Adapter
- **WHEN** room behavior requires Phoenix join refs, message refs, event names, or wire payloads
- **THEN** that knowledge SHALL be owned by a Phoenix Adapter behind the room Module Seam
- **AND** SHALL NOT be duplicated in HTTP adapters, MCP adapters, or session-pool callers

### Requirement: Cross-replica session operation serialization
The Game Service SHALL serialize state-changing and state-refreshing operations per session using the coordination store so concurrent requests across replicas cannot interleave on the same DragnCards room channel.

#### Scenario: Replica B receives a request while Replica A is already operating on the same session
- **WHEN** Replica A holds the session operation lock and Replica B receives another operation for the same `session_id`
- **THEN** Replica B SHALL wait up to a bounded timeout to acquire the lock, and SHALL return an explicit "session busy" error if the lock is not acquired

#### Scenario: Two concurrent operations target different sessions
- **WHEN** requests execute simultaneously for different `session_id` values
- **THEN** the Game Service SHALL allow both operations to proceed in parallel

### Requirement: Room control operations
The Game Service SHALL support room control operations (reset, seat assignment, spectator toggle, close room, send alert, save replay, set player count) via DragnCards room channel events.

#### Scenario: Room control operation is routed to the room channel
- **WHEN** a client invokes a supported room control operation for a session
- **THEN** the Game Service SHALL perform it via the corresponding DragnCards room channel event

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

#### Scenario: Broadcast room event is surfaced
- **WHEN** the DragnCards room channel broadcasts an event for an observed session
- **THEN** the Game Service SHALL surface that event through its observation interface

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

### Requirement: Look up a session by room slug
The Game Service SHALL provide a single, dedicated, non-mutating endpoint and MCP
tool (`GET /games/by-slug/{room_slug}`) that resolves a session's human-readable
DragnCards `room_slug` to its session metadata, including the canonical UUID
`session_id`. This lookup SHALL be the ONLY place a room slug is accepted.

State, mutation, and delete endpoints (everything that takes a `{session_id}` path
parameter) SHALL remain UUID-only and SHALL NOT accept a room slug. The room slug
(`adjective-noun-NNNN`, roughly 27 bits and visible in DragnCards URLs) is
low-entropy and guessable, and the session endpoints are unauthenticated; the
unguessable UUID is therefore the only access-control barrier protecting a session,
so a slug MUST NOT be able to authorize a state read, mutation, or delete.

#### Scenario: Resolve a session by its room slug
- **WHEN** a client supplies a session's DragnCards `room_slug` to `GET /games/by-slug/{room_slug}`
- **THEN** the Game Service SHALL return that session's metadata, including its canonical UUID `session_id`, without modifying any session

#### Scenario: Unknown room slug is rejected as not found
- **WHEN** a client supplies a `room_slug` that does not correspond to any managed session
- **THEN** the lookup SHALL fail with the not-found behavior (HTTP 404) and SHALL NOT create, modify, or destroy any session

#### Scenario: State, mutation, and delete endpoints are UUID-only
- **WHEN** a client supplies a room slug in the `{session_id}` position of any state, mutation, or delete endpoint
- **THEN** the Game Service SHALL NOT resolve the slug and SHALL fail with the not-found behavior (HTTP 404), so a guessable slug can never authorize a read, mutation, or delete

#### Scenario: Non-canonical UUID still matches the stored session
- **WHEN** a client supplies a valid but non-canonical UUID `session_id` (e.g. uppercase or braced) to a UUID-only endpoint
- **THEN** the Game Service SHALL normalize it to its canonical form (`str(uuid.UUID(value))`) so it matches the canonical id stored on the session

#### Scenario: Slug index is maintained across session lifecycle
- **WHEN** a session is created or attached and later deleted
- **THEN** the Game Service SHALL add a `room_slug -> session_id` mapping to the session store on creation and remove that mapping on deletion so the slug lookup stays consistent

#### Scenario: MCP tool documentation describes the lookup
- **WHEN** an MCP client inspects the `lookup_session_by_slug` tool
- **THEN** its description SHALL state that the tool resolves a room slug to a session's metadata (including the `session_id`) and that state/mutation/delete tools remain UUID-only

### Requirement: Game-state and status event emission
The Game Service SHALL emit a game-state/status event to the history ingestion bus after each state-mutating operation on a session — including action execution, prebuilt-deck loading, snapshot/state loading, and game reset — capturing the resulting game-state representation and the game status, using the versioned history event envelope with actor `game-service` and the session identifier as the `game_id`.

#### Scenario: Emit a state event after an executed action
- **WHEN** the Game Service executes an action for a session and observes the resulting state
- **THEN** the Game Service SHALL emit a history event with actor `game-service` whose payload includes the resulting game-state representation and the game status (such as `in progress`, `win`, or `loss`)

#### Scenario: Emit a state event after loading a prebuilt deck
- **WHEN** the Game Service successfully loads a prebuilt deck into a session and observes the resulting state
- **THEN** the Game Service SHALL emit exactly one history event capturing the post-load game-state representation and status, carrying the replayable deck-load action so the event can be replayed forward during restore

#### Scenario: Emit a state event after loading a game state snapshot
- **WHEN** the Game Service successfully loads a game-state snapshot into a session and observes the resulting state
- **THEN** the Game Service SHALL emit exactly one history event capturing the loaded game-state representation and status

#### Scenario: Emit a state event after resetting a game
- **WHEN** the Game Service successfully resets a session's game and observes the resulting state
- **THEN** the Game Service SHALL emit exactly one history event capturing the post-reset game-state representation and status

#### Scenario: Read-only state observation does not emit
- **WHEN** the Game Service serves a read-only state observation or snapshot export without mutating the session
- **THEN** the Game Service SHALL NOT emit a game-state/status event

#### Scenario: Emitted event uses the session id as the game correlation id
- **WHEN** the Game Service emits a game-state/status event
- **THEN** the event SHALL carry the session identifier as its `game_id` correlation identifier

#### Scenario: Emission does not change game behavior
- **WHEN** the Game Service emits a game-state/status event for any state-mutating operation
- **THEN** the result returned to the original caller SHALL be unchanged by the emission, and any emission failure SHALL be swallowed without aborting or altering the operation

### Requirement: Snapshot-based restore entry point for history replay
The Game Service SHALL provide a snapshot-based restore entry point that the history-service can use to load a stored snapshot into a target session and then apply replayed actions forward, reusing the existing versioned snapshot import contract.

#### Scenario: Load a history-supplied snapshot into a target session
- **WHEN** the history-service loads a stored snapshot into a target Game Service session whose plugin identity matches the snapshot
- **THEN** the Game Service SHALL apply the snapshot and return the updated game state so that subsequent replayed actions can be applied forward

#### Scenario: Reject a snapshot with mismatched plugin identity during restore
- **WHEN** the history-service loads a snapshot whose plugin identity or schema version does not match the target session
- **THEN** the Game Service SHALL reject the load with a descriptive client error and SHALL NOT mutate the target session

#### Scenario: Apply replayed actions after snapshot load
- **WHEN** the history-service applies replayed game-mutating actions to a session after loading a snapshot
- **THEN** the Game Service SHALL execute those actions through its normal action execution path and reflect them in the session state

