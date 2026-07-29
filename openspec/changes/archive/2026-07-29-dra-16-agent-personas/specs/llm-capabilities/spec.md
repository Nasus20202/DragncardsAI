## ADDED Requirements

### Requirement: Persona catalogue presented to a master job
When at least one persona is defined, a master prompt job's system prompt SHALL list the available personas by name with their descriptions, so the agent can name one in `spawn_subagent` rather than guessing. The catalogue SHALL be names and descriptions only — a persona's own system prompt SHALL NOT be inlined into the parent's context, because it is the child's instruction and would otherwise cost the parent context for every persona that exists.

A deployment with no personas SHALL see no persona section, and a subagent job SHALL NOT receive the catalogue because it cannot spawn anything.

#### Scenario: Master job sees the persona catalogue
- **WHEN** a master prompt job starts and two personas are defined
- **THEN** its system prompt SHALL name both personas with their descriptions and state that `spawn_subagent` accepts a persona

#### Scenario: No personas means no persona section
- **WHEN** a master prompt job starts and no personas are defined
- **THEN** its system prompt SHALL contain no persona catalogue

#### Scenario: Subagents do not receive the catalogue
- **WHEN** a subagent job starts and personas are defined
- **THEN** its system prompt SHALL NOT contain the persona catalogue, because a subagent has no `spawn_subagent` tool

## MODIFIED Requirements

### Requirement: spawn_subagent system tool supports non-blocking parallel dispatch
The agent SHALL have access to a system built-in tool named `spawn_subagent` that creates an isolated child agent session and immediately returns its `child_job_id` and a derived `name`. The child agent runs concurrently; the calling agent does not block and MAY spawn additional subagents in the same turn or continue with other work. This tool SHALL be available only on master prompt jobs.

`spawn_subagent` SHALL accept an optional `persona` argument naming a persona to start the child from. The tool description SHALL state that the argument is optional, that omitting it starts a child that inherits the caller's own configuration, and that a persona changes the child's prompt, skills, and tool access. Naming a persona that does not exist SHALL return an error result naming the requested persona and the available ones, without creating a child.

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
