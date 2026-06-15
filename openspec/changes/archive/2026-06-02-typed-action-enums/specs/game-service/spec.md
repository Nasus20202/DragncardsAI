## MODIFIED Requirements

### Requirement: Game action execution
The Game Service SHALL provide endpoints and MCP tools to execute game actions within a session.

#### Scenario: Execute a card movement action
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to move a card from one group to another (e.g., play a card from hand to the play area)
- **THEN** the Game Service SHALL translate the action into the appropriate DragnCards WebSocket message, execute it, and return a success acknowledgment (`session_id` + `success: true`); the caller must use `get_game_state` to observe the updated state

#### Scenario: Execute a game phase action
- **WHEN** a client requests a phase-related action (e.g., end the player phase, advance to the next round)
- **THEN** the Game Service SHALL execute the phase transition via WebSocket and return a success acknowledgment; the caller must use `get_game_state` to observe the updated state

#### Scenario: Execute action on non-existent session
- **WHEN** a client requests an action on an invalid session ID
- **THEN** the Game Service SHALL return a 404 error (HTTP) or an MCP error with a descriptive message

#### Scenario: Execute an invalid action
- **WHEN** a client requests an action that is not valid in the current game state
- **THEN** the Game Service SHALL return an error indicating the action could not be performed

#### Scenario: Typed action enums validate Marvel Champions inputs
- **WHEN** a client invokes a typed action helper with a Marvel Champions–scoped enum field (group ID, player identifier, or layout ID)
- **THEN** the Game Service SHALL validate the value against the Marvel Champions enum list and reject invalid values with a validation error

#### Scenario: Typed action schemas expose enums
- **WHEN** a client inspects the OpenAPI or MCP schema for typed action helpers
- **THEN** the enum-constrained fields SHALL be declared with explicit allowed values in the schema
