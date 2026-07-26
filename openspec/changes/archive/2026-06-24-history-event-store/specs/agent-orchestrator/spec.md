## ADDED Requirements

### Requirement: Agent move/decision event emission
The agent-orchestrator SHALL emit an agent move/decision event to the history ingestion bus for each game action it drives through the game-service MCP, capturing the intended action, the agent's reasoning/context for that action, the supplied action arguments, and the full conversation context (ordered message, tool-call, and tool-result history) the agent had at that decision, using the versioned history event envelope with actor `agent`.

#### Scenario: Emit an event for a game-mutating tool call
- **WHEN** a prompt job invokes a game-service MCP tool that performs a game action
- **THEN** the agent-orchestrator SHALL emit a history event with actor `agent` whose payload includes the intended action, the agent's reasoning/context, and the action arguments

#### Scenario: Emitted event carries the full conversation context
- **WHEN** the agent-orchestrator emits an agent move/decision event
- **THEN** the event payload SHALL include the conversation context (ordered messages, tool calls, and tool results) the agent had at that decision, sufficient to rehydrate the session at that point

#### Scenario: Emitted event carries the game correlation id
- **WHEN** the agent-orchestrator emits an agent move/decision event
- **THEN** the event SHALL include the `game_id` correlation identifier for the game the action targets

#### Scenario: Emission does not block the prompt job
- **WHEN** the agent-orchestrator emits an agent move/decision event
- **THEN** the emission SHALL be performed without blocking completion of the prompt job's tool round

### Requirement: Game correlation id capture for agent sessions
The agent-orchestrator SHALL capture the game-service game identifier when a game session is created or attached for an agent session and SHALL reuse it as the `game_id` on every subsequent agent move/decision event for that game.

#### Scenario: Capture the game id from game creation
- **WHEN** a prompt job creates or attaches a game-service game session via MCP and receives its session identifier
- **THEN** the agent-orchestrator SHALL associate that identifier as the `game_id` for subsequent agent move/decision events

#### Scenario: Reuse the captured game id across moves
- **WHEN** the agent-orchestrator emits multiple agent move/decision events for the same game
- **THEN** each event SHALL carry the same captured `game_id`

### Requirement: Resume a session from a supplied conversation context
The agent-orchestrator SHALL support creating or resuming an agent session seeded with a supplied conversation context and bound to a supplied restored `game_id`, so that after a history restore the agent continues from an identical decision situation.

#### Scenario: Resume a session with a restored conversation context
- **WHEN** a restore supplies a conversation context and a restored `game_id` to the agent-orchestrator
- **THEN** the agent-orchestrator SHALL create or resume a session whose conversation context matches the supplied context and whose game binding is the restored `game_id`

#### Scenario: Resumed session can play forward
- **WHEN** a session resumed from a restored conversation context runs its next turn
- **THEN** the agent SHALL act on the restored context and game state as if continuing from the original moment
