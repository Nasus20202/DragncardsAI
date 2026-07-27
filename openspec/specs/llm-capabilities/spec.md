# LLM Capabilities Spec

## Purpose

This spec defines the capabilities available to an LLM agent during a session: MCP tools, system built-in tools, on-demand skill loading, subagent delegation, and dashboard visibility of agent capability activity.

Implementation details such as worker mechanics, database schema, and internal session/job lifecycle belong in `agent-orchestrator/spec.md`.
## Requirements
### Requirement: Agent tool catalogue at session start
At the start of every prompt job the agent SHALL receive a unified tool list containing all MCP tools from assigned MCP servers and all system built-in tools applicable to the job type. The agent SHALL be able to call any tool in this list without distinguishing between MCP and built-in origin.

#### Scenario: Tool list includes MCP and built-in tools
- **WHEN** a prompt job starts with at least one MCP server and at least one built-in tool applicable
- **THEN** the tool list presented to the LLM contains tools from both sources in a single flat list

#### Scenario: Tool list reflects job type restrictions
- **WHEN** a prompt job starts that is not a master job, such as a child subagent job
- **THEN** the tool list omits built-in tools that are restricted to master jobs only

### Requirement: MCP tool invocation
The agent SHALL be able to invoke tools from any MCP server assigned to the session. Each MCP tool call SHALL be observable in the job transcript as a `tool_call` and `tool_result` event pair.

#### Scenario: Agent invokes an MCP tool
- **WHEN** the agent calls a tool provided by an assigned MCP server
- **THEN** the system executes the tool on the MCP server and returns the result to the agent
- **THEN** a `tool_call` event and a `tool_result` event are appended to the job transcript

#### Scenario: MCP tool not available for session
- **WHEN** the agent calls a tool from an MCP server not assigned to the session
- **THEN** the system returns an error result to the agent describing the unknown tool
- **THEN** the job continues without failing

### Requirement: Skill catalogue presented at job start
At the start of every prompt job the agent SHALL receive a list of assigned skills with their names and one-sentence summaries. Full skill content SHALL NOT be injected into the system prompt; it is delivered on demand via `load_skill`.

#### Scenario: System prompt contains skill summaries
- **WHEN** a job starts with one or more skills assigned to the session
- **THEN** the system prompt includes an "Available skills" section listing each skill name and summary
- **THEN** the system prompt instructs the agent to call `load_skill(<name>)` before using a skill
- **THEN** the system prompt does NOT include the full body of any `SKILL.md`

#### Scenario: No skills assigned
- **WHEN** a job starts with no skills assigned
- **THEN** the system prompt contains the base agent identity and tool-usage instructions only

### Requirement: load_skill system tool
The agent SHALL have access to a system built-in tool named `load_skill` that returns the full `SKILL.md` content of a named skill plus an inventory of available linked reference files. The tool SHALL be available on all job types.

#### Scenario: Agent loads an assigned skill
- **WHEN** the agent invokes `load_skill` with a skill name assigned to the session
- **THEN** the tool returns the full `SKILL.md` content
- **THEN** if the skill package contains other markdown files anywhere under the skill directory, the tool also returns a list of those relative file paths without inlining their contents
- **THEN** a `skill_loaded` event is appended to the job transcript with `skill_name` and `reference_file_count`

#### Scenario: Agent loads a skill not assigned to the session
- **WHEN** the agent invokes `load_skill` with a skill name not assigned to the session
- **THEN** the tool returns an error result and no `skill_loaded` event is emitted

#### Scenario: Skill has no reference files
- **WHEN** the agent loads a skill whose directory contains only `SKILL.md`
- **THEN** the tool result contains only the `SKILL.md` content

### Requirement: load_skill_reference system tool
The agent SHALL have access to a system built-in tool named `load_skill_reference` that returns the content of one named markdown reference file belonging to an assigned skill. The tool SHALL be available on all job types.

#### Scenario: Agent loads a listed skill reference
- **WHEN** the agent invokes `load_skill_reference` with a skill name assigned to the session and a reference filename listed by `load_skill`
- **THEN** the tool returns the full content of that single reference file

#### Scenario: Agent requests a missing skill reference
- **WHEN** the agent invokes `load_skill_reference` with a reference filename that does not exist under the skill directory
- **THEN** the tool returns an error result

#### Scenario: Agent requests a reference from an unassigned skill
- **WHEN** the agent invokes `load_skill_reference` for a skill not assigned to the session
- **THEN** the tool returns an error result

### Requirement: wait_for_subagent system tool
The agent SHALL have access to a `wait_for_subagent` built-in tool that blocks until a previously spawned subagent identified by `child_job_id` reaches a terminal state and returns its result. This tool SHALL be available only on master jobs.

#### Scenario: Agent waits for a subagent result
- **WHEN** a master job agent invokes `wait_for_subagent` with a `child_job_id`
- **THEN** the tool blocks until the child job reaches a terminal state
- **THEN** if the child completed successfully, the tool returns the child's result text
- **THEN** if the child failed or timed out, the tool returns an error result

### Requirement: spawn_subagent system tool supports non-blocking parallel dispatch
The agent SHALL have access to a system built-in tool named `spawn_subagent` that creates an isolated child agent session and immediately returns its `child_job_id` and a derived `name`. The child agent runs concurrently; the calling agent does not block and MAY spawn additional subagents in the same turn or continue with other work. This tool SHALL be available only on master prompt jobs.

#### Scenario: Agent spawns a subagent and continues immediately
- **WHEN** a master job agent invokes `spawn_subagent` with a prompt
- **THEN** a child session is created, a child prompt job is started concurrently, and the tool result is returned immediately containing `child_job_id` and `name`
- **THEN** the calling agent MAY continue its reasoning, call other tools, or spawn more subagents without waiting for this child to finish

#### Scenario: Agent spawns multiple subagents in parallel
- **WHEN** a master job agent invokes `spawn_subagent` multiple times in one or more turns
- **THEN** each child job runs concurrently with no ordering guarantee
- **THEN** each child's outcome is recorded on the parent job transcript asynchronously when it completes or fails

#### Scenario: Subagent name derived from prompt
- **WHEN** `spawn_subagent` is called with a prompt
- **THEN** the tool result includes a `name` field containing the first 50 characters of the prompt
- **THEN** the `subagent_started` event on the parent job also carries this `name`

#### Scenario: Child job fails
- **WHEN** a spawned child job fails
- **THEN** a `subagent_failed` event is appended to the parent job asynchronously
- **THEN** the parent agent is NOT interrupted because it has already received the initial tool result and continued

#### Scenario: spawn_subagent unavailable on child jobs
- **WHEN** the agent in a child subagent job attempts to call `spawn_subagent`
- **THEN** the tool is not present in the tool list and the call is treated as an unknown tool error

### Requirement: Subagent activity visible in parent transcript
The parent job transcript SHALL record the lifecycle of every subagent spawned during that job.

#### Scenario: subagent_started event
- **WHEN** `spawn_subagent` creates a child session and job
- **THEN** a `subagent_started` event is appended to the parent job with `child_session_id`, `child_job_id`, and `name`

#### Scenario: subagent_completed event
- **WHEN** a child job completes successfully
- **THEN** a `subagent_completed` event is appended to the parent job asynchronously with `child_session_id` and `child_job_id`

#### Scenario: subagent_failed event
- **WHEN** a child job fails or is cancelled
- **THEN** a `subagent_failed` event is appended to the parent job asynchronously with `child_session_id`, `child_job_id`, and `reason`

### Requirement: Dashboard renders agent capability events
The dashboard transcript SHALL render skill loads and MCP tool calls as distinct collapsible rows. Subagent lifecycle events in the parent transcript SHALL be minimal single-line entries; the full subagent transcript is shown in the inline subagent card, not duplicated in the parent thread.

#### Scenario: skill_loaded rendered
- **WHEN** the transcript receives a `skill_loaded` event
- **THEN** it displays a collapsible row showing the skill name and reference file count

#### Scenario: tool_call and tool_result rendered
- **WHEN** the transcript receives a `tool_call` / `tool_result` pair
- **THEN** it displays a collapsible row with the tool name, arguments, and result

#### Scenario: subagent transcript entry is a single line
- **WHEN** the transcript receives `subagent_started`, `subagent_completed`, or `subagent_failed`
- **THEN** it displays a single non-expandable line indicating the subagent name and status in the parent job thread
- **THEN** the full child transcript is shown in the separate inline subagent card

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

