# Marvel LCG seat-scoped world retrieval

## ADDED Requirements

### Requirement: Explicit state seats are validated before engine access

The Marvel LCG driver SHALL validate an explicit neutral `player_n` against the
session's held seats before checking transport state or calling `GET /get_world`. A
seat not held by the session SHALL be rejected without an engine request. When
`player_n` is omitted, the driver MAY use a held seat only as a transport fallback for
obtaining the engine world; that fallback SHALL not choose the normalized hand reader.

#### Scenario: An unheld seat is rejected before transport

- **WHEN** a session holding only `player1` receives a state request for `player2`
- **THEN** the driver SHALL return a seat error
- **AND** SHALL not call the Marvel engine

#### Scenario: A selected seat reaches the engine

- **WHEN** a session holds `player2` and receives a state request for `player2`
- **THEN** the client SHALL request `GET /get_world?p=1`
- **AND** the normalizer SHALL receive neutral `player_n=player2`

### Requirement: Marvel visibility is normalized per request

The driver SHALL not mutate a shared normalizer's reader seat. Each state projection
SHALL pass its requested seat to normalization, and each history projection SHALL pass
the spectator value. The neutral state vocabulary and existing operation surface SHALL
remain unchanged.

#### Scenario: Reader selection does not persist between calls

- **WHEN** the same Marvel normalizer handles a player-one projection and then a
  player-two projection
- **THEN** the second projection SHALL use only `player_n=player2`
- **AND** the first projection's reader SHALL not remain as shared mutable state
