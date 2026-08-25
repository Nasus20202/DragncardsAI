## MODIFIED Requirements

### Requirement: Game creation embeds document content, not file paths

marvel-lcg SHALL create a game entirely over HTTP through `GET /new?data=<NewGameDescriptor>`,
where the descriptor contains stringified scenario and hero-deck document content. The
game-service driver SHALL accept only scenario and hero-deck ids returned by the neutral setup
catalog, resolve those ids to document content immediately before creation, and preserve the
ordered `hero_decks` list when constructing `hero_json`.

The driver SHALL not accept a display name, an arbitrary filesystem path, a MarvelCDB import, or an
untyped `plugin_info` mapping as an alternative setup identity. If a selected id is no longer in
the live catalog, creation SHALL fail rather than selecting another entry.

#### Scenario: Selected catalog ids become document content

- **WHEN** a caller selects one listed scenario id and two listed hero-deck ids in seat order
- **THEN** the driver SHALL fetch the corresponding scenario and deck documents
- **AND** SHALL send those document texts in the descriptor in the same order

#### Scenario: A solo game is created from fetched document content

- **WHEN** our client creates a solo game from one listed scenario id and one listed hero-deck id
- **THEN** it SHALL fetch both document contents before calling `GET /new`
- **AND** it SHALL send the scenario text as `campaign_json` and a one-item ordered `hero_json`
  list
- **AND** the engine SHALL answer `200` with `{"result": "New game created"}`

#### Scenario: A descriptor carrying a path instead of content is a client defect

- **WHEN** a descriptor is constructed with a filesystem path rather than fetched document text
- **THEN** the client SHALL fail that construction before sending it
- **AND** it SHALL not rely on the engine to interpret the path

#### Scenario: An invalid descriptor is reported by status

- **WHEN** the engine rejects a descriptor
- **THEN** it SHALL answer `400` with an `error` field, or `409` when campaign progression
  conflicts
- **AND** the client SHALL surface that status as a creation failure rather than retrying blindly

#### Scenario: Only vendored decks and scenarios are used

- **WHEN** the client lists setup data for a game
- **THEN** the listings SHALL come from the vendored engine's scenario and starter-deck catalog
- **AND** the client SHALL not call a MarvelCDB import or sync path

#### Scenario: A stale catalog id is rejected

- **WHEN** a caller submits an id that was listed earlier but is absent during creation
- **THEN** the driver SHALL report that id as unavailable
- **AND** SHALL not send a descriptor containing a different scenario or deck

#### Scenario: A path or display name is not a setup identity

- **WHEN** a caller supplies an engine path or display name instead of a catalog id
- **THEN** the game-service SHALL refuse the request before `GET /new`
- **AND** SHALL direct the caller to `list_game_setup_catalog`

## ADDED Requirements

### Requirement: The vendored Marvel engine has one active game owner

The marvel-lcg driver SHALL declare that one configured engine endpoint supports one active game.
Game-service SHALL own a distributed lease for that endpoint and SHALL not create a second game or
attach an arbitrary session while the lease is held. The driver SHALL not claim that a
service-generated slug is an engine table identifier.

#### Scenario: The engine rejects a second owner

- **WHEN** a second game-service session requests creation against an endpoint with an active
  lease
- **THEN** the request SHALL be refused before `GET /new`
- **AND** the first session's ownership SHALL remain unchanged

#### Scenario: Attach is unsupported without an engine id

- **WHEN** a caller asks the driver to attach to a Marvel slug
- **THEN** the driver SHALL return a descriptive unsupported-attachment error
- **AND** SHALL not open a socket to an unverified active game

### Requirement: Marvel startup is a normal deployment prerequisite

The integration SHALL assume that the repository's ordinary Compose startup starts the engine and
its initialization service. The driver SHALL report a distinct unavailable-backend error when the
engine health or initialization prerequisite is not ready, rather than behaving as if the absence
were an empty setup catalog. The game-service API SHALL map that error to HTTP `503` with a
readiness-oriented `Retry-After` response header.

#### Scenario: A healthy ordinary stack serves setup catalogs

- **WHEN** the ordinary stack reports the Marvel engine and initializer ready
- **THEN** the driver SHALL authenticate and return its scenario and hero-deck catalog
- **AND** setup discovery SHALL not require a profile-specific startup action

#### Scenario: An unready engine is reported distinctly

- **WHEN** Marvel setup discovery runs before the engine initialization prerequisite is ready
- **THEN** the service SHALL report an unavailable-backend error naming the readiness dependency
- **AND** SHALL not report that the catalog is valid but empty
