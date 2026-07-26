## ADDED Requirements

### Requirement: Validated game_id at the route boundary
The history-service SHALL validate the `game_id` path parameter on every game-scoped route (events backfill/listing, snapshots listing, restore, and game deletion) against a strict pattern (`^[A-Za-z0-9_-]{1,64}$`) and SHALL reject a malformed, oversized, or encoded-traversal `game_id` before any database access or outbound service call. Validation SHALL NOT alter the existing idempotent semantics for a well-formed but absent `game_id`.

#### Scenario: Reject a malformed game_id
- **WHEN** a request targets a game-scoped route with a `game_id` that violates the allowed pattern (e.g. contains a dot, space, slash, encoded slash, or exceeds 64 characters)
- **THEN** the history-service SHALL reject the request before any database or outbound call, returning a validation error (422) or, for a path that cannot match the single-segment route, a route miss (404)

#### Scenario: Well-formed unknown game_id keeps idempotent delete
- **WHEN** a delete is requested for a well-formed `game_id` that has no stored history
- **THEN** the history-service SHALL return success with zero deleted events and snapshots

### Requirement: URL-encoded outbound service-call path parameters
The history-service SHALL construct outbound game-service request URLs by percent-encoding each path segment (e.g. via `httpx.URL` / `urllib.parse.quote`) rather than by raw f-string interpolation, so a crafted `game_id` or action suffix cannot inject additional path segments or traversal against the trusted internal API.

#### Scenario: Encode an id containing path-significant characters
- **WHEN** the history-service issues a game-service request for a `game_id` that contains slash or traversal characters
- **THEN** those characters SHALL be percent-encoded within a single path segment and SHALL NOT introduce extra path segments in the request

### Requirement: Allowlisted replay action_path
The history-service SHALL constrain the `action_path` read from a stored event payload to the known replay-endpoint shape (the generic `actions` endpoint, an `actions/<action_name>` suffix, or a single legacy `<action_name>` segment) before forwarding a replay, and SHALL reject any other value with a clear error instead of forwarding an arbitrary path.

#### Scenario: Reject a disallowed action_path
- **WHEN** a stored event payload carries an `action_path` that does not match the allowed replay-endpoint shape (e.g. contains traversal, extra segments, a scheme, or query characters)
- **THEN** the history-service SHALL raise an error and SHALL NOT forward any request to the game-service

#### Scenario: Forward an allowed action_path
- **WHEN** a stored event payload carries `actions` or `actions/<action_name>`
- **THEN** the history-service SHALL forward the replay to the corresponding game-service endpoint with each path segment percent-encoded
