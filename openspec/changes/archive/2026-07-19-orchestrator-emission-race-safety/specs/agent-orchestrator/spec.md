## MODIFIED Requirements

### Requirement: Agent move/decision event emission
The agent-orchestrator SHALL emit an agent move/decision event to the history ingestion bus for each game action it drives through the game-service MCP, capturing the intended action, the agent's reasoning/context for that action, the supplied action arguments, and the full conversation context (ordered message, tool-call, and tool-result history) the agent had at that decision, using the versioned history event envelope with actor `agent`.

Emission SHALL NOT block completion of the prompt job's tool round. When multiple history events are emitted for the same game, the agent-orchestrator SHALL ensure that, within a worker process, the events reach the ingestion stream in the same order their per-game producer offsets were assigned — because the history-service assigns each game's authoritative sequence by stream arrival order — so that assigning an offset and publishing the corresponding envelope is one indivisible step and a later-offset event can never reach the stream before an earlier-offset one.

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

#### Scenario: Concurrent emissions reach the stream in offset order
- **WHEN** several history events for the same game are emitted concurrently (for example a `user_prompt` and one or more `agent_move` events during one job, or interleaved emissions across jobs bound to the same game in one worker process)
- **THEN** the agent-orchestrator SHALL publish those events to the ingestion stream in the same order their producer offsets were assigned, so a later-offset event never arrives before an earlier-offset one and the durable timeline is not reordered
