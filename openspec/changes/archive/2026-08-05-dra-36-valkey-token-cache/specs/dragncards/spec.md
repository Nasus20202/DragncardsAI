## MODIFIED Requirements

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

## ADDED Requirements

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
