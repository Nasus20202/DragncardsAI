## MODIFIED Requirements

### Requirement: Game-state and status event emission
The Game Service SHALL emit a game-state/status event to the history ingestion bus after each state-mutating operation on a session — including action execution, prebuilt-deck loading, snapshot/state loading, and game reset — capturing the resulting game-state representation and the game status, using the versioned history event envelope with actor `game-service` and the session identifier as the `game_id`.

#### Scenario: Emit a state event after an executed action
- **WHEN** the Game Service executes an action for a session and observes the resulting state
- **THEN** the Game Service SHALL emit a history event with actor `game-service` whose payload includes the resulting game-state representation and the game status (such as `in progress`, `win`, or `loss`)

#### Scenario: Emit a state event after loading a prebuilt deck
- **WHEN** the Game Service successfully loads a prebuilt deck into a session and observes the resulting state
- **THEN** the Game Service SHALL emit exactly one history event capturing the post-load game-state representation and status, carrying the replayable deck-load action so the event can be replayed forward during restore

#### Scenario: Emit a state event after loading a game state snapshot
- **WHEN** the Game Service successfully loads a game-state snapshot into a session and observes the resulting state
- **THEN** the Game Service SHALL emit exactly one history event capturing the loaded game-state representation and status

#### Scenario: Emit a state event after resetting a game
- **WHEN** the Game Service successfully resets a session's game and observes the resulting state
- **THEN** the Game Service SHALL emit exactly one history event capturing the post-reset game-state representation and status

#### Scenario: Read-only state observation does not emit
- **WHEN** the Game Service serves a read-only state observation or snapshot export without mutating the session
- **THEN** the Game Service SHALL NOT emit a game-state/status event

#### Scenario: Emitted event uses the session id as the game correlation id
- **WHEN** the Game Service emits a game-state/status event
- **THEN** the event SHALL carry the session identifier as its `game_id` correlation identifier

#### Scenario: Emission does not change game behavior
- **WHEN** the Game Service emits a game-state/status event for any state-mutating operation
- **THEN** the result returned to the original caller SHALL be unchanged by the emission, and any emission failure SHALL be swallowed without aborting or altering the operation
