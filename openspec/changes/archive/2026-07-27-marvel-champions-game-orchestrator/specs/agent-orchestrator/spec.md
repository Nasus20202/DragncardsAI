## ADDED Requirements

### Requirement: Per-session player agent configuration
The agent-orchestrator SHALL let a client configure a roster of player agents on a session, one entry per player seat, and SHALL persist the roster in PostgreSQL rather than in process memory. Each entry SHALL be addressable by a seat id of the form `player<N>` for N between 1 and 4, and SHALL carry an optional display name, provider id, model name, reasoning configuration, skill list, and raw gateway and provider option overrides.

#### Scenario: Client configures two seats independently
- **WHEN** a client sets a player configuration for `player1` with one model and skill list and for `player2` with a different model and skill list
- **THEN** both entries SHALL be persisted against the session
- **AND** reading the session's roster SHALL return both entries with the values that were written

#### Scenario: Roster survives a restart
- **WHEN** a player configuration has been written and the service is restarted
- **THEN** reading the session's roster SHALL still return that configuration

#### Scenario: Roster is removable
- **WHEN** a client deletes a seat from a session's roster
- **THEN** the entry SHALL no longer be returned for that session
- **AND** deleting a seat that is not configured SHALL return a not-found error

#### Scenario: Roster is removed with its session
- **WHEN** a session is deleted
- **THEN** its player configurations SHALL be deleted with it

### Requirement: Player agent configuration validation
The agent-orchestrator SHALL reject an invalid player configuration with a client error and SHALL NOT persist it.

#### Scenario: Invalid seat id
- **WHEN** a client writes a player configuration for a seat id that is not `player1` through `player4`
- **THEN** the request SHALL be rejected with a client error

#### Scenario: Unsupported provider
- **WHEN** a client writes a player configuration naming a provider that is not enabled for the deployment
- **THEN** the request SHALL be rejected with a client error

#### Scenario: Unknown skill
- **WHEN** a client writes a player configuration naming a skill that cannot be resolved in the skill catalogue
- **THEN** the request SHALL be rejected with a client error

#### Scenario: Unknown session
- **WHEN** a client writes a player configuration for a session that does not exist
- **THEN** the request SHALL be rejected with a not-found error

### Requirement: Player agent configuration inheritance
An unset field in a player configuration SHALL inherit from the orchestrator session's own configuration. A set field SHALL override it. Gateway and provider options SHALL be overlaid on the inherited options rather than replacing them wholesale, and a reasoning configuration SHALL be folded into the resolved gateway options under the same key the runtime already reads.

#### Scenario: Unset provider and model inherit
- **WHEN** a player configuration sets a skill list but no provider or model
- **THEN** a player agent spawned for that seat SHALL run with the orchestrator session's provider and model

#### Scenario: Set fields override
- **WHEN** a player configuration sets a provider and model that differ from the orchestrator session's
- **THEN** a player agent spawned for that seat SHALL run with the seat's provider and model

#### Scenario: Reasoning effort is applied per seat
- **WHEN** a player configuration sets a reasoning effort
- **THEN** the resolved gateway options for that seat SHALL carry that reasoning effort
- **AND** a seat whose reasoning configuration is explicitly disabled SHALL have no reasoning entry in its resolved gateway options

#### Scenario: Unset skills inherit the orchestrator's skills
- **WHEN** a player configuration does not set a skill list
- **THEN** a player agent spawned for that seat SHALL have the orchestrator session's enabled skills enabled

### Requirement: Spawning a player agent from a seat configuration
The agent-orchestrator SHALL be able to spawn a child agent session configured from a named seat's stored configuration rather than from the parent session's configuration. The child SHALL reuse the existing subagent lifecycle: it SHALL run concurrently, its start and terminal outcome SHALL be observable on the parent job, it SHALL be awaitable by the parent, and it SHALL be cancelled when the parent is cancelled.

#### Scenario: Child runs with the seat's configuration
- **WHEN** the orchestrator spawns a player agent for a seat whose configuration names a different model from the parent session's
- **THEN** the child session's model configuration SHALL be the seat's resolved configuration, not the parent's

#### Scenario: Child inherits the parent's MCP servers
- **WHEN** a player agent is spawned
- **THEN** the child session SHALL have the parent session's enabled MCP servers enabled

#### Scenario: Spawning an unconfigured seat fails cleanly
- **WHEN** the orchestrator spawns a player agent for a seat that has no configuration on the session
- **THEN** the call SHALL return an error result naming the configured seats
- **AND** no child session or child job SHALL be created

#### Scenario: Child is observable on the parent
- **WHEN** a player agent is spawned
- **THEN** a subagent-started event SHALL be appended to the parent job identifying the seat
- **AND** a subagent terminal event SHALL be appended when the child finishes

### Requirement: Player identity on recorded agent moves
When an agent move is recorded from a session that represents a player seat, the emitted history envelope SHALL carry that seat id on the event payload so downstream consumers can attribute the move without inference. A move emitted from a session that does not represent a seat SHALL NOT carry a seat id.

#### Scenario: Player agent move carries its seat
- **WHEN** a player agent session makes a game-mutating tool call
- **THEN** the emitted agent-move envelope's payload SHALL include the acting seat id

#### Scenario: Orchestrator move carries no seat
- **WHEN** the orchestrator session itself makes a game-mutating tool call, such as advancing a phase
- **THEN** the emitted agent-move envelope's payload SHALL NOT include a seat id

#### Scenario: Player session is bound to the orchestrator's game
- **WHEN** a player agent is spawned from an orchestrator session that is already bound to a game
- **THEN** the child session SHALL be bound to the same game so its first move is recorded on that game's timeline
