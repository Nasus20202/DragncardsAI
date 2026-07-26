## ADDED Requirements

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
