## ADDED Requirements

### Requirement: Player attribution on evaluation events
The history-service SHALL accept, store, and return an optional `player` attribute on evaluation
events, identifying the player a verdict pertains to (e.g. `player1`), so per-player move/round/
game evaluations can be distinguished and queried. The field SHALL be optional for backward
compatibility with existing evaluation events that predate per-player scoring.

#### Scenario: Store and return a player-attributed evaluation
- **WHEN** an evaluation event is appended with a `player` attribute
- **THEN** the history-service SHALL persist it and SHALL include the `player` when the event is
  listed or read back

#### Scenario: Evaluation without a player remains valid
- **WHEN** an evaluation event is appended without a `player` attribute
- **THEN** the history-service SHALL accept and store it unchanged (backward compatible)
