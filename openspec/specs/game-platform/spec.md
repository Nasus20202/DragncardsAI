# game-platform Specification

## Purpose
The game-platform capability provides one platform-neutral driver contract so session orchestration
can create, drive, observe, and tear down games without depending on a platform's wire protocol.

## Requirements

### Requirement: A game platform is driven through one driver protocol

The system SHALL define a single `GamePlatform` driver protocol that covers the whole of a game
platform's externally observable surface, and every platform SHALL be driven only through it. The
protocol SHALL cover, at minimum: authenticating against the platform, creating a table, attaching
to an existing table, connecting to the table's live channel, requesting the table's current state,
executing a move, assigning a seat, setting spectator visibility, and tearing the attachment down.

A caller of the protocol — the session object, the HTTP routers, the MCP surface, the history
emitter and the snapshot path — SHALL NOT name, import, or type itself on any platform's concrete
transport types, wire event names, payload shapes, or log-message text. Every such detail SHALL live
behind the driver for that platform. A platform-specific behaviour that the protocol does not
express SHALL be added to the protocol rather than reached around by a caller inspecting the driver's
type.

Exactly two implementations SHALL exist: one for DragnCards and one for marvel-lcg. The protocol
SHALL NOT be widened into a discovery or plugin-registration mechanism for further platforms.

#### Scenario: A session drives a platform without naming its transport
- **WHEN** the session layer creates a table, requests state, executes a move and tears the session down
- **THEN** every one of those calls SHALL go through the `GamePlatform` protocol
- **AND** no module above the driver SHALL reference a Phoenix channel, a Phoenix event name, a render-frame socket, or any other platform transport type

#### Scenario: Both platforms satisfy the same protocol
- **WHEN** the driver implementations for `dragncards` and `marvel-lcg` are inspected
- **THEN** each SHALL implement every operation the protocol declares
- **AND** an operation a platform cannot perform SHALL be refused by that driver with a descriptive error rather than left undefined

#### Scenario: Platform failure signals are surfaced by the driver
- **WHEN** a platform reports a table-level failure in its own vocabulary, such as a corrupted-state broadcast or an unstartable engine
- **THEN** the driver SHALL translate it into the protocol's failure result
- **AND** no caller above the driver SHALL detect that failure by matching platform log text

### Requirement: Every session declares the platform it plays on

Every game session SHALL carry a `platform` slug on its metadata, and that slug SHALL be one of
exactly `dragncards` or `marvel-lcg`. A session-creating or session-attaching request that omits the
slug SHALL be treated as `dragncards`, so that every caller written before this capability keeps its
existing behaviour without change. A request naming any other value SHALL be refused as a bad
request and SHALL NOT create or attach anything.

The slug SHALL be fixed for the life of the session: no endpoint, tool, or internal path SHALL
change the platform of an existing session. The slug SHALL be present on every response that returns
session metadata, including the session list and the slug-based lookup.

#### Scenario: A session created without a platform is a DragnCards session
- **WHEN** a client creates a session and supplies no `platform`
- **THEN** the created session SHALL carry `platform` equal to `dragncards`
- **AND** the session SHALL behave exactly as it did before this capability existed

#### Scenario: A session created for marvel-lcg carries that platform
- **WHEN** a client creates a session supplying `platform` equal to `marvel-lcg`
- **THEN** the created session SHALL carry `platform` equal to `marvel-lcg`
- **AND** every subsequent operation on that session SHALL be routed to the marvel-lcg driver

#### Scenario: An unknown platform is refused
- **WHEN** a client creates or attaches a session supplying a `platform` that is neither `dragncards` nor `marvel-lcg`
- **THEN** the request SHALL be refused as a bad request naming the offending value
- **AND** no table SHALL be created and no session SHALL be stored

#### Scenario: The platform is reported wherever a session is described
- **WHEN** a client lists sessions or looks a session up by its table identifier
- **THEN** each returned session SHALL carry its `platform` slug

### Requirement: Every recorded datum is attributed to the platform that produced it

Every service that records data derived from a game SHALL attribute that data to a platform. The
`platform` slug SHALL be carried on each history event and snapshot, on each evaluation request and
evaluated target, in the export-bundle header, and on each game row the dashboard lists. It SHALL be
a stored, queryable field rather than an incidental key inside an opaque payload.

Where a stored identity today keys on the game identifier alone — a uniqueness constraint, an
ordering series, an advisory lock, or an idempotency digest — the platform SHALL be joined into that
identity, so that two platforms can never collide on one game identifier and so that a per-platform
listing is answerable without reading payloads.

A record that carries no platform SHALL be read as `dragncards`. This SHALL hold for rows written
before this capability existed, for an export bundle written before it existed, and for a producer
that has not yet been updated, so that no backfill and no coordinated restart is required.

#### Scenario: A recorded event carries its platform
- **WHEN** a game-state event is recorded for a marvel-lcg session
- **THEN** the stored event SHALL carry `platform` equal to `marvel-lcg` as a queryable field
- **AND** an event recorded for a DragnCards session SHALL carry `platform` equal to `dragncards`

#### Scenario: A record written before this capability reads as DragnCards
- **WHEN** a record, envelope, or export bundle that carries no `platform` is read
- **THEN** the reader SHALL treat its platform as `dragncards`
- **AND** SHALL NOT reject the record for the missing field

#### Scenario: Two platforms do not collide on one game identifier
- **WHEN** two sessions on different platforms are recorded under the same game identifier
- **THEN** each platform's events, snapshots, and evaluations SHALL remain separately addressable
- **AND** neither SHALL be rejected as a duplicate of the other

#### Scenario: Recorded data is listable per platform
- **WHEN** a client lists recorded games filtered by a platform
- **THEN** the response SHALL contain only games recorded for that platform
- **AND** the filter SHALL be answered from the stored field rather than by inspecting payloads

### Requirement: The service imports and serves its API document with no platform data on disk

The game-service SHALL import, start, and serve its complete OpenAPI document without any platform's
card database, plugin metadata, group vocabulary, or layout vocabulary being present on disk. Group
and layout vocabularies SHALL be resolved per platform and only at the moment a caller needs them,
and SHALL NOT be read while a module is being imported.

This is required because marvel-lcg has no plugin, no group ids, and no layout ids at all, and
because a document — and therefore every derived MCP tool schema — that is a function of one
platform's files on disk cannot describe a second platform.

Resolving the vocabularies lazily SHALL NOT change the document that is served when a platform's
data *is* present. The DragnCards request schemas, response schemas, operation identifiers, and
derived MCP tool schemas SHALL be identical before and after this change; any difference SHALL be
treated as a regression rather than as an update.

#### Scenario: The service starts with no plugin data present
- **WHEN** the game-service is started with no plugin JSON, card database, or group metadata on disk
- **THEN** the service SHALL import successfully, answer its liveness probe, and serve its complete OpenAPI document
- **AND** SHALL NOT raise during module import

#### Scenario: A vocabulary is read only when a caller needs it
- **WHEN** the service is started and its OpenAPI document is requested, with no session created
- **THEN** no platform's group or layout vocabulary SHALL have been read from disk

#### Scenario: The DragnCards schemas are byte-identical
- **WHEN** the OpenAPI document and derived MCP tool schemas are generated with the DragnCards plugin data present, before and after lazy resolution is introduced
- **THEN** the DragnCards operation identifiers, request schemas, response schemas, and tool schemas SHALL be identical
- **AND** any difference SHALL fail the build

### Requirement: Seats are the neutral identifiers player1 through player4

The neutral seat vocabulary SHALL be exactly the identifiers `player1`, `player2`, `player3` and
`player4`, and every surface above the driver — session metadata, HTTP and MCP parameters, the
simplified game state, recorded events, evaluation rows, skills, and the dashboard — SHALL use only
those identifiers. A value outside that set SHALL be refused as a bad request.

Each driver SHALL map the neutral identifier onto its platform's own seat addressing at the
transport edge, and that mapping SHALL be the only place the platform's form appears. For DragnCards
the identifier SHALL be used as the seat key directly. For marvel-lcg the identifier `playerN` SHALL
be mapped to the zero-based seat `N-1`.

A driver SHALL occupy exactly the seats it was asked to occupy, and SHALL NOT use a platform
facility that collapses all seats into one client, because doing so would defeat the per-seat
visibility the system depends on for fair play.

#### Scenario: A neutral seat is mapped to a zero-based platform seat
- **WHEN** an operation for seat `player2` is executed on a marvel-lcg session
- **THEN** the driver SHALL address the platform's seat `1`
- **AND** the neutral identifier `player2` SHALL be what every surface above the driver records and reports

#### Scenario: A DragnCards seat identifier is passed through unchanged
- **WHEN** an operation for seat `player2` is executed on a DragnCards session
- **THEN** the driver SHALL use `player2` directly as the platform's seat key

#### Scenario: A seat outside the neutral set is refused
- **WHEN** a caller supplies a seat that is not one of `player1` through `player4`, including a bare numeric index
- **THEN** the request SHALL be refused as a bad request
- **AND** nothing SHALL be sent to the platform

#### Scenario: Another seat's hidden information is never read
- **WHEN** a session holds one seat and the platform's state carries cards visible only to another seat
- **THEN** the state the session exposes SHALL omit or collapse those cards exactly as that seat's human player would see them

### Requirement: A platform's move surface is declared, not assumed

Each platform SHALL declare which move surface it offers, and the system SHALL NOT require the two
platforms to offer the same one. A platform that accepts composed actions SHALL offer the typed
action surface; a platform whose engine adjudicates the rules and enumerates the legal move set
SHALL offer the enumerated-option surface. Neither surface SHALL be synthesised on a platform that
does not natively provide it.

An operation belonging to a surface the session's platform does not offer SHALL be refused with an
error naming the session's platform and the surface that platform does offer, and SHALL NOT be
translated, approximated, or silently ignored. A session's action catalog SHALL advertise only the
surface its platform offers.

#### Scenario: A typed action on an enumerating platform is refused
- **WHEN** a caller submits a typed composed action for a session whose platform offers only enumerated options
- **THEN** the request SHALL be refused with an error naming the session's platform and the enumerated-option surface
- **AND** no move SHALL be sent to the platform

#### Scenario: An enumerated-option call on a composing platform is refused
- **WHEN** a caller lists or chooses enumerated options for a session whose platform offers only typed composed actions
- **THEN** the request SHALL be refused with an error naming the session's platform and the typed action surface
- **AND** the service SHALL NOT fabricate an option list

#### Scenario: The catalog advertises only the platform's own surface
- **WHEN** a client reads the action catalog for a session
- **THEN** the catalog SHALL list only the move surface that session's platform offers

### Requirement: Platform creation uses a typed platform-owned specification

The `GamePlatform` protocol SHALL accept a typed, platform-discriminated create specification
rather than an untyped mapping named `plugin_info`. The specification SHALL have exactly one
variant for each supported platform. The DragnCards variant SHALL carry its plugin selection; the
marvel-lcg variant SHALL carry a `scenario_id` and an ordered non-empty contiguous prefix of
neutral `player1`..`playerN` seat and `hero_deck_id` pairs.

The API boundary SHALL validate the discriminator, required fields, neutral seat vocabulary,
contiguous roster order, duplicate seats, and catalog membership before invoking a driver. A driver SHALL not silently
discard fields belonging to another platform, infer a platform from plugin metadata, or replace an
invalid requested identifier with another catalog entry.

#### Scenario: A Marvel create spec reaches the Marvel driver typed

- **WHEN** a caller creates a marvel-lcg game with a scenario id and ordered seat/deck pairs from
  the setup catalog
- **THEN** game-service SHALL pass a marvel-lcg create-spec object to the Marvel driver
- **AND** the driver SHALL preserve the pair order when resolving hero documents
- **AND** no `plugin_info` mapping SHALL be used as the cross-platform contract

#### Scenario: A setup discriminator cannot select another platform

- **WHEN** a create request names `platform: marvel-lcg` but supplies a DragnCards create spec
- **THEN** the request SHALL be refused before either backend is called
- **AND** the error SHALL identify the mismatched platform discriminator

#### Scenario: Duplicate or unknown setup selections are rejected

- **WHEN** a create request repeats a seat, uses a seat outside `player1` through `player4`, or
  names a scenario/deck id absent from the selected platform catalog
- **THEN** the request SHALL be refused before table creation
- **AND** no different catalog entry SHALL be substituted

### Requirement: Platform capability metadata is explicit

Each platform driver SHALL declare a stable `platform` slug and exactly one `move_surface` slug.
The supported move surfaces SHALL be `typed_actions` for DragnCards and `enumerated_options` for
marvel-lcg. The capability declaration SHALL be available without creating a game and SHALL be
carried on every session metadata response and session action catalog.

#### Scenario: DragnCards declares its typed surface

- **WHEN** a caller reads the DragnCards platform capability
- **THEN** the response SHALL contain `platform: dragncards` and
  `move_surface: typed_actions`

#### Scenario: Marvel declares its enumerated surface

- **WHEN** a caller reads the marvel-lcg platform capability
- **THEN** the response SHALL contain `platform: marvel-lcg` and
  `move_surface: enumerated_options`

#### Scenario: Capability metadata does not imply cross-surface translation

- **WHEN** a caller uses a move operation not offered by the session's declared move surface
- **THEN** the driver SHALL refuse it with the platform and offered surface
- **AND** SHALL not translate or partially execute the request

### Requirement: Singleton platforms expose ownership constraints

A platform driver whose engine supports one active game SHALL declare that ownership constraint to
the session manager. The manager SHALL acquire and renew one distributed lease per engine endpoint
before creating or mutating a session, and SHALL release it during teardown. A lost lease SHALL
fence subsequent mutating operations and mark the session degraded.

#### Scenario: A second Marvel session cannot claim the engine

- **WHEN** a second session requests a Marvel table while the endpoint lease belongs to another
  active session
- **THEN** creation SHALL be rejected with a conflict naming the singleton constraint
- **AND** the second session SHALL not send a create request to the engine

#### Scenario: Lease loss prevents unowned mutation

- **WHEN** a Marvel session cannot renew its endpoint lease
- **THEN** the session SHALL become degraded
- **AND** subsequent moves SHALL be refused until a new owned session is created

#### Scenario: Unsupported singleton attachment is explicit

- **WHEN** a caller attempts to attach a Marvel session using a service-generated slug
- **THEN** the driver SHALL refuse the attachment as unsupported
- **AND** SHALL not attach to whichever singleton game happens to be active
