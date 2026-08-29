## MODIFIED Requirements

### Requirement: Game creation embeds document content, not file paths

marvel-lcg SHALL create a game entirely over HTTP through `GET /new?data=<NewGameDescriptor>`,
where the descriptor contains stringified scenario and hero-deck document content. The
game-service driver SHALL accept only scenario and hero-deck ids returned by the neutral setup
catalog, resolve those ids to document content immediately before creation, and preserve the
ordered `hero_decks` list when constructing `hero_json`.

The driver SHALL derive catalog identity from the engine document's logical relative path. Equivalent
representations that differ only by a leading `./` SHALL identify the same document for catalog
membership checks, so an opaque id returned by setup discovery SHALL remain valid if the engine
uses the equivalent spelling in the immediately subsequent listing. The driver SHALL retain the
actual path returned by the live creation listing when fetching the document.

The driver SHALL not accept a display name, an arbitrary filesystem path, a MarvelCDB import, or an
untyped `plugin_info` mapping as an alternative setup identity. If a selected id is no longer in the
live catalog, creation SHALL fail rather than selecting another entry.

#### Scenario: Selected catalog ids become document content

- **WHEN** a caller selects one listed scenario id and two listed hero-deck ids in seat order
- **THEN** the driver SHALL fetch the corresponding scenario and deck documents
- **AND** SHALL send those document texts in the descriptor in the same order

#### Scenario: Catalog identifiers are passed through unchanged

- **WHEN** a caller builds a creation request from the scenario and hero-deck entries returned by setup discovery
- **THEN** the request SHALL contain those exact opaque identifiers without reconstructing them from paths or names
- **AND** the driver SHALL resolve each identifier against the live creation catalog before fetching document content

#### Scenario: Equivalent engine path spellings preserve a selected hero-deck id

- **WHEN** setup discovery returns `./deck/starter/spider_man.json` and creation's live listing returns
the same document as `deck/starter/spider_man.json`
- **THEN** the opaque id returned by setup discovery SHALL be accepted by creation
- **AND** the driver SHALL fetch the path from the live creation listing
- **AND** the driver SHALL send Spider-Man's document content in the new-game descriptor

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
