## MODIFIED Requirements

### Requirement: Identify a session by session id or room slug
The Game Service SHALL accept EITHER a session's UUID `session_id` OR its
human-readable DragnCards `room_slug` wherever an endpoint or MCP tool identifies a
session — state reads, mutations, and delete alike — resolving both forms through one
shared resolver.

The Game Service SHALL also keep a dedicated, non-mutating lookup
(`GET /games/by-slug/{room_slug}`, the `lookup_session_by_slug` MCP tool) that returns
a session's metadata including its canonical UUID `session_id`.

The room slug (`adjective-noun-NNNN`, roughly 27 bits and visible in DragnCards URLs)
is low-entropy and guessable, and the session endpoints are unauthenticated, so
accepting it on state, mutation, and delete paths is a knowingly accepted
access-control trade-off made for a local-development harness in favour of human and
agent readability. It is not a claim that the slug is unguessable.

#### Scenario: Address a session by its room slug
- **WHEN** a client supplies a session's `room_slug` in the `{session_id}` position of any state, mutation, or delete endpoint
- **THEN** the Game Service SHALL resolve the slug to that session and perform the operation exactly as if the canonical UUID `session_id` had been supplied

#### Scenario: Address a session by its UUID
- **WHEN** a client supplies a session's UUID `session_id` in the `{session_id}` position
- **THEN** the Game Service SHALL perform the operation on that session

#### Scenario: Non-canonical UUID still matches the stored session
- **WHEN** a client supplies a valid but non-canonical UUID `session_id` (e.g. uppercase or braced)
- **THEN** the Game Service SHALL normalize it to its canonical form (`str(uuid.UUID(value))`) so it matches the canonical id stored on the session

#### Scenario: Unresolvable identifier is reported as not found
- **WHEN** a client supplies an identifier that is neither a well-formed session id nor a room slug of any managed session
- **THEN** the Game Service SHALL fail with the not-found behavior (HTTP 404) and SHALL NOT create, modify, or destroy any session

#### Scenario: Room slug shared by more than one live session is rejected
- **WHEN** a client supplies a room slug that more than one live session is attached to
- **THEN** the Game Service SHALL refuse the request with a conflict error (HTTP 409) naming the candidate session ids, and SHALL NOT act on any of them

#### Scenario: Slug-addressed and UUID-addressed operations share one lock
- **WHEN** two concurrent operations address the same session, one by its room slug and one by its UUID `session_id`
- **THEN** the Game Service SHALL resolve both to the same canonical session id before deriving the session operation lock key, so the operations are serialized

#### Scenario: Resolve a session's metadata by its room slug
- **WHEN** a client supplies a session's DragnCards `room_slug` to `GET /games/by-slug/{room_slug}`
- **THEN** the Game Service SHALL return that session's metadata, including its canonical UUID `session_id`, without modifying any session

#### Scenario: Unknown room slug lookup is rejected as not found
- **WHEN** a client supplies a `room_slug` that does not correspond to any managed session
- **THEN** the lookup SHALL fail with the not-found behavior (HTTP 404) and SHALL NOT create, modify, or destroy any session

#### Scenario: Slug index is maintained across session lifecycle
- **WHEN** a session is created or attached and later deleted
- **THEN** the Game Service SHALL add a `room_slug -> session_id` mapping to the session store on creation and remove that mapping on deletion so slug resolution stays consistent

#### Scenario: Delete by a resolvable identifier is idempotent
- **WHEN** a client deletes a session by an identifier that resolves, but the session has already been removed (for example by the ephemeral reaper or a prior teardown)
- **THEN** the Game Service SHALL report success and SHALL return the canonical `session_id` rather than the raw identifier supplied

#### Scenario: MCP tool documentation describes both accepted forms
- **WHEN** an MCP client inspects the `session_id` parameter of any session-identifying tool
- **THEN** its description SHALL state that either the UUID `session_id` or the room slug is accepted, and SHALL NOT claim the parameter is UUID-only

#### Scenario: MCP tool documentation describes the slug lookup
- **WHEN** an MCP client inspects the `lookup_session_by_slug` tool
- **THEN** its description SHALL state that the tool reads a session's metadata (including the `session_id`) from a room slug, and that it is not a prerequisite for acting on a session
