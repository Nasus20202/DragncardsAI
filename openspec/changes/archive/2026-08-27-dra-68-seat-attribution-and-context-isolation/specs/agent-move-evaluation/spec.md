## ADDED Requirements

### Requirement: Isolate attributed move context

The evaluator SHALL restrict neighbouring agent moves supplied as context for a move-scoped evaluation to the target move's player when the target carries a player attribution. Context for an attributed move SHALL NOT include another player's action, reasoning, or arguments.

#### Scenario: A move receives only its seat's context

- **WHEN** a move-scoped evaluation targets a `player1` move in a round that also contains `player2` moves
- **THEN** the assembled neighbouring context SHALL contain only `player1` agent moves from the target's round

#### Scenario: Legacy chat context remains aggregate

- **WHEN** a move-scoped evaluation targets an agent move with no player attribution
- **THEN** the assembled neighbouring context SHALL retain the existing aggregate selection across agent moves
