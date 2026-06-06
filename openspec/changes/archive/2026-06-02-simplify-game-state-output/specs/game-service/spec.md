## MODIFIED Requirements

### Requirement: Game state observation
The Game Service SHALL provide endpoints and MCP tools to query the current game state for a given session, returning a simplified representation for Marvel Champions sessions.

#### Scenario: Get current game state via HTTP
- **WHEN** a client sends `GET /games/{id}/state`
- **THEN** the Game Service SHALL return the current game state including all card groups (hand, deck, play area, discard, etc.), card properties, player state, round/phase information, and any game counters

#### Scenario: Get current game state via MCP
- **WHEN** an MCP client invokes the `get_game_state` tool with a session ID
- **THEN** the Game Service SHALL return the game state formatted as structured text suitable for LLM consumption, clearly describing the board state including card names, locations, and properties

#### Scenario: Get state for non-existent session
- **WHEN** a client requests state for an invalid session ID
- **THEN** the Game Service SHALL return a 404 error (HTTP) or an MCP error with a descriptive message

#### Scenario: State reflects latest game changes
- **WHEN** an action is executed on a session and then the state is queried
- **THEN** the returned state SHALL reflect the result of the most recent action, including any automated effects triggered by the DragnCards engine

#### Scenario: Get simplified state for Marvel Champions via HTTP
- **WHEN** a client sends `GET /games/{id}/state` for a Marvel Champions session
- **THEN** the Game Service SHALL return a flattened representation containing only `roundNumber`, `mode`, `villainHitPoints`, `players` (hitPoints/handSize), and `zones` with visible cards (id, instanceId, name, currentSide, exhausted, tokens)

#### Scenario: Simplified state omits attachment hierarchy
- **WHEN** a client requests state for a Marvel Champions session
- **THEN** the Game Service SHALL exclude cards that are attachments tucked under other cards from zone listings