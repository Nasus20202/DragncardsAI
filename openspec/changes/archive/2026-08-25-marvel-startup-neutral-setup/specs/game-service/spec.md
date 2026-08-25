## ADDED Requirements

### Requirement: Game setup is discovered through a neutral typed catalog

The Game Service SHALL expose a read-only `GET /games/setup-catalog` route with operation
identifier `list_game_setup_catalog`, and the generated MCP tool SHALL have the same operation
identifier. It SHALL accept an optional `platform` selector defaulting to `dragncards` and SHALL
return a typed catalog discriminated by `platform` and carrying `move_surface`.

The catalog SHALL expose opaque, platform-owned setup ids. A marvel-lcg catalog SHALL include
scenario entries and hero-deck entries, each with an `id` and human-readable metadata. A caller
SHALL use the returned ids in `create_game`; it SHALL not construct engine paths, choose by array
position, or use a display name as an identifier. Catalog reads SHALL not create or mutate a game.

#### Scenario: A backend-neutral caller discovers Marvel setup

- **WHEN** an MCP client invokes `list_game_setup_catalog` with `platform: marvel-lcg`
- **THEN** the result SHALL identify `platform: marvel-lcg` and
  `move_surface: enumerated_options`
- **AND** it SHALL list selectable scenario and hero-deck ids
- **AND** the client SHALL not need to call a Marvel-specific route to discover setup

#### Scenario: Catalog discovery defaults compatibly

- **WHEN** a legacy caller invokes `list_game_setup_catalog` without a platform
- **THEN** the service SHALL return the DragnCards catalog using the existing default platform
- **AND** an explicit Marvel caller SHALL receive the Marvel catalog when it supplies
  `platform: marvel-lcg`

#### Scenario: Catalog reads are side-effect free

- **WHEN** a caller reads setup catalogs repeatedly
- **THEN** no session, table, lease, or game state SHALL be created or mutated

### Requirement: Create game accepts optional typed setup

`create_game` SHALL accept an optional platform-discriminated typed setup specification in the
`setup` field. The marvel-lcg variant SHALL contain one `scenario_id` and an ordered non-empty
`hero_decks` list, where each entry contains one neutral `seat` and one `hero_deck_id`. The roster
SHALL be the exact contiguous prefix `player1` through `playerN`; reverse or gapped rosters SHALL
be rejected. The service SHALL preserve the list order, validate every id against a fresh catalog
read, and return the resolved setup selection in typed `SessionMetadata.setup`.

When setup is omitted, existing DragnCards requests SHALL retain their behavior. Marvel-lcg SHALL
use an explicitly configured legacy default only when every default id validates against the live
catalog. If no valid configured default exists, the service SHALL refuse creation with an
actionable error naming `list_game_setup_catalog`, `scenario_id`, and the ordered player entries.
The service SHALL never select the first scenario or deck in a catalog as an invisible fallback.

#### Scenario: The requested Marvel heroes are created in order

- **WHEN** a caller supplies a Marvel setup with scenario `S` and ordered hero decks
  `[{seat: player1, hero_deck_id: H1}, {seat: player2, hero_deck_id: H2}]`
- **THEN** the engine SHALL receive the document for `S` and hero documents for `H1`, then `H2`
- **AND** the returned session metadata SHALL report those same ordered selections

#### Scenario: A non-contiguous roster is rejected

- **WHEN** a caller supplies reverse or gapped seats such as `[player2, player1]` or
  `[player1, player3]`
- **THEN** the service SHALL reject the request before engine creation
- **AND** it SHALL not reorder the hero decks or silently fill the gap

#### Scenario: Omitted setup preserves a safe legacy default

- **WHEN** a legacy Marvel caller omits setup and the configured scenario and hero-deck defaults
  are present in the current catalog
- **THEN** creation SHALL use those defaults
- **AND** the response SHALL expose the resolved scenario and ordered hero-deck selections

#### Scenario: Missing defaults do not choose the first catalog entry

- **WHEN** a Marvel caller omits setup and no valid configured defaults exist
- **THEN** creation SHALL fail before the engine creates a game
- **AND** the error SHALL direct the caller to discover and supply the typed setup

#### Scenario: Invalid setup never creates a game

- **WHEN** a caller supplies an unknown scenario id, unknown hero-deck id, duplicate seat, or
  unsupported seat
- **THEN** the service SHALL reject the request before engine creation
- **AND** SHALL not replace the invalid selection with a catalog default

### Requirement: Session responses advertise platform capabilities

Every response that describes a game session, including create, attach, list, lookup, and state
responses, SHALL carry `platform` and `move_surface`. The session action catalog SHALL carry the
same values and SHALL advertise only operations belonging to that surface. These fields SHALL be
machine-readable and SHALL not require a caller to inspect plugin metadata or tool names.

#### Scenario: Marvel metadata is explicit on creation

- **WHEN** a caller creates a marvel-lcg session
- **THEN** the response SHALL contain `platform: marvel-lcg` and
  `move_surface: enumerated_options`

#### Scenario: DragnCards metadata is explicit by default

- **WHEN** a legacy caller creates a session without a platform
- **THEN** the response SHALL contain `platform: dragncards` and
  `move_surface: typed_actions`

#### Scenario: The action catalog follows metadata

- **WHEN** a caller reads actions for a Marvel session
- **THEN** the catalog SHALL expose enumerated-option operations and SHALL omit typed DragnCards
  helpers
- **AND** a DragnCards catalog SHALL retain its typed helpers and omit enumerated-option operations

### Requirement: Marvel singleton attachment is rejected safely

The Game Service SHALL treat the marvel-lcg engine as a singleton endpoint owned by one active
session lease. It SHALL acquire the lease before creation, renew it while the session is live, and
release it on teardown. A second claimant SHALL receive a conflict without an engine create call.

The `attach_game` operation SHALL reject `platform: marvel-lcg` because the engine has no stable
external room identifier. A service-generated Marvel room slug SHALL be treated as local metadata
only and SHALL never select an engine game after restart.

The generic `close_room` operation SHALL also reject `platform: marvel-lcg` before sending a
DragnCards room event or invoking session removal. Deleting the session SHALL remain the supported
full teardown path and SHALL close the render transport and release the singleton lease.

#### Scenario: A second Marvel creation is refused

- **WHEN** a Marvel session already owns the engine lease and another caller invokes `create_game`
  for Marvel
- **THEN** the second call SHALL return a conflict naming the active singleton constraint
- **AND** the engine SHALL receive no second table-creation request

#### Scenario: Marvel attachment does not guess the active game

- **WHEN** a caller invokes `attach_game` for a Marvel room slug
- **THEN** the service SHALL return an unsupported-attachment error
- **AND** no render socket or move connection SHALL be opened for an unowned game

#### Scenario: Marvel close-room does not orphan a live session

- **WHEN** a caller invokes `close_room` for a Marvel session
- **THEN** the service SHALL return an unsupported-operation error before sending a room event
- **AND** it SHALL keep the session transport and singleton lease unchanged
