## MODIFIED Requirements

### Requirement: spawn_subagent system tool supports non-blocking parallel dispatch
The agent SHALL have access to a system built-in tool named `spawn_subagent` that creates an isolated child agent session and immediately returns its `child_job_id` and a generated `name`. The child agent runs concurrently; the calling agent does not block and MAY spawn additional subagents in the same turn or continue with other work. This tool SHALL be available only on master prompt jobs.

The returned `name` SHALL be a generated display name rather than a slice of the prompt, so that several subagents started from prompts that share their opening are still distinguishable to whoever reads the transcript. The same string SHALL appear in the tool result, on the child session, and in the `subagent_started` event.

`spawn_subagent` SHALL accept an optional `persona` argument naming a persona to start the child from. The tool description SHALL state that the argument is optional, that omitting it starts a child that inherits the caller's own configuration, and that a persona changes the child's prompt, skills, and tool access. Naming a persona that does not exist SHALL return an error result naming the requested persona and the available ones, without creating a child.

#### Scenario: Agent spawns a subagent and continues immediately
- **WHEN** a master job agent invokes `spawn_subagent` with a prompt
- **THEN** a child session is created, a child prompt job is started concurrently, and the tool result is returned immediately containing `child_job_id` and `name`
- **THEN** the calling agent MAY continue its reasoning, call other tools, or spawn more subagents without waiting for this child to finish

#### Scenario: Agent spawns multiple subagents in parallel
- **WHEN** a master job agent invokes `spawn_subagent` multiple times in one or more turns
- **THEN** each child job runs concurrently with no ordering guarantee
- **THEN** each child's outcome is recorded on the parent job transcript asynchronously when it completes or fails

#### Scenario: Subagent name is generated, not sliced from the prompt
- **WHEN** `spawn_subagent` is called with a prompt
- **THEN** the tool result SHALL include a `name` field holding a generated display name
- **THEN** that name SHALL NOT be a truncation of the prompt
- **THEN** the `subagent_started` event on the parent job SHALL carry the same `name`

#### Scenario: Subagents started from similar prompts get different names
- **WHEN** a master job agent spawns several subagents whose prompts share the same opening text
- **THEN** each child SHALL have a distinguishable `name`

#### Scenario: Agent names a persona for the child
- **WHEN** a master job agent invokes `spawn_subagent` with a prompt and the name of an existing persona
- **THEN** the child SHALL be started from that persona, and the tool result and the `subagent_started` event SHALL both name it

#### Scenario: Agent names a persona that does not exist
- **WHEN** a master job agent invokes `spawn_subagent` naming a persona that is not defined
- **THEN** the tool SHALL return an error result naming the requested persona and the available personas, and no child job SHALL be created

#### Scenario: Persona is optional
- **WHEN** a master job agent invokes `spawn_subagent` with only a prompt
- **THEN** the child SHALL inherit the caller's model configuration and skills exactly as it did before personas existed

#### Scenario: Child job fails
- **WHEN** a spawned child job fails
- **THEN** a `subagent_failed` event is appended to the parent job asynchronously
- **THEN** the parent agent is NOT interrupted because it has already received the initial tool result and continued

#### Scenario: spawn_subagent unavailable on child jobs
- **WHEN** the agent in a child subagent job attempts to call `spawn_subagent`
- **THEN** the tool is not present in the tool list and the call is treated as an unknown tool error

### Requirement: Dashboard renders agent capability events
The dashboard transcript SHALL render skill loads and MCP tool calls as distinct collapsible rows. Subagent lifecycle events in the parent transcript SHALL be minimal single-line entries; the full subagent transcript is shown in the subagent output view opened from the subagent list or from the tool card that started it, not duplicated in the parent thread.

#### Scenario: skill_loaded rendered
- **WHEN** the transcript receives a `skill_loaded` event
- **THEN** it displays a collapsible row showing the skill name and reference file count

#### Scenario: tool_call and tool_result rendered
- **WHEN** the transcript receives a `tool_call` / `tool_result` pair
- **THEN** it displays a collapsible row with the tool name, arguments, and result

#### Scenario: subagent transcript entry is a single line
- **WHEN** the transcript receives `subagent_started`, `subagent_completed`, or `subagent_failed`
- **THEN** it displays a single non-expandable line indicating the subagent name and status in the parent job thread
- **THEN** the full child transcript is shown in the separate subagent output view
