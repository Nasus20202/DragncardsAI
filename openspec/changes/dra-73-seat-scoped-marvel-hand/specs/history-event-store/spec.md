# Spectator-redacted Marvel state history

## ADDED Requirements

### Requirement: Marvel hand names are excluded from durable state events

When game-service publishes a Marvel LCG state, prompt, move, or terminal event for
history, its normalized state SHALL use the spectator projection. Player hands SHALL be
represented only by hidden counts, while unambiguous public state may remain visible.
The history payload SHALL not contain private hand card names, identifiers, or metadata.

#### Scenario: A player-specific live read does not affect history

- **WHEN** a player-specific state read occurs before a Marvel history event is emitted
- **THEN** history normalization SHALL independently use the spectator projection
- **AND** the event SHALL not contain the previously selected hand's card names
