<!-- Scope: this spec covers implementation details — worker mechanics, DB schema, internal session/job lifecycle.
     LLM-visible behaviour (tool contracts, events, dashboard rendering) belongs in llm-capabilities/spec.md. -->

## ADDED Requirements

### Requirement: parent_job_id persisted on subagent jobs
The `jobs` table SHALL include a nullable `parent_job_id` foreign key referencing `jobs.id`. Jobs created by the `spawn_subagent` built-in tool SHALL have this field set to the spawning job's id. All other jobs SHALL have it set to null.

#### Scenario: Master job has null parent_job_id
- **WHEN** a prompt job is created via the normal prompt submission endpoint
- **THEN** its `parent_job_id` SHALL be null

#### Scenario: Child job has parent_job_id set
- **WHEN** a job is created as a result of a `spawn_subagent` tool call
- **THEN** its `parent_job_id` SHALL reference the spawning job's id

### Requirement: Built-in tool dispatch in worker loop
The worker SHALL maintain a registry of built-in tools that are dispatched locally before MCP tool lookup. Built-in tools SHALL appear in the OpenAI tool list presented to the LLM alongside MCP tools. When the LLM calls a built-in tool the worker SHALL handle it locally and emit `tool_call` and `tool_result` events using `assignment="builtin"` and `server_url=null`.

#### Scenario: Built-in tool called by LLM
- **WHEN** the LLM invokes a tool name that matches a registered built-in
- **THEN** the worker SHALL execute the built-in handler locally
- **THEN** the worker SHALL append a `tool_call` event with `assignment="builtin"` and a `tool_result` event with the handler's output before continuing the tool round

#### Scenario: Built-in tool name does not shadow MCP tool
- **WHEN** the LLM invokes a tool name that matches a built-in AND an MCP tool with the same name
- **THEN** the built-in handler SHALL take precedence and no MCP call SHALL be made

### Requirement: spawn_subagent fires child job and returns immediately
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, name the child session from the prompt, and return a tool result immediately containing the `child_job_id` and derived `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task monitors the child job and appends `subagent_completed` or `subagent_failed` to the parent job's event log when the child reaches a terminal state, then terminates the child session.

#### Scenario: Child session created and configured
- **WHEN** `spawn_subagent` is called with a valid prompt
- **THEN** the worker SHALL create a new `AgentSession` via the repository
- **THEN** the worker SHALL name the child session with the first 50 characters of the prompt (truncated, no ellipsis)
- **THEN** the worker SHALL copy the parent session's model config

#### Scenario: Child job enqueued with parent reference
- **WHEN** the child session is configured
- **THEN** the worker SHALL enqueue a prompt job with `parent_job_id` pointing to the current (parent) job
- **THEN** the child job SHALL begin running concurrently via `asyncio.create_task`

#### Scenario: spawn_subagent returns immediately
- **WHEN** the child job is enqueued and started
- **THEN** `spawn_subagent` SHALL return a tool result immediately with `child_job_id` and `name` without waiting for the child to finish
- **THEN** the parent agent SHALL continue its own reasoning and may spawn additional subagents

#### Scenario: Background task monitors child and emits outcome
- **WHEN** the child job reaches a terminal state (`completion` or `failure`)
- **THEN** a background coroutine SHALL append `subagent_completed` or `subagent_failed` to the parent job's event log
- **THEN** the background coroutine SHALL terminate the child session

#### Scenario: Child session terminated after job reaches terminal state
- **WHEN** the child job reaches a terminal state
- **THEN** the background task SHALL call `terminate_session` on the child session

### Requirement: subagent_started payload includes name
The `subagent_started` event appended to the parent job SHALL include a `name` field containing the first 50 characters of the prompt (used to identify the subagent in the dashboard).

#### Scenario: subagent_started name field present
- **WHEN** `spawn_subagent` emits `subagent_started`
- **THEN** the event payload SHALL include `child_job_id`, `child_session_id`, and `name` (first 50 chars of prompt)
The worker SHALL determine whether a job is a master job by checking `parent_job_id is null AND job_type = "prompt"`. The `spawn_subagent` tool SHALL be included in the tool list only for master jobs.

#### Scenario: spawn_subagent omitted for child jobs
- **WHEN** a job has a non-null `parent_job_id`
- **THEN** `spawn_subagent` SHALL NOT appear in the tool definitions sent to the LLM

#### Scenario: spawn_subagent omitted for compaction jobs
- **WHEN** a job has `job_type = "compaction"`
- **THEN** `spawn_subagent` SHALL NOT appear in the tool definitions sent to the LLM

## MODIFIED Requirements

### Requirement: System prompt construction
The worker SHALL build the system prompt by including only a short skill summary (name + one-sentence description) for each assigned skill rather than the full SKILL.md content. Full skill content SHALL be delivered on demand via the skill-loading built-in tools.

#### Scenario: System prompt with assigned skills
- **WHEN** a job starts with skills assigned to the session
- **THEN** the system prompt contains a "Available skills" section listing each skill name and its summary
- **THEN** the system prompt instructs the agent to call `load_skill(<name>)` to load a skill's full instructions and reference inventory before using it
- **THEN** the system prompt instructs the agent to call `load_skill_reference(<skill_name>, <reference_name>)` only for the specific reference files it chooses to inspect

#### Scenario: System prompt with no assigned skills
- **WHEN** a job starts with no skills assigned
- **THEN** the system prompt contains the base identity and tool-usage instructions only
