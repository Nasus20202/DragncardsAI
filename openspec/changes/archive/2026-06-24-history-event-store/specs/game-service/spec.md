## ADDED Requirements

### Requirement: Game-state and status event emission
The Game Service SHALL emit a game-state/status event to the history ingestion bus after each executed action, capturing the resulting game-state representation and the game status, using the versioned history event envelope with actor `game-service` and the session identifier as the `game_id`.

#### Scenario: Emit a state event after an executed action
- **WHEN** the Game Service executes an action for a session and observes the resulting state
- **THEN** the Game Service SHALL emit a history event with actor `game-service` whose payload includes the resulting game-state representation and the game status (such as `in progress`, `win`, or `loss`)

#### Scenario: Emitted event uses the session id as the game correlation id
- **WHEN** the Game Service emits a game-state/status event
- **THEN** the event SHALL carry the session identifier as its `game_id` correlation identifier

#### Scenario: Emission does not change game behavior
- **WHEN** the Game Service emits a game-state/status event
- **THEN** the action result returned to the original caller SHALL be unchanged by the emission

### Requirement: Snapshot-based restore entry point for history replay
The Game Service SHALL provide a snapshot-based restore entry point that the history-service can use to load a stored snapshot into a target session and then apply replayed actions forward, reusing the existing versioned snapshot import contract.

#### Scenario: Load a history-supplied snapshot into a target session
- **WHEN** the history-service loads a stored snapshot into a target Game Service session whose plugin identity matches the snapshot
- **THEN** the Game Service SHALL apply the snapshot and return the updated game state so that subsequent replayed actions can be applied forward

#### Scenario: Reject a snapshot with mismatched plugin identity during restore
- **WHEN** the history-service loads a snapshot whose plugin identity or schema version does not match the target session
- **THEN** the Game Service SHALL reject the load with a descriptive client error and SHALL NOT mutate the target session

#### Scenario: Apply replayed actions after snapshot load
- **WHEN** the history-service applies replayed game-mutating actions to a session after loading a snapshot
- **THEN** the Game Service SHALL execute those actions through its normal action execution path and reflect them in the session state
