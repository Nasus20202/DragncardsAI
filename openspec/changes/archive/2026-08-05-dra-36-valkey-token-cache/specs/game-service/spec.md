## ADDED Requirements

### Requirement: Valkey-backed DragnCards credential cache

The Game Service SHALL resolve the DragnCards session token and the bot's numeric
user id through a cache held in Valkey, and SHALL NOT authenticate against
DragnCards once per room while a valid cached entry exists. The cache SHALL NOT be
held in process memory, so that every replica and every restart shares one entry.

Authenticating costs a password verification on the DragnCards side, not a payload
transfer: `POST /api/v1/session` was measured at ~240 ms and the `GET /api/v1/profile`
call that turns the token into a user id at ~65 ms, together over half of a ~590 ms
`POST /games`. The token is valid for 30 minutes, so re-deriving it for every room
is repeated work with no result that differs.

The token and the user id SHALL be stored as one entry. The id is a pure function
of the token, so storing them apart admits an entry holding one without the other.

The entry SHALL be keyed by the DragnCards backend URL and the configured account,
so that repointing the service at another backend or changing the account cannot
serve a credential minted for the previous one. The key SHALL NOT contain the
account address in clear text.

The entry's time to live SHALL be shorter than the token's own lifetime and SHALL
be configurable through `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS`, defaulting to 900
seconds against a 30-minute token lifetime. A value of `0` SHALL disable the cache
entirely and restore per-room authentication.

#### Scenario: A cached credential is reused instead of re-authenticated
- **WHEN** a session is created and a cached entry for the configured backend and account has not expired
- **THEN** the Game Service SHALL use the cached token and user id, and SHALL NOT send `POST /api/v1/session` or `GET /api/v1/profile` to DragnCards

#### Scenario: A cache miss authenticates live and populates the cache
- **WHEN** a session is created and no cached entry exists for the configured backend and account
- **THEN** the Game Service SHALL authenticate against DragnCards, read the user id, store both under the namespaced key with the configured time to live, and proceed with room creation

#### Scenario: Caching disabled by a zero time to live
- **WHEN** `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS` is `0`
- **THEN** the Game Service SHALL perform no Valkey read or write for credentials and SHALL authenticate against DragnCards for every room, exactly as it does with no cache configured

#### Scenario: A credential minted for another backend is not reused
- **WHEN** the configured DragnCards URL or account differs from the one a cached entry was stored under
- **THEN** the lookup SHALL miss and the Game Service SHALL authenticate against the currently configured backend

### Requirement: Credential cache failure degrades to live authentication

The Game Service SHALL NOT fail a session creation because of a Valkey miss,
outage, refused connection, reset connection, or malformed reply. It SHALL log the
failure without the cached value, treat it as a cache miss, and authenticate
against DragnCards directly.

The Game Service opens a fresh TCP connection per Valkey command, so a transport
error on any single command is a live possibility rather than a theoretical one; a
cache that turned one into a failed room creation would make the service less
reliable than it was before the cache existed.

#### Scenario: Valkey is unreachable when a session is created
- **WHEN** the Valkey instance is unreachable and a session is created
- **THEN** the Game Service SHALL authenticate against DragnCards, create the room, and return the session successfully

#### Scenario: A Valkey read fails mid-command
- **WHEN** reading the cached credential raises a transport error
- **THEN** the Game Service SHALL log a warning naming the key and the command but not the value, and SHALL proceed as though the entry were absent

#### Scenario: A Valkey write fails after a live authentication
- **WHEN** storing a freshly derived credential raises a transport error
- **THEN** the Game Service SHALL log a warning and SHALL still create the room with the credential it just derived

### Requirement: A credential the backend no longer recognises is evicted

The Game Service SHALL delete the cached entry when DragnCards declines to serve
a joined room's state and the credential used came from the cache, so that the
next room derives a new one rather than repeating the failure for the remainder of
the time to live. A credential that was derived live for that same attempt SHALL
NOT be evicted.

The room channel is where this is detected because it is the only place the
credential is judged on this path. Room creation is not authenticated upstream and
accepts any token, and the profile read that would reject one is the call the cache
exists to remove; a socket bearing an unusable token is also accepted, and the room
channel then answers the join with a room-unavailable push instead of a state.

A room-unavailable push has causes other than the credential — a room holding no
server state produces the same answer — so evicting a credential that was just
derived would re-derive an identical value and establish nothing.

The configured time to live is a prediction about a DragnCards deployment's
configuration, and one cause of it being wrong is routine: the deployment's
credential store does not survive the backend being recreated, so every issued
token can stop working while a cached entry still looks fresh.

#### Scenario: A cached credential the backend has forgotten is evicted
- **WHEN** a room join is answered with a room-unavailable push and the credential used came from the cache
- **THEN** the Game Service SHALL delete the cached entry, and the next session creation SHALL derive a new credential rather than reuse the evicted one

#### Scenario: A freshly derived credential is not evicted on the same failure
- **WHEN** a room join is answered with a room-unavailable push and the credential used was derived live for that attempt
- **THEN** the Game Service SHALL leave the cache entry in place, because re-deriving would produce the same credential and the cause lies elsewhere

#### Scenario: A refused join still returns a session
- **WHEN** a room join is answered with a room-unavailable push
- **THEN** the Game Service SHALL return the session, which fetches state on demand, and SHALL NOT fail the request — raising would strand the room just created, whose channel refuses the push that closes a room

### Requirement: A joined channel does not miss the room's opening broadcasts

The Game Service SHALL register a channel handle before awaiting its join reply,
so that broadcasts arriving with the join are delivered rather than discarded.

The receive loop runs independently of the coroutine performing the join, so it
can deliver the room's opening messages before that coroutine is rescheduled to
register the channel — and a message whose topic is not yet registered is dropped
without a trace. Both the state broadcast the join itself triggers and the
room-unavailable push that replaces it fall in that window, so the eviction above
cannot be observed reliably without this.

#### Scenario: The join's own state broadcast is delivered
- **WHEN** a channel is joined and DragnCards pushes the room's full state immediately after replying
- **THEN** the Game Service SHALL receive that state on the returned channel

#### Scenario: A failed join leaves no channel registered
- **WHEN** a channel join is rejected or raises
- **THEN** the Game Service SHALL NOT leave a handle registered for that topic

### Requirement: The cached credential never leaves the cache value

The DragnCards token SHALL appear only in the cache entry's value and in the
`authorization` header of DragnCards requests. It SHALL NOT be written to a log
record, attached to a span attribute, included in an error message or exception
text, or written into any specification, README, or example.

Caching a credential widens the set of places it can escape from, and the usual
escape is diagnostics: an upstream rejection body echoed into an exception message
reaches the logs and, from there, the traces.

#### Scenario: Cache diagnostics name the key, not the value
- **WHEN** a credential cache command fails and is logged
- **THEN** the log record SHALL contain the key and the command name and SHALL NOT contain the token

#### Scenario: Spans carry no credential
- **WHEN** a credential cache command is traced
- **THEN** the span SHALL carry only the operation name, server address, and port, and SHALL NOT carry any command argument

#### Scenario: Authentication failures report status, not credentials
- **WHEN** DragnCards rejects a credential and the Game Service raises an error
- **THEN** the error message SHALL identify the status code and the request path and SHALL NOT contain the token, the password, or the upstream response body
