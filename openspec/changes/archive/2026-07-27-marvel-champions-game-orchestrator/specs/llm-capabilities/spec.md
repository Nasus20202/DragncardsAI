## ADDED Requirements

### Requirement: Player agent built-in tools
A master prompt job on a session that has a player roster SHALL receive two additional built-in tools: `list_player_agents`, which returns the configured seats and their resolved configuration, and `prompt_player_agent`, which sends a prompt to a named seat's player agent. A session with no player roster SHALL NOT receive these tools, and a job that is not a master job SHALL NOT receive them.

#### Scenario: Tools appear for a session with a roster
- **WHEN** a master prompt job starts on a session that has at least one player configuration
- **THEN** the tool list presented to the agent SHALL include `list_player_agents` and `prompt_player_agent`

#### Scenario: Tools are absent without a roster
- **WHEN** a master prompt job starts on a session with no player configurations
- **THEN** the tool list presented to the agent SHALL NOT include `list_player_agents` or `prompt_player_agent`

#### Scenario: Player agents cannot spawn player agents
- **WHEN** a job is running as a player agent or any other subagent
- **THEN** the tool list SHALL NOT include `prompt_player_agent`

### Requirement: Inspecting the player roster
`list_player_agents` SHALL return, for every configured seat, the seat id, the display name if set, and the provider, model, reasoning, and skills that a player agent for that seat would actually run with after inheritance is applied.

#### Scenario: Roster reports resolved configuration
- **WHEN** the agent calls `list_player_agents` on a session with two configured seats
- **THEN** the result SHALL list both seats with the provider, model, reasoning, and skills each would run with

### Requirement: Prompting a player agent
`prompt_player_agent` SHALL accept a seat id and a prompt, SHALL spawn a child agent for that seat configured from its stored configuration, and SHALL return immediately with the child job id so the orchestrator can await it with `wait_for_subagent`.

#### Scenario: Prompt returns a child job id
- **WHEN** the agent calls `prompt_player_agent` with a configured seat id and a prompt
- **THEN** the result SHALL contain the child job id and the seat id
- **AND** the child SHALL run concurrently rather than blocking the call

#### Scenario: Result is retrievable
- **WHEN** the orchestrator calls `wait_for_subagent` with the child job id returned by `prompt_player_agent`
- **THEN** it SHALL receive that player agent's final answer once the child finishes

#### Scenario: Missing arguments are rejected
- **WHEN** the agent calls `prompt_player_agent` without a seat id or without a prompt
- **THEN** the call SHALL return an error result describing the missing argument
- **AND** no child job SHALL be created
