# Game Service

## ADDED Requirements

### Requirement: A session carries its game platform

The Game Service SHALL accept an optional `platform` on session creation and on attachment, through
both HTTP and the derived MCP tools, SHALL store it on the session's metadata, and SHALL return it on
every response that describes a session. The permitted values SHALL be exactly `dragncards` and
`marvel-lcg`.

An omitted `platform` SHALL be recorded as `dragncards`, so that every existing caller, skill, test
and recorded session keeps its behaviour with no change to its request. A value outside the permitted
set SHALL be refused with HTTP 422 and SHALL NOT create, attach, or mutate anything.

The stored platform SHALL select the driver every subsequent operation on that session uses, and
SHALL NOT be changeable once the session exists. The Game Service SHALL NOT infer the platform from
the session's plugin identity: `plugin_id` and `plugin_name` name a DragnCards plugin and have no
meaning on marvel-lcg.

#### Scenario: Creating a session without a platform yields a DragnCards session
- **WHEN** a client sends `POST /games` with a plugin identifier and no `platform`
- **THEN** the created session's metadata SHALL report `platform` as `dragncards`
- **AND** the session SHALL be driven through the DragnCards driver exactly as before this capability existed

#### Scenario: Creating a marvel-lcg session
- **WHEN** a client sends `POST /games` with `platform` set to `marvel-lcg`
- **THEN** the Game Service SHALL create the table through the marvel-lcg driver
- **AND** the returned metadata SHALL report `platform` as `marvel-lcg`

#### Scenario: An unknown platform is refused
- **WHEN** a client sends `POST /games` with `platform` set to a value that is neither `dragncards` nor `marvel-lcg`
- **THEN** the Game Service SHALL respond `422` naming the `platform` field
- **AND** SHALL NOT create a table on either platform

#### Scenario: The platform is reported on every session-describing response
- **WHEN** a client sends `GET /games`, `GET /games/by-slug/{room_slug}`, or reads a single session's metadata
- **THEN** each described session SHALL carry its `platform` slug

#### Scenario: The platform of an existing session cannot be changed
- **WHEN** a client attempts to set a different `platform` on an existing session through any endpoint or tool
- **THEN** the request SHALL be refused and the session's stored platform SHALL remain as created

### Requirement: Group and layout vocabularies are resolved lazily per platform

The Game Service SHALL NOT read any platform's plugin metadata, group vocabulary, or layout
vocabulary while a module is being imported. The group and layout identifier vocabularies SHALL be
resolved per platform, on demand, at the point a caller needs them, so that the service imports,
starts, and serves its complete OpenAPI document with no platform's plugin JSON or card data present
on disk.

This is a prerequisite for marvel-lcg, which has no plugin, no group ids, and no layout ids at all.
It also removes the condition where the OpenAPI document — and therefore every MCP tool schema
derived from it — is a function of one platform's files existing at process start.

Making the resolution lazy SHALL NOT change the document served when the DragnCards plugin data is
present. The DragnCards operation identifiers, request schemas, response schemas, and derived MCP
tool schemas SHALL be identical before and after this change, and the existing tests that pin the MCP
tool set, the strict request bodies, and the capability list SHALL pass unmodified.

#### Scenario: The service starts and serves its document with no plugin data on disk
- **WHEN** the Game Service is started with no DragnCards plugin JSON, card database, or group metadata present
- **THEN** the service SHALL import successfully, answer its liveness probe, and serve a complete `GET /openapi.json`
- **AND** SHALL NOT raise during module import

#### Scenario: A vocabulary is read only when a caller needs one
- **WHEN** the Game Service is started and its OpenAPI document is fetched with no session created
- **THEN** no group or layout vocabulary SHALL have been loaded from disk

#### Scenario: The DragnCards tool schemas are unchanged
- **WHEN** the derived MCP tool schemas are generated with the DragnCards plugin data present
- **THEN** every DragnCards tool name and input schema SHALL be identical to the one produced before lazy resolution was introduced
- **AND** the tests that pin the MCP tool set, strict request bodies, and capability list SHALL pass without being edited

#### Scenario: A marvel-lcg session needs no group vocabulary
- **WHEN** a marvel-lcg session is created, its state is read, and a move is executed
- **THEN** no group or layout vocabulary SHALL be required for any of those operations

### Requirement: marvel-lcg sessions expose enumerated-option and catalog routes

The Game Service SHALL expose the marvel-lcg move surface as HTTP routes with stable operation
identifiers, from which the MCP tools are derived by operation identifier as they are for every other
route:

- `GET /games/{session_id}/options` with operation identifier `list_game_options` — the enumerated
  legal options pending for a seat.
- `POST /games/{session_id}/options/choose` with operation identifier `choose_game_option` — submit
  one option by its option id with its targets and resource payments.
- `GET /marvel-lcg/scenarios` with operation identifier `list_marvel_lcg_scenarios` — the scenarios
  that ship in the vendored engine.
- `GET /marvel-lcg/decks` with operation identifier `list_marvel_lcg_decks` — the prebuilt hero decks
  that ship in the vendored engine.

Every one of these request bodies SHALL inherit the service's strict request base, so a key the model
does not declare is refused with `422` naming the key rather than discarded. The option routes SHALL
be reachable only for a session whose platform offers enumerated options; called for a DragnCards
session they SHALL be refused with a descriptive conflict naming the session's platform, and SHALL
NOT be translated into DragnCards actions. The Game Service SHALL NOT expose any route, tool, or
proxy that reaches marvel-lcg's `/debug` endpoint.

#### Scenario: The option routes are exposed as MCP tools named by their operation identifier
- **WHEN** an MCP client lists the Game Service's tools
- **THEN** the tools `list_game_options` and `choose_game_option` SHALL be present
- **AND** each SHALL carry a JSON Schema that refuses arguments the endpoint does not take

#### Scenario: Listing options for a marvel-lcg seat
- **WHEN** a client sends `GET /games/{session_id}/options` for a marvel-lcg session and a seat that is being asked to decide
- **THEN** the Game Service SHALL return the enumerated legal options for that seat

#### Scenario: An option route on a DragnCards session is refused
- **WHEN** a client sends `GET /games/{session_id}/options` for a session whose platform is `dragncards`
- **THEN** the Game Service SHALL refuse the request with a conflict naming the session's platform and its typed action surface
- **AND** SHALL NOT return a fabricated option list

#### Scenario: The scenario and deck catalogs are read-only
- **WHEN** a client sends `GET /marvel-lcg/scenarios` or `GET /marvel-lcg/decks`
- **THEN** the Game Service SHALL return the listings sourced from the vendored engine
- **AND** SHALL NOT create, mutate, or destroy any session or table

#### Scenario: No route reaches the engine's debug endpoint
- **WHEN** the Game Service's OpenAPI document and MCP tool list are inspected
- **THEN** no route and no tool SHALL reach marvel-lcg's `/debug` endpoint
- **AND** the service SHALL never issue a request to that path

### Requirement: The DragnCards surface is unchanged by the platform seam

Introducing the platform seam SHALL NOT change any part of the DragnCards surface the Game Service
already exposes. Every existing route SHALL keep its path, method, operation identifier, request
schema and response schema; every derived MCP tool SHALL keep its name and input schema; the set of
routes excluded from MCP SHALL change only by the addition of the new routes' exclusions; and the 25
typed action helpers SHALL keep their parameter names and their emitted DragnLang.

The existing test suite SHALL pass unmodified across the refactor that introduces the driver protocol
with DragnCards as its only implementation, before the marvel-lcg driver is added. A diff in a
DragnCards route, tool name, or schema SHALL be treated as a regression, not as an update.

#### Scenario: The refactor is proven by the untouched suite
- **WHEN** the driver protocol is introduced with DragnCards as its only implementation
- **THEN** the existing unit and integration suites SHALL pass without any test being edited

#### Scenario: DragnCards route identity is preserved
- **WHEN** the OpenAPI document is compared against the document generated before the platform seam
- **THEN** every DragnCards route SHALL keep the same path, method, operation identifier, request schema, and response schema

#### Scenario: DragnCards MCP tool identity is preserved
- **WHEN** the derived MCP tool list is compared against the list generated before the platform seam
- **THEN** every DragnCards tool SHALL keep its name and input schema
- **AND** the only additions SHALL be the enumerated-option and marvel-lcg catalog tools

## MODIFIED Requirements

### Requirement: Room semantics are owned by one room Module
The Game Service SHALL concentrate table semantics behind one driver Module — the `GamePlatform`
protocol — whose Interface is used by HTTP adapters, MCP adapters, and session-pool orchestration.

That driver Module SHALL own state refresh, stale-state recovery, move execution, table control
operations, alert buffering, GUI update buffering, and table-side error handling. `GameSession` and
the session pool SHALL hold a driver rather than a concrete platform client, SHALL NOT construct any
platform's payloads, and SHALL NOT detect a platform error by matching text in that platform's game
log.

Platform protocol details — Phoenix event names, refs and payload construction for DragnCards;
render frames, form-encoded submissions and seat query parameters for marvel-lcg — SHALL live behind
a per-platform Adapter at the Seam and SHALL NOT be required knowledge for callers using table
behavior. Adding the second platform SHALL add an Adapter, and SHALL NOT add a branch above the Seam.

#### Scenario: HTTP and MCP adapters share table semantics
- **WHEN** a caller uses HTTP or MCP to observe state, execute a move, or invoke table control for the same session
- **THEN** both adapters SHALL delegate through the same driver Module Interface
- **AND** SHALL observe the same state-freshness, recovery, and table-side error semantics

#### Scenario: Phoenix protocol knowledge is hidden behind an Adapter
- **WHEN** table behavior requires Phoenix join refs, message refs, event names, or wire payloads
- **THEN** that knowledge SHALL be owned by the DragnCards Adapter behind the driver Module Seam
- **AND** SHALL NOT be duplicated in HTTP adapters, MCP adapters, or session-pool callers

#### Scenario: marvel-lcg protocol knowledge is hidden behind an Adapter
- **WHEN** table behavior requires render frames, seat query parameters, or form-encoded move submissions
- **THEN** that knowledge SHALL be owned by the marvel-lcg Adapter behind the same Seam
- **AND** SHALL NOT appear in any module above the Seam

#### Scenario: HTTP and MCP adapters share room semantics
- **WHEN** a caller uses HTTP or MCP to observe state, execute an action, or invoke room control for the same session
- **THEN** both adapters SHALL delegate through the same driver Module Interface
- **AND** SHALL observe the same state-freshness, recovery, and table-side error semantics

#### Scenario: The session holds a driver, not a platform client
- **WHEN** the session object and the session pool are inspected
- **THEN** neither SHALL be typed on a Phoenix client, channel, or room type, nor on any marvel-lcg client type
- **AND** neither SHALL contain a branch on the session's platform slug

#### Scenario: A platform error is reported by the driver, not grepped from the log
- **WHEN** a platform reports a failed move in its own game log or response
- **THEN** the driver SHALL return that failure through the protocol
- **AND** no module above the driver SHALL search game-log text for an error marker

### Requirement: Game state observation
The Game Service SHALL provide endpoints and MCP tools to query the current game state for a given session, returning one simplified representation whose shape does not depend on the session's platform.

State normalisation SHALL live below `GameSession`, in a per-platform normaliser selected by the session's platform, and SHALL NOT live in an HTTP router. No router, MCP adapter, or session-pool caller SHALL branch on a plugin name or a platform slug to decide how to shape state; the normaliser SHALL be reached through one polymorphic call.

Each normaliser SHALL be the only place its platform's vocabulary is converted. The simplified state SHALL carry the play-round number, an opaque platform-supplied phase label, and a neutral phase classification. DragnCards' `roundNumber` counts completed rounds and SHALL be converted to the play round by its own normaliser; marvel-lcg's round identifier is already the play round and SHALL NOT be converted. That conversion SHALL NOT be re-encoded by any consumer of the simplified state.

Each normaliser SHALL honour its platform's per-seat visibility model, so that a session sees exactly what the seats it holds would see, and hidden cards SHALL collapse to the existing hidden form.

#### Scenario: Get current game state via HTTP
- **WHEN** a client sends `GET /games/{id}/state`
- **THEN** the Game Service SHALL return the current game state including all card groups (hand, deck, play area, discard, etc.), card properties, player state, round/phase information, and any game counters

#### Scenario: Get simplified state for Marvel Champions via HTTP
- **WHEN** a client sends `GET /games/{id}/state` for a Marvel Champions session
- **THEN** the Game Service SHALL return the platform-neutral simplified representation, including the play round, phase, player state, and visible zones without exposing the platform's raw state vocabulary

#### Scenario: Get current game state via MCP
- **WHEN** an MCP client invokes the `get_game_state` tool with a session ID
- **THEN** the Game Service SHALL return the game state formatted as structured text suitable for LLM consumption, clearly describing the board state including card names, locations, and properties

#### Scenario: Get state for non-existent session
- **WHEN** a client requests state for an invalid session ID
- **THEN** the Game Service SHALL return a 404 error (HTTP) or an MCP error with a descriptive message

#### Scenario: State reflects latest game changes
- **WHEN** a move is executed on a session and then the state is queried
- **THEN** the returned state SHALL reflect the result of the most recent move, including any automated effects the platform's engine triggered

#### Scenario: Both platforms produce the same simplified shape
- **WHEN** a client sends `GET /games/{id}/state` for a DragnCards session and for a marvel-lcg session
- **THEN** both responses SHALL carry the same top-level fields, including the play-round number, the platform phase label, the neutral phase classification, the per-seat entries, and the zones
- **AND** a consumer SHALL read both without knowing which platform produced them

#### Scenario: Normalisation is one polymorphic call, not a plugin-name branch
- **WHEN** the state-serving path is inspected
- **THEN** it SHALL invoke one normaliser obtained from the session
- **AND** it SHALL contain no comparison against a plugin name or a platform slug

#### Scenario: The play round is converted once, by the platform's own normaliser
- **WHEN** a DragnCards session reports two completed rounds and a marvel-lcg session reports round identifier three
- **THEN** the DragnCards normaliser SHALL emit play round three and the marvel-lcg normaliser SHALL emit play round three
- **AND** no consumer of the simplified state SHALL apply a further adjustment

#### Scenario: Simplified state omits attachment hierarchy
- **WHEN** a client requests state for any session
- **THEN** the Game Service SHALL exclude cards that are attachments tucked under other cards from zone listings

#### Scenario: Another seat's hidden cards are not exposed
- **WHEN** a marvel-lcg session holds one seat and the platform's state carries cards visible only to another seat
- **THEN** the simplified state SHALL collapse those cards to the hidden form
- **AND** SHALL NOT reveal their names or identifiers

### Requirement: WebSocket connection to DragnCards
The Game Service SHALL maintain a persistent live connection to the platform for every session, using that platform's own protocol, and SHALL own connection liveness itself rather than delegating it to the platform.

For DragnCards the connection SHALL be a Phoenix Channels WebSocket. For marvel-lcg it SHALL be the engine's render-frame WebSocket, opened for the seats the session holds. The protocol-specific handshake, keep-alive, and reconnection mechanics SHALL live in that platform's driver, and the connection lifecycle a caller observes — established on session creation, degraded when it cannot be re-established — SHALL be identical for both.

#### Scenario: Establish connection on session creation
- **WHEN** a new game session is created
- **THEN** the Game Service SHALL open the platform's live connection, authenticate, and attach to the session's table before returning

#### Scenario: Handle connection loss
- **WHEN** a session's live connection to its platform is lost
- **THEN** the Game Service SHALL attempt to reconnect and re-attach to the table, and SHALL report the session as degraded if reconnection fails

#### Scenario: Phoenix heartbeat maintenance
- **WHEN** a DragnCards session's WebSocket connection is active
- **THEN** the Game Service SHALL send periodic heartbeat messages as required by the Phoenix Channels protocol to keep the connection alive

#### Scenario: The marvel-lcg socket is opened as part of bring-up
- **WHEN** a marvel-lcg session is created
- **THEN** the Game Service SHALL open the render-frame socket and complete the engine's connect handshake before reporting the session as ready
- **AND** SHALL NOT report the session as ready on table creation alone

### Requirement: Bad game state detection
The Game Service SHALL detect a platform's corrupted-or-unusable-state signal and surface it as an error on subsequent session operations, and SHALL do that detection inside the platform's driver rather than by inspecting platform-specific broadcasts above the driver.

For DragnCards the signal SHALL be the `bad_game_state` broadcast on the room channel. For marvel-lcg the signal SHALL be a state the driver cannot normalise or an engine that reports the game as ended while a move is pending. In both cases the driver SHALL raise the same error type, so callers behave identically.

#### Scenario: Bad state raises error on next operation
- **WHEN** a platform signals a corrupted or unusable state for a session
- **THEN** the next call to `get_state()` or move execution on that session SHALL raise a `BadGameStateError` with a descriptive message

#### Scenario: Bad state reflected in HTTP response
- **WHEN** a corrupted-state signal has been received for a session and a client sends `GET /games/{id}/state`
- **THEN** the Game Service SHALL return HTTP 409 with `{"detail": "game state is corrupted or unavailable"}`

#### Scenario: DragnCards signals it by broadcast
- **WHEN** the DragnCards backend broadcasts `bad_game_state` on a session's room channel
- **THEN** the DragnCards driver SHALL raise `BadGameStateError` on the next operation for that session

#### Scenario: marvel-lcg signals it through the driver
- **WHEN** a marvel-lcg session's world payload cannot be normalised
- **THEN** the marvel-lcg driver SHALL raise the same `BadGameStateError`
- **AND** the HTTP response SHALL be the same 409 a DragnCards session produces
