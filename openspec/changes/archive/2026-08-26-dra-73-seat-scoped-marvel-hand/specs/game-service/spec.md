# Seat-scoped Marvel state reads

## ADDED Requirements

### Requirement: State reads accept an optional trusted seat projection

The Game Service SHALL preserve the `get_game_state` operation ID and SHALL accept an
optional neutral `player_n` query/tool parameter on `GET /games/{id}/state`. When
`player_n` is omitted, the service SHALL return the spectator/public projection and
SHALL NOT implicitly select `player1`. When supplied, `player_n` SHALL select the
requested seat's platform-permitted projection. This selector is trusted-session view
selection, not caller authorization; caller-bound seat authorization remains a separate
capability.

#### Scenario: A Marvel player requests its own state

- **WHEN** a trusted caller requests `GET /games/{id}/state?player_n=player1` for a
  Marvel LCG session
- **THEN** the requested seat SHALL be forwarded through state retrieval and
  normalization
- **AND** the response SHALL use the existing neutral state fields and operation ID

#### Scenario: Omission is a spectator read

- **WHEN** a caller requests `GET /games/{id}/state` without `player_n`
- **THEN** the service SHALL use the spectator/public projection
- **AND** it SHALL NOT substitute `player1` as the reader

#### Scenario: Projected state is not cacheable

- **WHEN** the projected state endpoint returns a response
- **THEN** it SHALL include `Cache-Control: private, no-store`

### Requirement: Reader-specific state does not cross-contaminate

The Game Service SHALL not reuse a reader-specific normalized view for another reader.
An explicit seat read SHALL obtain a fresh platform state when the platform applies
reader-sensitive retrieval, and normalization SHALL receive the same requested seat.
Raw transport state cached on a session SHALL NOT determine which normalized hand
projection is returned.

#### Scenario: Sequential seats receive independent projections

- **WHEN** a caller requests a player-one projection and then a player-two projection
  on the same session
- **THEN** the second request SHALL not return player one's normalized hand
- **AND** the platform SHALL receive the player-two selector for the second read

#### Scenario: An ignored DragnCards selector preserves the session cache

- **WHEN** a DragnCards session has a current cached state and a caller supplies
  `player_n` to `get_game_state`
- **THEN** the session SHALL retain its existing cached-state behavior rather than
  forcing a fresh platform read
- **AND** DragnCards normalization SHALL continue to ignore the selector

### Requirement: Existing raw state access remains separate

The existing HTTP-only raw-state endpoint SHALL retain its current route and access
behavior. This change SHALL not add cross-user authentication or restrict raw state;
caller authorization and raw-state restriction are tracked by DRA-75.

#### Scenario: Raw state remains outside the projection change

- **WHEN** a caller requests `GET /games/{id}/state/raw`
- **THEN** the service SHALL preserve the existing raw-state response and HTTP-only
  surface
- **AND** the seat-scoped projection selector SHALL not change that endpoint's access
  policy
