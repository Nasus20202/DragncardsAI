# DragnCards Integration Contract Spec

## Purpose

This spec defines the integration contract between the Game Service and the DragnCards backend. It describes the external APIs, protocols, and behaviors that the Game Service depends on — written from the perspective of the Game Service as a client.

DragnCards is an Elixir/Phoenix application running as a Docker service. The Game Service treats it as a dependency and communicates with it via two interfaces: an HTTP REST API and a Phoenix Channels WebSocket connection.

## Requirements

### Requirement: HTTP authentication
The DragnCards backend SHALL expose an HTTP endpoint for session-based authentication that issues a bearer token usable for subsequent API and WebSocket calls.

The issued token SHALL remain valid for a bounded period after it is issued and SHALL be usable for any number of subsequent API and WebSocket calls within that period. In the pinned upstream (`pow` 1.0.27), `DragnCardsWeb.APIAuthPlug.create/3` stores the token in `Pow.Store.CredentialsCache`, which is declared with a 30-minute time to live, and DragnCards configures `:pow` without a `:ttl` override, so the default applies. `APIAuthPlug.fetch/2` reads the store without rewriting the entry, so the period runs from issue and is NOT extended by use.

Because a token is reusable, the Game Service SHALL NOT treat authentication as a per-room step. The call verifies a password hash rather than transferring a payload — measured at ~240 ms against a local backend, with the `GET /api/v1/profile` call that derives the user id from it at a further ~65 ms — so repeating it for every room is the dominant avoidable cost of creating one.

The validity period is upstream configuration this repository does not control, and the Game Service SHALL NOT assume a request bearing an expired token is rejected on this path. `POST /api/v1/games` is NOT behind the authenticated pipeline and SHALL be expected to create a room for any token, valid or not; the WebSocket endpoint likewise accepts a socket bearing an unusable token. The room channel is where a credential is judged: it answers the join with a room-unavailable push instead of a state, and that push is what the Game Service SHALL treat as the token having ceased to be valid.

#### Scenario: Successful authentication
- **WHEN** the Game Service sends `POST /api/v1/session` with `{"user": {"email": "<email>", "password": "<password>"}}`
- **THEN** the DragnCards backend SHALL respond with HTTP 200 and a JSON body containing `{"data": {"token": "<bearer-token>"}}`

#### Scenario: Failed authentication
- **WHEN** the Game Service sends `POST /api/v1/session` with invalid credentials
- **THEN** the DragnCards backend SHALL respond with a non-200 status code

#### Scenario: One token serves many room creations
- **WHEN** the Game Service creates several rooms within the token's validity period using the same token
- **THEN** the DragnCards backend SHALL accept each `POST /api/v1/games` request and SHALL NOT require a new authentication between them

#### Scenario: Room creation does not reject an unusable token
- **WHEN** the Game Service sends `POST /api/v1/games` bearing a token the backend does not recognise
- **THEN** the DragnCards backend SHALL still create the room and respond with success, so the Game Service SHALL NOT rely on this call to validate a credential

#### Scenario: The room channel refuses to serve state for an unusable token
- **WHEN** the Game Service opens a socket bearing a token the backend does not recognise and joins a room channel
- **THEN** the DragnCards backend SHALL accept the socket and the join, and SHALL push a room-unavailable event on that channel instead of the room's state

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

For a `draw_boost` action, the backend workflow SHALL mark the drawn encounter card as a boost while it is used during villain activation without making its identity visible to an unauthorized reader. When the DragnCards villain phase ends, the workflow SHALL identify every card whose authoritative engine state marks it as a boost, clear that transient marker and state, and move the card to the shared encounter discard before advancing to the next player phase. The workflow SHALL NOT select a card from a collapsed hidden count, a stack position, or an identity supplied by the caller, and SHALL NOT log or return the hidden card's name or identifier as part of cleanup.

#### Scenario: Submit a valid game action
- **WHEN** the Game Service pushes a `game_action` event on the room channel with a DragnLang payload `{"action": [...], "options": {"description": "..."}, "timestamp": <ms>`
- **THEN** the DragnCards backend SHALL apply the action to the game state and reply with `phx_reply` status `"ok"`

#### Scenario: State update broadcast after action
- **WHEN** a game action is applied
- **THEN** the DragnCards backend SHALL broadcast a `state_update` event on the room channel indicating the game state has changed

#### Scenario: Invalid or rejected action
- **WHEN** the Game Service pushes a `game_action` event that the DragnCards engine cannot apply
- **THEN** the DragnCards backend SHALL reply with `phx_reply` status `"error"` and a response payload describing the failure

#### Scenario: Draw boost remains hidden while active
- **WHEN** a valid `draw_boost` action moves an encounter card into a player's engaged zone for villain activation
- **THEN** the card SHALL remain represented to an unauthorized state reader only as a hidden count
- **AND** the engine SHALL retain an authoritative boost marker for the cleanup workflow

#### Scenario: Villain end phase authoritatively cleans boost cards
- **WHEN** the DragnCards villain end-phase action runs after one or more boost cards were drawn
- **THEN** every card with the engine's boost marker SHALL be moved to the shared encounter discard and have its boost marker, rotation, and transient tokens cleared before the next player phase begins
- **AND** the cleanup SHALL use the marked card records rather than a hidden count or stack position
- **AND** the action log and response SHALL NOT reveal a cleaned card's name or identifier

#### Scenario: Villain end phase tolerates an already-discarded boost
- **WHEN** a boost-marked card is already in the shared encounter discard when villain end phase runs
- **THEN** the workflow SHALL clear the stale boost marker and transient state without failing or selecting another card by position
- **AND** the action SHALL not reveal the card's identity

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

A plugin identity — `plugin_id`, `plugin_version` and `plugin_name` — SHALL be understood as naming a
row in DragnCards' own plugin table and therefore as a DragnCards concept only. It SHALL NOT be used
to identify, infer, or carry the platform a session plays on, because a platform that has no plugin
notion would have to be described by a fabricated plugin identity. The platform SHALL be carried by
its own explicit discriminator, as required by the `game-platform` capability.

#### Scenario: Marvel Champions plugin available
- **WHEN** the DragnCards backend is started with the Marvel Champions plugin volume mounted at `/plugin`
- **THEN** the plugin SHALL be registered and its `plugin_id` and `plugin_version` SHALL be known to the Game Service via environment-injected configuration

#### Scenario: Plugin loaded on room creation
- **WHEN** a room is created with a valid `plugin_id` and `plugin_version`
- **THEN** the DragnCards backend SHALL load the plugin into the room, and the initial `current_state` broadcast SHALL reflect an initialized game

#### Scenario: Plugin identity is not a platform discriminator
- **WHEN** a consumer needs to know which platform produced a session, an event, a snapshot, or an evaluation
- **THEN** it SHALL read the explicit platform discriminator
- **AND** SHALL NOT derive the platform from `plugin_name`, `plugin_id`, or `plugin_version`

### Requirement: Whole-state replacement by set_game
The DragnCards backend SHALL treat the `set_game` game action as a total replacement of the room's game document rather than a merge into it, so that the document supplied by the caller is the entire resulting state.

In the pinned upstream, `GameUI.resolve_action_type/4` implements `set_game` by returning `options["game"]`, discarding the room's prior game entirely. This is what makes loading a full-state base into an already-open room equivalent to loading it into a newly created one: no card, token, counter, or zone from the previous contents can survive the load.

This guarantee covers the `game` document only. Room-level fields the game document does not contain — notably the accumulated replay `deltas` and `replayStep` — are NOT reset by `set_game`, so a room that has had several states loaded into it carries a longer replay history than a fresh one while showing an identical board.

#### Scenario: A loaded state does not inherit the room's previous contents
- **WHEN** the Game Service loads a full-state document into a room that already holds a different game state
- **THEN** the resulting game document SHALL equal the loaded document, and SHALL be byte-for-byte identical to the result of loading that same document into a freshly created room

#### Scenario: Replay history is not reset by a state load
- **WHEN** a full-state document is loaded into a room
- **THEN** the room SHALL append a replay delta rather than discarding its existing ones, so the room's replay history reflects every load it has served

### Requirement: A seat is a slot in a room, not an authenticated identity
The integration contract with DragnCards SHALL record that a room's seats are the keys `player1` through `player4` of one seat map held in that room's server process, and that the seat an action acts as is taken from the action's own payload rather than from the identity of the connection that sent it.

The acting seat SHALL be understood to come from `options.player_ui.playerN` on the `game_action` event, which the backend grafts onto the game state and from which the `$PLAYER_N` variable — the value all player-scoped plugin automation branches on — resolves. The authenticated user carried by the websocket SHALL be understood to select the user's language, attribute a saved replay, and route a targeted GUI update, and SHALL NOT be understood to authorize, restrict, or determine the seat an action acts as.

The consequence the Game Service depends on SHALL be stated plainly: one authenticated connection can act as every seat of a room, and a multi-player game therefore requires no additional DragnCards account.

#### Scenario: One connection acts as two seats
- **WHEN** the Game Service, connected as a single authenticated user, pushes one action naming `player1` and another naming `player2`
- **THEN** the DragnCards backend SHALL apply each action to the named seat's cards and groups, regardless of which seat that user occupies

#### Scenario: An action that needs a seat and omits it fails
- **WHEN** the Game Service pushes an action whose DragnLang references `$PLAYER_N` and whose payload carries no `player_ui.playerN`
- **THEN** the DragnCards backend SHALL fail that action with `Variable $PLAYER_N is undefined` rather than choosing a seat on the caller's behalf

### Requirement: Seat occupancy governs how a seat is named in the game log
The DragnCards integration contract SHALL record that a DragnCards room's seat map supplies the alias by which a seat is named in the game log, and that a seat with no entry in that map is not merely unnamed but can be omitted from the log entirely.

DragnCards plugin automation reads a seat's alias out of the seat map and, where it guards a log line on that alias being defined, writes no line at all when the seat is unoccupied. Because the game log is what the history and evaluation pipelines consume, an unoccupied seat's actions can therefore be absent from the recorded game rather than merely anonymous.

This is a property of DragnCards' plugin automation and SHALL NOT be assumed of another platform, whose engine records a seat's actions without reference to any occupancy map.

#### Scenario: An occupied seat is named in the log
- **WHEN** a DragnCards action logs on behalf of a seat that holds a user in the room's seat map
- **THEN** the log line SHALL name that user's alias

#### Scenario: An unoccupied seat can be omitted from the log
- **WHEN** the end-of-player-phase automation runs for a DragnCards seat with no entry in the room's seat map
- **THEN** that seat's draw SHALL NOT appear in the game log, while an occupied seat's draw SHALL appear

#### Scenario: The omission is not assumed of another platform
- **WHEN** a consumer of recorded games reasons about a missing seat's actions
- **THEN** it SHALL apply this omission rule only to games whose platform is `dragncards`

### Requirement: Seat assignment is addressed by seat id
The DragnCards backend SHALL accept seat assignment on the room channel as a `set_seat` event whose `player_i` is a seat id — `player1` through `player4` — because that value is used directly as the key of the room's seat map.

The Game Service SHALL NOT send a numeric index for this field, as no numeric value names a seat and sending one writes an entry into the seat map that no seat lookup will ever find.

Because the backend's handling of this event returns no acknowledgement that distinguishes an applied assignment from a rejected one, the Game Service SHALL treat the room's subsequent state as the authority on whether a seat was taken.

#### Scenario: Assign a seat by its seat id
- **WHEN** the Game Service pushes `set_seat` with `player_i` set to `player2` and a user id
- **THEN** the DragnCards backend SHALL record that user in the second seat of the room's seat map

#### Scenario: Occupancy is confirmed from state, not from the push
- **WHEN** the Game Service needs to know whether a seat assignment took effect
- **THEN** it SHALL read the room's state and inspect the seat map, rather than inferring success from having sent the event

### Requirement: This contract describes one platform, not every platform

This capability SHALL be read as the integration contract for the DragnCards platform specifically:
what the DragnCards backend provides, and how the Game Service's DragnCards driver MUST use it. It
SHALL NOT be read as the contract every game platform satisfies, and a requirement stated here SHALL
NOT be taken to constrain another platform.

The cross-platform contract SHALL live in the `game-platform` capability, and every operation named
here SHALL be understood as the DragnCards driver's implementation of one of that protocol's
operations: authenticating, creating a table, attaching to an existing table, connecting, requesting
state, executing a move, assigning a seat, setting spectator visibility, and tearing down.

Consequently, the vocabulary this capability uses — Phoenix Channels, room slugs, room channels,
DragnLang action lists, plugin identity, `set_game`, `set_seat` — SHALL be understood as DragnCards
vocabulary. It SHALL NOT be required of, mapped onto, or fabricated for any other platform, and no
module above the DragnCards driver SHALL depend on it.

#### Scenario: A DragnCards fact is not applied to another platform
- **WHEN** a reader consults this capability for how a platform authenticates, creates a table, or executes a move
- **THEN** the answer SHALL apply only to sessions whose platform is `dragncards`
- **AND** the platform-neutral obligation SHALL be taken from the `game-platform` capability instead

#### Scenario: DragnCards vocabulary stays behind the DragnCards driver
- **WHEN** the Game Service's modules above the platform driver are inspected
- **THEN** none of them SHALL reference a Phoenix event name, a room channel topic, a DragnLang action list, or a plugin identifier
- **AND** every such reference SHALL live in the DragnCards driver or in this capability's own contract

#### Scenario: A second platform is not held to this contract
- **WHEN** a session whose platform is not `dragncards` is created and driven
- **THEN** no requirement of this capability SHALL be asserted against it
- **AND** its own platform capability SHALL be the contract that governs it
