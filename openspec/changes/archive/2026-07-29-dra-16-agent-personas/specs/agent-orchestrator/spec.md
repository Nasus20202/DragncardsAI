## ADDED Requirements

### Requirement: Agent persona persistence
The agent-orchestrator SHALL let a client define named agent personas and SHALL persist them in PostgreSQL rather than in process memory, in a repository file, or in the runtime skills directory. A persona SHALL be a reusable bundle of a system prompt, a skill selection, and a tool configuration, and SHALL carry: a name that identifies it, an optional display name and description, a system prompt, an optional provider id and model name, gateway and provider option overrides, a skill list, and a tool allowlist.

A persona SHALL be scoped to the deployment rather than to a session or a user, because a persona exists precisely to be reused across sessions and because the service carries no user identity to scope to. A persona's name SHALL be its identity, so a persona is addressable by name in an API path and nameable by an agent in a tool argument.

A persona SHALL NOT carry provider credentials of any kind. Naming a provider and a model SHALL be the only way a persona refers to provider configuration, and API keys SHALL remain in the gateway configuration.

#### Scenario: Persona is created and read back
- **WHEN** a client writes a persona with a system prompt, a skill list, and a tool allowlist
- **THEN** the persona SHALL be persisted
- **AND** reading that persona by name SHALL return the values that were written

#### Scenario: Persona survives a restart
- **WHEN** a persona has been written and the service is restarted
- **THEN** listing personas SHALL still return that persona with its stored configuration

#### Scenario: Persona write is an upsert
- **WHEN** a client writes a persona whose name already exists
- **THEN** the stored persona SHALL be replaced by the submitted configuration rather than rejected as a duplicate

#### Scenario: Persona is listed and deletable
- **WHEN** a client lists personas
- **THEN** every stored persona SHALL be returned
- **AND** deleting a persona by name SHALL remove it, and deleting a persona that does not exist SHALL return a not-found error

#### Scenario: Unknown persona is not found
- **WHEN** a client reads a persona name that has never been written
- **THEN** the request SHALL be rejected with a not-found error

### Requirement: Agent persona validation
The agent-orchestrator SHALL reject an invalid persona with a client error and SHALL NOT persist it. A persona name SHALL be a lowercase slug. A persona's system prompt SHALL be bounded in length so that a single persona cannot exhaust a context window or a request-body limit on its own, and its description, skill list, and tool allowlist SHALL be bounded likewise.

A persona naming a provider that the deployment has not enabled SHALL be rejected. A persona naming a skill that cannot be resolved in the skill catalogue SHALL be rejected with a message that names the unresolvable skill.

#### Scenario: Invalid persona name
- **WHEN** a client writes a persona whose name is not a lowercase slug
- **THEN** the request SHALL be rejected with a client error and nothing SHALL be persisted

#### Scenario: Oversized persona prompt
- **WHEN** a client writes a persona whose system prompt exceeds the permitted length
- **THEN** the request SHALL be rejected with a client error and nothing SHALL be persisted

#### Scenario: Unsupported provider
- **WHEN** a client writes a persona naming a provider that is not enabled for the deployment
- **THEN** the request SHALL be rejected with a client error

#### Scenario: Unknown skill named on write
- **WHEN** a client writes a persona naming a skill that cannot be resolved in the skill catalogue
- **THEN** the request SHALL be rejected with a client error whose message names that skill

### Requirement: Persona resolution against the spawning session
When a subagent is started from a persona, the agent-orchestrator SHALL resolve the persona against the spawning session before configuring the child. An unset provider or model on the persona SHALL inherit the session's. The persona's gateway and provider options SHALL be overlaid on the session's rather than replacing them wholesale, so a persona can change one option without restating the rest. A persona whose skill list is unset SHALL inherit the session's enabled skills; a persona whose skill list is set — including to an empty list — SHALL replace them.

#### Scenario: Unset provider and model inherit
- **WHEN** a persona sets a system prompt but no provider or model
- **THEN** a subagent started from that persona SHALL run with the spawning session's provider and model

#### Scenario: Set provider and model override
- **WHEN** a persona names a provider and model different from the spawning session's
- **THEN** a subagent started from that persona SHALL run with the persona's provider and model

#### Scenario: Options are overlaid, not replaced
- **WHEN** a persona sets one gateway option and the spawning session has others set
- **THEN** the child's resolved gateway options SHALL contain both the persona's option and the session's other options, with the persona's value winning on a shared key

#### Scenario: Unset skills inherit
- **WHEN** a persona does not set a skill list
- **THEN** a subagent started from that persona SHALL have the spawning session's enabled skills enabled

#### Scenario: An empty skill list means no skills
- **WHEN** a persona sets an empty skill list and the spawning session has skills enabled
- **THEN** a subagent started from that persona SHALL have no skills enabled

### Requirement: A persona is captured at subagent start and never re-read
When a subagent is started from a persona, the agent-orchestrator SHALL materialise the resolved persona onto the child at start time: as the child session's model configuration, as the child session's enabled skills, and as a persona snapshot recorded on the child session that carries the resolved system prompt, skill list, tool allowlist, provider, model, the persona's name, and the time of capture. A running or queued child SHALL NOT re-read the persona definition at any later point.

Consequently, editing or deleting a persona SHALL NOT change the behaviour of any subagent already started from it, whether that subagent is running or still queued. A subagent SHALL NOT silently change behaviour mid-game because its persona was edited.

Deleting a persona SHALL be permitted regardless of how many subagents were started from it, precisely because none of them depends on the stored row, and the persona snapshot recorded on each of those children SHALL remain readable afterwards so a past run stays interpretable.

#### Scenario: Persona is materialised onto the child
- **WHEN** a subagent is started from a persona
- **THEN** the child session's model configuration SHALL be the resolved persona's provider, model, and options
- **AND** the child session's enabled skills SHALL be the resolved persona's skills
- **AND** the child session SHALL carry a persona snapshot naming the persona and holding its resolved prompt, skills, and tool allowlist

#### Scenario: Editing a persona does not affect a running subagent
- **WHEN** a persona is edited after a subagent was started from it, changing its prompt, its skills, and its tool allowlist
- **THEN** that subagent SHALL continue to run with the configuration captured at its start, and its persona snapshot SHALL be unchanged

#### Scenario: Deleting a persona does not affect a queued subagent
- **WHEN** a persona is deleted after a subagent was started from it but before that subagent's job begins executing
- **THEN** the subagent SHALL still run with the captured configuration, and its execution SHALL NOT fail for want of the persona row

#### Scenario: Deletion leaves the record of past runs intact
- **WHEN** a persona is deleted
- **THEN** the persona snapshot on every child session started from it SHALL still name that persona and describe what it ran with

### Requirement: A persona narrows a subagent's tools and never widens them
A persona's tool configuration SHALL be an allowlist that can only remove tools from what the child session already exposes. The agent-orchestrator SHALL NOT provide any way for a persona to add a tool, an MCP server, or a provider that the child would not otherwise have.

The allowlist SHALL be applied by filtering the child's resolved MCP tool definitions, and the filter SHALL apply both to the tool list presented to the model and to the mapping used to dispatch a call, so that a tool excluded by a persona cannot be invoked by naming it directly. An unset allowlist SHALL mean no narrowing. A name in the allowlist that the child's catalogue does not contain SHALL have no effect.

MCP servers SHALL always be inherited from the spawning session and SHALL NOT be nameable by a persona. The `load_skill` and `load_skill_reference` built-in tools SHALL always remain available regardless of the allowlist, because a persona's own skill list is unusable without them and they read only from the configured skill roots.

#### Scenario: Allowlist narrows the tool list
- **WHEN** a subagent is started from a persona whose allowlist names one of the tools its session exposes
- **THEN** the tool list presented to that subagent SHALL contain that tool and SHALL NOT contain the session's other MCP tools

#### Scenario: An excluded tool cannot be invoked by name
- **WHEN** a subagent started from a narrowing persona requests a tool that the allowlist excluded
- **THEN** the call SHALL be refused as an unknown tool and SHALL NOT reach the MCP server

#### Scenario: An allowlist cannot add a tool
- **WHEN** a persona's allowlist names a tool that the child session's catalogue does not contain
- **THEN** the child's tool list SHALL NOT contain that tool, and no MCP server SHALL be attached to satisfy it

#### Scenario: No allowlist means no narrowing
- **WHEN** a subagent is started from a persona that sets no tool allowlist
- **THEN** the child SHALL be presented with every MCP tool its session exposes

#### Scenario: Skill tools survive narrowing
- **WHEN** a subagent is started from a persona whose allowlist names no built-in tool
- **THEN** the child SHALL still have `load_skill` and `load_skill_reference` available

### Requirement: A persona's skills are validated when the subagent starts
The agent-orchestrator SHALL re-validate a persona's skill list against the skill catalogue at the moment a subagent is started from it, because the catalogue mirrors the filesystem and a skill can stop existing after the persona was written. A persona naming a skill that cannot be resolved SHALL fail the spawn with an error result that names both the persona and the missing skill, and SHALL NOT create a child session or a child job. An unresolvable skill SHALL NOT be silently dropped.

#### Scenario: A persona naming a vanished skill fails the spawn
- **WHEN** a subagent is started from a persona naming a skill that is no longer in the skill catalogue
- **THEN** the spawn SHALL return an error result naming the persona and the missing skill
- **AND** no child session and no child job SHALL be created

#### Scenario: Naming an unknown persona fails the spawn
- **WHEN** a subagent is started naming a persona that does not exist
- **THEN** the spawn SHALL return an error result naming the requested persona and the personas that are available
- **AND** no child session and no child job SHALL be created

### Requirement: Session default subagent persona
A session SHALL be able to record a default persona for the subagents it spawns, so that a persona can be chosen once for a session rather than named on every spawn. An explicitly named persona SHALL take precedence over the session default. A session with no default and a spawn that names no persona SHALL behave exactly as before personas existed: the child copies the parent's model configuration, skills, and MCP servers and runs the standard subagent prompt.

Setting a session's default to a persona that does not exist SHALL be rejected. Deleting a persona that is a session's default SHALL clear that default rather than leaving the session pointing at a persona that is gone.

#### Scenario: Session default applies when no persona is named
- **WHEN** a session records a default subagent persona and a subagent is spawned without naming one
- **THEN** the child SHALL be configured from the default persona

#### Scenario: A named persona wins over the session default
- **WHEN** a session records a default subagent persona and a subagent is spawned naming a different persona
- **THEN** the child SHALL be configured from the named persona

#### Scenario: No persona anywhere leaves behaviour unchanged
- **WHEN** a session records no default persona and a subagent is spawned without naming one
- **THEN** the child SHALL inherit the parent session's model configuration and enabled skills and SHALL run with no persona snapshot

#### Scenario: Unknown default is rejected
- **WHEN** a client sets a session's default subagent persona to a name that does not exist
- **THEN** the request SHALL be rejected with a client error

#### Scenario: Deleting a persona clears it as a default
- **WHEN** a persona that is a session's default subagent persona is deleted
- **THEN** that session SHALL no longer name it as a default

## MODIFIED Requirements

### Requirement: spawn_subagent creates monitored child jobs without blocking
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, name the child session from the prompt, and return a tool result immediately containing the `child_job_id` and derived `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task SHALL monitor the child job, append the child outcome to the parent job's event log, and terminate the child session when the child reaches a terminal state.

`spawn_subagent` SHALL accept an optional persona name. When a persona applies — either because the call named one or because the parent session records a default subagent persona — the child SHALL be configured from the resolved persona instead of from a plain copy of the parent's model config and skills, and the persona SHALL be captured onto the child at that moment. MCP servers SHALL be inherited from the parent either way. When no persona applies the child SHALL be configured exactly as before: a copy of the parent's model config and skill assignments.

The monitor SHALL resolve the child's outcome the same way `wait_for_subagent` does — from the child's persisted status, with live events short-circuiting the wait — so the reported outcome is the child's actual fate and not a timeout observed because no event was ever published. The `reason` on a `subagent_failed` event SHALL be the terminal status the child reached (`failed`, `cancelled`) or why the monitor stopped observing, and SHALL carry the child's `error_code` and `error_message` when it has them. A child that ended `"interrupted"` produced usable partial work and SHALL be reported as `subagent_completed`.

#### Scenario: Child session created and configured
- **WHEN** `spawn_subagent` is called with a valid prompt
- **THEN** the worker SHALL create a new `AgentSession` via the repository
- **THEN** the worker SHALL name the child session with the first 50 characters of the prompt, truncated without ellipsis
- **THEN** the worker SHALL copy the parent session's model config and skill assignments

#### Scenario: Child job enqueued with parent reference
- **WHEN** the child session is configured
- **THEN** the worker SHALL enqueue a prompt job with `parent_job_id` pointing to the current parent job
- **THEN** the child job SHALL begin running concurrently via `asyncio.create_task`

#### Scenario: spawn_subagent returns immediately
- **WHEN** the child job is enqueued and started
- **THEN** `spawn_subagent` SHALL return a tool result immediately with `child_job_id` and `name` without waiting for the child to finish
- **THEN** the parent agent SHALL continue its own reasoning and may spawn additional subagents

#### Scenario: subagent_started payload includes name
- **WHEN** `spawn_subagent` emits `subagent_started`
- **THEN** the event payload SHALL include `child_job_id`, `child_session_id`, and `name`

#### Scenario: Child configured from a named persona
- **WHEN** `spawn_subagent` is called naming an existing persona
- **THEN** the child session SHALL be configured from that persona's resolved provider, model, options, and skills
- **AND** the `subagent_started` event payload SHALL name the persona the child was started from

#### Scenario: Background task monitors child and emits outcome
- **WHEN** the child job reaches a terminal state
- **THEN** a background coroutine SHALL append `subagent_completed` or `subagent_failed` to the parent job's event log
- **THEN** the background coroutine SHALL terminate the child session

#### Scenario: Monitor reports the child's real failure
- **WHEN** a child job crashes
- **THEN** the `subagent_failed` event on the parent job SHALL carry `reason: "failed"` together with the child's `error_code` and `error_message`

### Requirement: Subagent jobs use a dedicated system prompt
Subagent jobs SHALL receive a system prompt distinct from the master job prompt.

A subagent started from a persona SHALL additionally receive that persona's system prompt as its own clearly delimited section of the assembled prompt. The persona prompt SHALL be treated purely as text: it SHALL be concatenated into the message body and SHALL NOT be used as a format string or interpolated into any context where text becomes code, a query, or a shell command. The persona prompt SHALL NOT determine which tools the subagent has, because tool availability is decided from the job's own configuration.

#### Scenario: Subagent receives subagent-specific prompt
- **WHEN** a job with a non-null `parent_job_id` starts execution
- **THEN** the system prompt SHALL be built from `SUBAGENT_SYSTEM_PROMPT_PARTS`
- **THEN** the prompt SHALL state the agent is a subagent spawned for a focused task

#### Scenario: Subagent prompt permits large-payload tools
- **WHEN** the subagent system prompt is constructed
- **THEN** it SHALL explicitly permit direct calls to `get_game_state`, `search_cards_marvel_champions`, and other large-payload tools
- **THEN** it SHALL instruct the subagent to extract only required data

#### Scenario: Subagent prompt blocks nesting
- **WHEN** the subagent system prompt is constructed
- **THEN** it SHALL state the subagent does not have `spawn_subagent` or `wait_for_subagent`
- **THEN** it SHALL instruct the subagent to complete work directly rather than delegating

#### Scenario: Master job receives master prompt
- **WHEN** a job with a null `parent_job_id` starts execution
- **THEN** the system prompt SHALL be built from `BASE_SYSTEM_PROMPT_PARTS`

#### Scenario: Persona prompt is included as its own section
- **WHEN** a subagent started from a persona begins execution
- **THEN** its system prompt SHALL contain the persona's prompt as a delimited section in addition to the subagent prompt parts

#### Scenario: A persona prompt cannot grant a tool
- **WHEN** a persona's prompt instructs the model to use a tool that the persona's allowlist excluded, or to spawn a subagent
- **THEN** that tool SHALL still be absent from the subagent's tool list, because tool availability is computed from configuration rather than read from the prompt
