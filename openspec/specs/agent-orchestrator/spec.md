# Agent Orchestrator Spec

## Purpose

This spec describes the agent orchestration service for DragnCardsAI, including session management, background prompt execution, provider integration through Bifrost, MCP tool usage, and streaming job events.
## Requirements
### Requirement: Agent session lifecycle API
The system SHALL expose HTTP endpoints to create, retrieve, list, update, and terminate agent sessions used to run LLM-driven DragnCards gameplay.

Session representations returned by those endpoints SHALL include the session's multi-turn memory settings, including whether memory replay is enabled and any configured replay limits that affect prompt-context construction.

Those replay settings SHALL include the configured recent-message limit and recent-tool-exchange limit used when reconstructing prompt context.

#### Scenario: Create agent session
- **WHEN** a client submits a valid request to create an agent session
- **THEN** the system SHALL persist the session and return its identifier, lifecycle status, and configuration summary

#### Scenario: Retrieve agent session
- **WHEN** a client requests an existing agent session by identifier
- **THEN** the system SHALL return the persisted session state, model configuration, assigned skills, assigned MCPs, replay settings, and recent job summary

#### Scenario: Terminate agent session
- **WHEN** a client terminates an active agent session
- **THEN** the system SHALL mark the session terminated and prevent new prompt jobs from being accepted for that session

### Requirement: Agent session deletion
The system SHALL expose an HTTP endpoint to permanently delete an agent session, removing the session together with every record stored under it: its model configuration, enabled skills, MCP assignments, player configurations, jobs, transcript events, job outputs, and compaction records.

Deletion SHALL return no content on success and SHALL report an unknown session as not found, including on a repeated deletion of the same session.

Deletion SHALL terminate before it deletes: cancellation SHALL be requested for any queued or running job in the session before its rows are removed, so an executing worker observes the cancellation rather than discovering that its records have disappeared.

Deletion SHALL be scoped to the session: global skill and MCP registries, and any other session, SHALL be unaffected. Jobs belonging to other sessions that reference a deleted job SHALL have that reference cleared rather than left dangling.

Every dependent row SHALL be removed explicitly rather than relying on database-level cascade behaviour, so that no transcript, compaction, or configuration row can be orphaned on a backend that does not enforce the declared foreign keys.

Terminating a session SHALL remain distinct from deleting it: termination ends the session while preserving its history, and only deletion removes that history.

#### Scenario: Delete a session and its history
- **WHEN** a client deletes an existing agent session
- **THEN** the system SHALL remove the session with its model configuration, enabled skills, MCP assignments, player configurations, jobs, transcript events, outputs, and compaction records, and SHALL return a no-content response
- **AND** subsequent requests for that session or for its jobs SHALL report them as not found

#### Scenario: Delete a session that is still executing
- **WHEN** a client deletes a session that has a queued or running job
- **THEN** the system SHALL request cancellation of that job before removing the session, and SHALL still complete the deletion

#### Scenario: Delete an unknown session
- **WHEN** a client deletes a session identifier that does not exist, or deletes the same session twice
- **THEN** the system SHALL respond that the session was not found

#### Scenario: Deletion leaves other sessions intact
- **WHEN** a client deletes one session while other sessions exist
- **THEN** the other sessions and their jobs SHALL remain retrievable, the global skill and MCP registries SHALL be unchanged, and any job in another session that referenced a deleted job SHALL have that reference cleared

### Requirement: Model and provider configuration
The system SHALL allow each agent session to configure the model provider, model name, gateway options, and provider-specific non-secret settings used for prompt execution.

Provider model listings SHALL be cached in Valkey (not in process memory) so that all replicas share a consistent cache. The cache TTL SHALL be controlled by `PROVIDER_MODELS_CACHE_TTL_SECONDS`. When Valkey is unavailable, the system SHALL fall through to a live Bifrost fetch and SHALL NOT raise an error to the caller.

`BifrostClient` SHALL NOT hold any mutable in-process state after construction. In particular, `self._models_cache` and `self._all_models_cache` SHALL NOT exist.

#### Scenario: Configure supported provider
- **WHEN** a client configures a session with one of OpenRouter, Mistral, Claude, OpenAI, LM Studio, or Gemini
- **THEN** the system SHALL persist the provider configuration and validate that the provider is known to the Bifrost gateway configuration

#### Scenario: Reject unsupported provider
- **WHEN** a client configures a session with an unknown provider identifier
- **THEN** the system SHALL reject the request with a validation error and SHALL NOT change the session model configuration

#### Scenario: Model listing served from shared Valkey cache
- **WHEN** two replicas of the agent-orchestrator both call `list_models` for the same provider within the TTL window
- **THEN** the second call SHALL receive the cached value from Valkey and SHALL NOT issue a new HTTP request to Bifrost

### Requirement: Valkey-backed model listing cache
The model cache SHALL store provider model listings in Valkey using native key TTL so that all replicas share a single consistent cache.

Each cached entry SHALL be stored as a JSON-serialised list of model objects under a namespaced key and SHALL expire automatically after `PROVIDER_MODELS_CACHE_TTL_SECONDS` seconds.

The cache SHALL use the following key schema:
- Per-provider listing: `agent-orchestrator:model-cache:provider:<provider_id>`
- All-models listing: `agent-orchestrator:model-cache:all`

#### Scenario: Cache hit for provider listing
- **WHEN** `list_models` is called for a `provider_id` whose Valkey key has not yet expired
- **THEN** the system SHALL return the cached model list without issuing any HTTP request to Bifrost

#### Scenario: Cache miss triggers live fetch
- **WHEN** `list_models` is called for a `provider_id` whose Valkey key is absent or expired
- **THEN** the system SHALL fetch the listing from Bifrost, store the result in Valkey with `SETEX`, and return the result

#### Scenario: Cache hit for all-models listing
- **WHEN** `_fetch_all_models` is called and the `agent-orchestrator:model-cache:all` key has not expired
- **THEN** the system SHALL return the cached model list without issuing any HTTP request

#### Scenario: Valkey unavailability falls through to live fetch
- **WHEN** Valkey is unavailable and `list_models` or `_fetch_all_models` is called
- **THEN** the system SHALL log a warning and fall through to fetch the listing live from Bifrost, returning the result without caching

#### Scenario: Caching disabled via zero TTL
- **WHEN** `PROVIDER_MODELS_CACHE_TTL_SECONDS` is set to `0`
- **THEN** the system SHALL skip all Valkey read and write operations and always fetch live from Bifrost

### Requirement: Shared Valkey connection module
The low-level Valkey RESP connection SHALL be extracted into a shared module (`storage/valkey.py`) so that it can be reused across `ValkeyLiveEventBus` and `BifrostClient` without duplication.

The connection class SHALL be named `RespConnection` (public, no leading underscore) and SHALL expose an `aclose()` method for lifecycle consistency. The `RespConnection` instance created for `BifrostClient` SHALL be explicitly closed during application lifespan teardown.

#### Scenario: Live event bus uses shared connection
- **WHEN** `ValkeyLiveEventBus` is constructed
- **THEN** it SHALL obtain a `RespConnection` from the shared module and operate identically to before the extraction

#### Scenario: BifrostClient uses shared connection
- **WHEN** `BifrostClient` is constructed with a non-None Valkey connection
- **THEN** it SHALL use the shared `RespConnection` to read and write cache keys

#### Scenario: Valkey connection closed on shutdown
- **WHEN** the application lifespan exits
- **THEN** the `RespConnection` created for `BifrostClient` SHALL have `aclose()` called in the teardown `finally` block

### Requirement: Smoke-model provider configuration
The agent-orchestrator SHALL support a local smoke-test model configuration that can target a repo-local `llama.cpp` server through the same session model configuration flow used for other providers.

The smoke-model configuration SHALL be expressible through non-secret environment-backed provider metadata and session model configuration fields rather than hard-coded test logic in the worker.

#### Scenario: Configure a session for the local smoke model
- **WHEN** a client configures an agent session for the documented smoke-test provider and model
- **THEN** the agent-orchestrator SHALL persist that model configuration and use it for prompt execution without requiring hosted-provider credentials

#### Scenario: Smoke-model configuration survives normal session retrieval
- **WHEN** a client retrieves a session configured for the local smoke model
- **THEN** the returned session detail SHALL include the persisted provider, model, and non-secret options needed to understand the smoke configuration

#### Scenario: Smoke session can use default game-service MCP
- **WHEN** a session is configured for the local smoke model
- **THEN** the session SHALL still expose the default `game-service` MCP tools needed for prompt-driven game creation

### Requirement: Multi-turn memory session flag
The agent-orchestrator SHALL support a `multi_turn_memory` boolean flag on `AgentSession` (default `true`). When `false`, job workers SHALL build a fresh messages list with no replay of prior job events, preserving existing behavior.

#### Scenario: Session created with multi-turn memory enabled
- **WHEN** a session is created without specifying `multi_turn_memory`
- **THEN** `multi_turn_memory` SHALL default to `true`

#### Scenario: Session created with multi-turn memory disabled
- **WHEN** a session is created with `multi_turn_memory: false`
- **THEN** each job for that session SHALL start with a fresh messages list containing only the current system prompt and user input

### Requirement: Skill assignment
The system SHALL allow clients to assign and remove skills from `@skills/` for an agent session, discovered from environment-configured skill roots using the directory shape `skills/<skill_name>`.

The system SHALL maintain a persistent registry of known skills in PostgreSQL. On startup it SHALL upsert every skill discovered in the configured skill roots into that registry, so the registry reflects what is on disk rather than only the skills some session has already enabled. The sync SHALL be idempotent and SHALL NOT delete registry rows for skills that are no longer on disk, because existing session assignments reference them.

Any skill that resolves in the configured skill roots SHALL be enablable for a session, whether or not it has been enabled before and whether or not it was present at startup. A request that enables a skill SHALL register it first when it is not already registered.

Disabling a skill for a session SHALL be idempotent: when the skill is already disabled, was never enabled, or cannot be resolved at all, the system SHALL report success without changing state, because the session is already in the requested state. A request that targets a session that does not exist SHALL still be rejected as not found.

A session's assigned skills SHALL be reported consistently across endpoints: the session summary, the session detail, and the session skill list SHALL each include only the skills currently enabled for that session, and SHALL NOT report a disabled skill as assigned.

#### Scenario: Assign known skill
- **WHEN** a client assigns a skill identifier that exists under `skills/<skill_name>` in a configured skill root
- **THEN** the system SHALL persist the skill assignment for the session

#### Scenario: Reject unknown skill
- **WHEN** a client assigns a skill identifier that cannot be resolved from configured skill roots
- **THEN** the system SHALL reject the assignment and SHALL NOT persist it

#### Scenario: On-disk skills are registered at startup
- **WHEN** the agent-orchestrator starts with skills present in its configured skill roots
- **THEN** it SHALL upsert a registry row for each discovered skill, recording its path and summary
- **AND** starting again SHALL leave the registry in the same state

#### Scenario: Enable a skill that has never been enabled before
- **WHEN** a client enables a skill that resolves in a configured skill root but has no registry row
- **THEN** the system SHALL register that skill and persist the assignment
- **AND** SHALL NOT reject the request as not found

#### Scenario: Disable a skill that is already disabled
- **WHEN** a client disables a skill that a session has already disabled, or has never enabled
- **THEN** the system SHALL report success and leave the session's skills unchanged

#### Scenario: Disable a skill on a session that does not exist
- **WHEN** a client disables a skill for an unknown session id
- **THEN** the system SHALL reject the request as not found

#### Scenario: A disabled skill is not reported as assigned
- **WHEN** a client disables a skill for a session and then reads that session
- **THEN** the session summary, the session detail, and the session skill list SHALL all omit that skill

### Requirement: System prompt construction uses skill summaries
The worker SHALL build the system prompt by including only a short skill summary for each assigned skill rather than the full `SKILL.md` content. Full skill content SHALL be delivered on demand through the built-in skill-loading tools.

Only skills currently enabled for the session SHALL be treated as assigned. A disabled skill SHALL NOT appear in the system prompt, SHALL NOT be loadable through the skill-loading built-ins, SHALL NOT be counted in the session's context-usage estimate, and SHALL NOT be inherited by a subagent or player agent.

#### Scenario: System prompt with assigned skills
- **WHEN** a job starts with skills assigned to the session
- **THEN** the system prompt SHALL contain an "Available skills" section listing each skill name and summary
- **THEN** the system prompt SHALL instruct the agent to call `load_skill` before using a skill and `load_skill_reference` only for the specific reference files it chooses to inspect
- **THEN** the system prompt SHALL NOT include the full body of any assigned `SKILL.md`

#### Scenario: System prompt with no assigned skills
- **WHEN** a job starts with no skills assigned
- **THEN** the system prompt SHALL contain the base identity and tool-usage instructions only

#### Scenario: Disabled skill withdrawn from the agent
- **WHEN** a job starts for a session that has one enabled skill and one disabled skill
- **THEN** the system prompt SHALL list only the enabled skill
- **AND** the disabled skill SHALL NOT be loadable through `load_skill`

### Requirement: MCP assignment
The system SHALL maintain a global registry of MCP servers accessible to all sessions. Sessions SHALL enable and disable MCPs from this registry to make them available for tool calls.

#### Scenario: Assign game-service MCP
- **WHEN** a client enables the game-service MCP for an agent session
- **THEN** prompt jobs for that session SHALL be able to call the game-service MCP tools during orchestration

#### Scenario: Inspect MCP assignments
- **WHEN** a client retrieves an agent session
- **THEN** the response SHALL include all registered MCPs with their enabled and disabled state for that session

#### Scenario: Default MCP available immediately
- **WHEN** a client creates or later loads an agent session
- **THEN** non-custom default MCPs such as `game-service` SHALL already be enabled for that session

#### Scenario: SSE transport supported
- **WHEN** an MCP is configured with transport `sse`
- **THEN** the system SHALL connect using SSE transport rather than streamable-http

### Requirement: Global MCP registry management
The system SHALL expose CRUD endpoints for managing the global MCP registry.

#### Scenario: List all registered MCPs
- **WHEN** a client requests `GET /mcps`
- **THEN** the system SHALL return all MCPs in the global registry

#### Scenario: Add new MCP to registry
- **WHEN** a client submits `POST /mcps` with valid name, transport, and server_url
- **THEN** the system SHALL create the MCP entry and return its details

#### Scenario: Remove MCP from registry
- **WHEN** a client submits `DELETE /mcps/{mcp_name}`
- **THEN** the system SHALL remove the MCP from the registry

#### Scenario: Non-custom MCP registry cannot be removed
- **WHEN** a client submits `DELETE /mcps/{mcp_name}` for a non-custom default MCP
- **THEN** the system SHALL reject the request instead of deleting that registry entry

### Requirement: Default game-service MCP
The system SHALL auto-create a default game-service MCP entry on startup using the configured URL.

#### Scenario: Default MCP exists after startup
- **WHEN** the agent-orchestrator starts
- **THEN** a game-service MCP entry SHALL exist in the registry with the URL from `game_service_mcp_url` config

### Requirement: Session MCP enablement
Sessions SHALL see all registered MCPs. Custom registries SHALL require explicit enablement, while non-custom default registries SHALL be enabled automatically.

#### Scenario: Session lists MCPs with enablement state
- **WHEN** a client requests `GET /sessions/{session_id}/mcps`
- **THEN** the response SHALL include all registered MCPs with their enabled and disabled state for that session

#### Scenario: Enable MCP for session
- **WHEN** a client submits `PATCH /sessions/{session_id}/mcps/{mcp_name}` with `{"enabled": true}`
- **THEN** the system SHALL enable the MCP for that session

#### Scenario: Session-scoped MCP add remains supported
- **WHEN** a client submits `POST /sessions/{session_id}/mcps` with a valid MCP payload
- **THEN** the system SHALL upsert that MCP in the global registry and enable it for the session

#### Scenario: Session-scoped MCP delete disables assignment
- **WHEN** a client submits `DELETE /sessions/{session_id}/mcps/{mcp_name}`
- **THEN** the system SHALL disable that MCP for the session without removing the global registry entry

#### Scenario: Disabled MCP tools not available
- **WHEN** a session has an MCP disabled
- **THEN** the MCP tools SHALL NOT be included in tool definitions for that session

### Requirement: Child session MCP inheritance
When spawning a subagent, the child session SHALL inherit enabled MCPs from the parent.

#### Scenario: Spawn subagent copies enabled MCPs
- **WHEN** `spawn_subagent` is called
- **THEN** the child session SHALL have the same MCPs enabled as the parent

### Requirement: Prompt submission creates background jobs
The system SHALL expose an endpoint to submit prompts to an agent session and SHALL execute the resulting orchestration work only through background jobs.

Recoverable provider and tool-execution failures SHALL be recorded on the current attempt and SHALL re-queue the job when retry policy allows another attempt.

Invalid tool invocations from the model SHALL be surfaced back to the model as error tool results and SHALL NOT fail the job attempt by themselves.

#### Scenario: Submit prompt
- **WHEN** a client submits a prompt to an active agent session
- **THEN** the system SHALL persist a prompt run, enqueue a background job, and return the job identifier without waiting for LLM execution to complete

#### Scenario: Reject prompt for terminated session
- **WHEN** a client submits a prompt to a terminated agent session
- **THEN** the system SHALL reject the prompt and SHALL NOT enqueue a job

#### Scenario: Retry recoverable execution failure
- **WHEN** a background job attempt fails with a retryable provider timeout, provider rate limit, or MCP transport failure and remaining attempts are available
- **THEN** the system SHALL persist the failed attempt details
- **AND** SHALL return the job to the queue for another attempt instead of marking the job terminally failed

#### Scenario: Stop after non-retryable execution failure
- **WHEN** a background job attempt fails because of an unknown local tool, invalid persisted session configuration, or another non-retryable execution error
- **THEN** the system SHALL mark the job failed without re-queueing it

#### Scenario: Invalid tool invocation returned to model
- **WHEN** the model requests a tool that is unknown, unavailable to the session, or malformed in a way the worker can describe locally
- **THEN** the worker SHALL append an error `tool_result` describing the problem
- **AND** SHALL continue orchestration without failing the job attempt solely because of that invalid tool request

### Requirement: A prompt can load skill content into its own turn
The prompt submission endpoint SHALL accept the names of skills whose full content the prompt loads into its own turn, and SHALL record them on the enqueued job so the worker can act on them.

Each named skill SHALL resolve in the configured skill roots; a name that does not SHALL be rejected as a bad request and SHALL NOT enqueue a job. The number of skills one prompt may load SHALL be bounded, and a request exceeding that bound SHALL be rejected as a bad request. Repeated names SHALL be recorded once, in the order first given.

The names the worker acts on SHALL be the validated ones. A client SHALL NOT be able to smuggle unvalidated skill names past this validation through free-form job metadata.

When a job names no skills, prompt submission SHALL behave exactly as before.

#### Scenario: Submit a prompt that loads a skill
- **WHEN** a client submits a prompt naming a skill that resolves in a configured skill root
- **THEN** the system SHALL enqueue the job and record that skill against it

#### Scenario: Reject a prompt naming an unknown skill
- **WHEN** a client submits a prompt naming a skill that cannot be resolved from the configured skill roots
- **THEN** the system SHALL reject the request as a bad request and SHALL NOT enqueue a job

#### Scenario: Reject a prompt loading too many skills
- **WHEN** a client submits a prompt naming more skills than one prompt may load
- **THEN** the system SHALL reject the request as a bad request and SHALL NOT enqueue a job

#### Scenario: Duplicate names collapse
- **WHEN** a client submits a prompt naming the same skill twice
- **THEN** the system SHALL record that skill once

#### Scenario: Metadata cannot forge the loaded skill list
- **WHEN** a client submits a prompt whose free-form metadata carries the key the system uses to record loaded skills
- **THEN** the system SHALL record only the validated names from the request's own skill list

### Requirement: Skills loaded by a prompt are delivered in that turn's user message
When a job records skills loaded by its prompt, the worker SHALL place each skill's full content — `SKILL.md` plus the inventory of its reference files, the same payload the `load_skill` built-in returns — ahead of the user's text inside that turn's user message, and SHALL tell the model those instructions are already present so it does not load them again.

The stored job prompt SHALL remain exactly the text the client submitted. Skill content SHALL NOT be written into it, so the transcript, the session name derived from a first prompt, and the replayed message history are unaffected — a later turn replays the typed text only, and the skill's content occupies context on the turn that loaded it and no other.

A recorded skill that no longer resolves on disk SHALL be skipped rather than failing the job.

For each skill actually loaded this way the worker SHALL record and publish a `skill_loaded` event carrying the skill name and its reference-file count, the same event a `load_skill` call produces, so the transcript shows the load.

The system prompt SHALL be unaffected: it still advertises assigned skills by summary only.

#### Scenario: Loaded skill content precedes the user's text
- **WHEN** a job whose prompt loaded a skill starts
- **THEN** that turn's user message SHALL contain the skill's `SKILL.md` content followed by the text the user submitted

#### Scenario: The stored prompt stays as typed
- **WHEN** a job whose prompt loaded a skill has run
- **THEN** the job's stored prompt SHALL be exactly the submitted text, with no skill content in it

#### Scenario: Loading is not repeated on later turns
- **WHEN** a later job in the same session replays that earlier turn from history
- **THEN** the replayed user message SHALL be the typed text only, without the loaded skill's content

#### Scenario: A load emits a skill_loaded event
- **WHEN** a job's prompt loads a skill
- **THEN** the system SHALL record and publish a `skill_loaded` event naming that skill

#### Scenario: A skill that vanished from disk is skipped
- **WHEN** a job records a skill that no longer resolves in the configured skill roots
- **THEN** the worker SHALL run the turn without that skill's content and SHALL NOT fail the job

### Requirement: Worker loop executes jobs concurrently
The worker loop SHALL claim queued jobs as fast as they become available and execute each one as a non-blocking `asyncio` task. There is no upper bound on the number of jobs that may run in parallel within a single process. The loop SHALL NOT await job completion before claiming the next job.

All tasks — both top-level jobs and child jobs spawned by `spawn_subagent` — SHALL be tracked in a shared task set so that graceful shutdown can cancel and await them.

#### Scenario: Top-level jobs run concurrently
- **WHEN** multiple prompt jobs are queued
- **THEN** the worker loop SHALL claim and start each job as a background task without waiting for prior jobs to finish

#### Scenario: Graceful shutdown cancels all in-flight tasks
- **WHEN** the worker receives a stop signal
- **THEN** it SHALL cancel all in-flight job tasks (top-level and child) and await their completion before exiting

### Requirement: Prompt execution is owned by one prompt-run Module
The agent-orchestrator SHALL execute each prompt job through one prompt-run Module whose Interface owns tool rounds, cancellation checkpoints, event emission, and terminal job outcomes.

The worker loop SHALL remain responsible for claiming work and delegating execution, but SHALL NOT duplicate prompt-run lifecycle semantics outside that Module.

#### Scenario: Worker loop delegates prompt execution
- **WHEN** a queued prompt job or queued child prompt job is claimed for execution
- **THEN** the worker loop SHALL delegate execution through the same prompt-run Module Interface

#### Scenario: Prompt-run Module owns terminal job handling
- **WHEN** prompt execution completes, fails, or is cancelled
- **THEN** the prompt-run Module SHALL emit the final orchestration events and terminal job outcome through one Implementation path

### Requirement: Subagent jobs persist parent job reference
The `jobs` table SHALL include a nullable `parent_job_id` foreign key referencing `jobs.id`. Jobs created by the `spawn_subagent` built-in tool SHALL have this field set to the spawning job's id. Jobs created through normal prompt submission SHALL have it set to null.

#### Scenario: Master job has null parent_job_id
- **WHEN** a prompt job is created via the normal prompt submission endpoint
- **THEN** its `parent_job_id` SHALL be null

#### Scenario: Child job has parent_job_id set
- **WHEN** a job is created as a result of a `spawn_subagent` tool call
- **THEN** its `parent_job_id` SHALL reference the spawning job's id

### Requirement: Built-in tool dispatch in worker loop
The worker SHALL maintain a registry of built-in tools that are dispatched locally before MCP tool lookup. Built-in tools SHALL appear in the tool list presented to the LLM alongside MCP tools. When the LLM calls a built-in tool the worker SHALL handle it locally and emit `tool_call` and `tool_result` events using `assignment="builtin"` and `server_url=null`.

The worker SHALL determine whether a job is a master job by checking `parent_job_id is null AND job_type = "prompt"`. The `spawn_subagent` tool SHALL be included in the tool list only for master jobs.

#### Scenario: Built-in tool called by LLM
- **WHEN** the LLM invokes a tool name that matches a registered built-in
- **THEN** the worker SHALL execute the built-in handler locally
- **THEN** the worker SHALL append a `tool_call` event with `assignment="builtin"` and a `tool_result` event with the handler's output before continuing the tool round

#### Scenario: Skill loading built-ins available on all jobs
- **WHEN** the worker builds the built-in tool registry for any job type
- **THEN** both `load_skill` and `load_skill_reference` SHALL be present in the tool definitions sent to the LLM

#### Scenario: Built-in tool name takes precedence over MCP tool
- **WHEN** the LLM invokes a tool name that matches a built-in and an MCP tool with the same name
- **THEN** the built-in handler SHALL take precedence and no MCP call SHALL be made

#### Scenario: spawn_subagent omitted for child jobs
- **WHEN** a job has a non-null `parent_job_id`
- **THEN** `spawn_subagent` SHALL NOT appear in the tool definitions sent to the LLM

#### Scenario: spawn_subagent omitted for compaction jobs
- **WHEN** a job has `job_type = "compaction"`
- **THEN** `spawn_subagent` SHALL NOT appear in the tool definitions sent to the LLM

### Requirement: spawn_subagent creates monitored child jobs without blocking
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, give the child session a generated display name, and return a tool result immediately containing the `child_job_id` and that `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task SHALL monitor the child job, append the child outcome to the parent job's event log, and terminate the child session when the child reaches a terminal state.

The child's name SHALL be generated rather than taken from the prompt, and SHALL be seeded on the child session's own identifier so that no two children share a codename. The name SHALL be stored on the child session and SHALL be the same string in the `subagent_started` event, in the outcome event the monitor appends, and in the tool result — generated once, never recomputed. A caller that supplies a name for the child SHALL have that name used instead; this is how a player agent keeps its seat's own display name.

`spawn_subagent` SHALL accept an optional persona name. When a persona applies — either because the call named one or because the parent session records a default subagent persona — the persona SHALL first be checked against the spawning session's subagent allowlist and SHALL be refused when it is not permitted. When it is permitted, the child SHALL be configured from the resolved persona instead of from a plain copy of the parent's model config and skills, and the persona SHALL be captured onto the child at that moment. MCP servers SHALL be inherited from the parent either way. When no persona applies the child SHALL be configured exactly as before: a copy of the parent's model config and skill assignments, unaffected by the allowlist.

The monitor SHALL resolve the child's outcome the same way `wait_for_subagent` does — from the child's persisted status, with live events short-circuiting the wait — so the reported outcome is the child's actual fate and not a timeout observed because no event was ever published. The `reason` on a `subagent_failed` event SHALL be the terminal status the child reached (`failed`, `cancelled`) or why the monitor stopped observing, and SHALL carry the child's `error_code` and `error_message` when it has them. A child that ended `"interrupted"` produced usable partial work and SHALL be reported as `subagent_completed`.

#### Scenario: Child configured from a named persona
- **WHEN** `spawn_subagent` is called naming a persona the session allows
- **THEN** the child session SHALL be configured from that persona's resolved provider, model, options, and skills
- **AND** the `subagent_started` event payload SHALL name the persona the child was started from

#### Scenario: Child spawned without a persona
- **WHEN** `spawn_subagent` is called with no persona and the session records no default
- **THEN** the child SHALL be configured from a copy of the parent's model config and skill assignments
- **AND** the spawn SHALL succeed whatever the session's allowlist contains

### Requirement: Prior job event replay
When `multi_turn_memory` is enabled, the job worker SHALL replay prior job events for the session into the messages list before the current user prompt.

Eligible jobs for replay are those with status `"completed"`, `"interrupted"`, or `"failed"` (excluding `"cancelled"` and the current job itself).

Replay order SHALL be: for each prior job in chronological order — user prompt, assistant output, tool calls and results interleaved, optional synthetic status note (for non-completed jobs), then continue to next job.

If a `CompactionRecord` exists for the session, the worker SHALL:
1. Inject the compaction summary as a system message
2. Replay only jobs created **after** the `CompactionRecord.covers_up_to_job_id`

If replay limits are configured on the session, the worker SHALL apply them after reconstructing the eligible message history:
1. `context_recent_message_limit` bounds the number of replayed prior conversational messages by recency
2. `context_recent_tool_exchange_limit` bounds the number of replayed prior tool exchanges by recency
3. A tool exchange SHALL include both the assistant tool call and its matching tool result
4. Compaction summary messages SHALL NOT count against either limit

#### Scenario: No prior jobs, no compaction record
- **WHEN** a job starts for a session with no prior jobs and `multi_turn_memory: true`
- **THEN** the messages list SHALL contain only the system prompt and current user prompt

#### Scenario: Prior jobs exist, no compaction record
- **WHEN** a job starts for a session with N prior completed jobs and no `CompactionRecord`
- **THEN** the messages list SHALL begin with the system prompt, followed by all prior job events replayed in order, then the current user prompt

#### Scenario: Prior interrupted job replayed with synthetic note
- **WHEN** a job starts and the immediately prior job has status `"interrupted"`
- **THEN** the interrupted job's events SHALL be replayed, followed by the synthetic interruption note, before the current user prompt

#### Scenario: Compaction record exists
- **WHEN** a job starts and a `CompactionRecord` exists for the session
- **THEN** the messages list SHALL begin with the original system prompt, then the compaction summary as a second system message, then only events from jobs after `covers_up_to_job_id`, then the current user prompt

#### Scenario: Replay history limited by message count
- **WHEN** a session has `context_recent_message_limit` configured and eligible conversational history exceeds that count
- **THEN** the worker SHALL include only the most recent replayable conversational messages up to the configured limit before appending the current user prompt

#### Scenario: Replay history limited by tool exchanges
- **WHEN** a session has `context_recent_tool_exchange_limit` configured and eligible replay history contains more tool exchanges than allowed
- **THEN** the worker SHALL include only the most recent replayable tool exchanges up to the configured limit
- **AND** SHALL retain each included exchange as an assistant tool call plus its matching tool result

#### Scenario: State-heavy exchanges displaced by newer state-heavy exchanges
- **WHEN** replay history contains multiple state-heavy game-service tool exchanges and the configured tool-exchange budget cannot include all of them
- **THEN** the worker SHALL favor the newest state-heavy exchange over older state-heavy exchanges
- **AND** SHALL use remaining tool-exchange budget for other recent exchanges when available

### Requirement: Interrupted job terminal status
When the tool round limit is reached and the job has not produced a final text-only response, the worker SHALL mark the job with status `"interrupted"` (not `"failed"`). The worker SHALL:
1. Publish a `"completion"` event with a message explaining the interruption and asking the user to send a follow-up.
2. Call `mark_job_interrupted` on the repository, which sets `status = "interrupted"`, `error_code = "tool_round_limit"`, and `result_text` to the interruption message.
3. Return normally (not raise an exception).

The `"interrupted"` status SHALL be included in `TERMINAL_JOB_STATUSES`.

#### Scenario: Tool round limit hit produces interrupted job
- **WHEN** a job exhausts `worker_max_tool_rounds` iterations without returning a text-only response
- **THEN** the job status SHALL be `"interrupted"` with `error_code = "tool_round_limit"`
- **AND** a `"completion"` SSE event SHALL be published with the interruption message

#### Scenario: Interrupted job is not retried
- **WHEN** a job is marked `"interrupted"`
- **THEN** it SHALL NOT be re-queued regardless of `max_attempts`

### Requirement: Interrupted and failed jobs included in context replay
When `multi_turn_memory` is enabled, the worker SHALL include `"interrupted"` and `"failed"` jobs (in addition to `"completed"` jobs) when replaying prior job events. `"cancelled"` jobs SHALL remain excluded.

After reconstructing the event replay items for a non-completed job, the worker SHALL append a synthetic `role: assistant` message:
- For `"interrupted"` jobs: `"[Previous turn was interrupted by the tool round limit. The partial work above is preserved. Continue from where this left off.]"`
- For `"failed"` jobs: `"[Previous turn failed before completing. Partial tool calls above may be incomplete. Resume the task taking the partial work into account.]"`

#### Scenario: Interrupted job partial work replayed
- **WHEN** a new job starts and the prior job has status `"interrupted"`
- **THEN** the prior job's tool calls and tool results SHALL be replayed into the messages list
- **AND** a synthetic assistant note SHALL follow indicating the interruption

#### Scenario: Failed job partial work replayed
- **WHEN** a new job starts and the prior job has status `"failed"`
- **THEN** the prior job's tool calls and tool results SHALL be replayed into the messages list
- **AND** a synthetic assistant note SHALL follow indicating the failure

#### Scenario: Cancelled job still excluded from replay
- **WHEN** a new job starts and a prior job has status `"cancelled"`
- **THEN** that prior job's events SHALL NOT appear in the messages list

### Requirement: Crashed prompt runs reach a terminal status
The worker SHALL drive every claimed prompt job to a terminal status no matter which error is raised while executing it. This includes error types the worker does not explicitly classify — for example timeouts, `ExceptionGroup` wrappers raised by task groups, and programming errors — and errors raised before the first model call, such as while loading the job, reading its model configuration, or checking for cancellation.

Any such error SHALL be classified, persisted as a `failure` event, and applied through job failure handling so the job ends as `"failed"` (or is re-queued when the classified failure is retryable and attempts remain). A prompt job SHALL NOT be left in the non-terminal `"running"` status because of an unhandled error. `asyncio.CancelledError` SHALL remain uncaught so worker shutdown continues to cancel in-flight jobs.

When the prompt run's own failure handling raises, the worker SHALL still mark the job `"failed"` with `error_code = "worker_crash"`.

A failure to announce a job's fate on the live event bus SHALL NOT be one of the errors that reaches that fallback. The prompt run's failure handling records the durable `failure` event, publishes it, and marks the job failed; because publishing is best-effort, a transport error there SHALL leave that sequence intact, so the job SHALL end with the `error_code` its real failure was classified as and SHALL carry exactly one `failure` event. Before DRA-42 a failed publish skipped `mark_job_failed` and escaped into the crash fallback, which did still reach `"failed"` but recorded the cause as `worker_crash` and left the job's event list carrying `failure` twice — a diagnosis lost to an unrelated transport error.

Because context replay only includes `"completed"`, `"interrupted"`, and `"failed"` jobs, reaching a terminal status is what keeps the prompt of a crashed run in the session transcript, so the next run replays that prompt instead of continuing as though the message was never sent.

#### Scenario: Unclassified error during the model call
- **WHEN** the gateway call for a prompt job raises an error the worker does not explicitly classify, such as a timeout or an `ExceptionGroup`
- **THEN** the worker SHALL persist a `failure` event for the job
- **AND** the job SHALL end with status `"failed"` rather than remaining `"running"`

#### Scenario: Error before the first model call
- **WHEN** a prompt job crashes before its first model call, for example while checking cancellation or loading the job record
- **THEN** the job SHALL end with status `"failed"` rather than remaining `"running"`

#### Scenario: Failure handling itself crashes
- **WHEN** the prompt run raises while recording a failure, so the exception escapes the prompt run
- **THEN** the worker SHALL mark the job `"failed"` with `error_code = "worker_crash"`

#### Scenario: Announcing a failure fails
- **WHEN** the live publish of a job's `failure` event raises a connection error
- **THEN** the job SHALL end with status `"failed"` carrying the `error_code` of the failure that actually occurred
- **AND** SHALL have exactly one `failure` job event

#### Scenario: The prompt of a crashed run survives into the next run
- **WHEN** a prompt job crashes and a later job runs in the same session with `multi_turn_memory` enabled
- **THEN** the crashed job's prompt SHALL appear as a `role: user` message in the replayed context
- **AND** SHALL be followed by the synthetic assistant note for failed jobs

### Requirement: Subagent jobs use a dedicated system prompt
Subagent jobs SHALL receive a system prompt distinct from the master job prompt.

A job started from a persona — a subagent started from a spawn's persona, or a top-level job whose session has adopted a persona of its own — SHALL additionally receive that persona's system prompt as its own clearly delimited section of the assembled prompt. The persona prompt SHALL be treated purely as text: it SHALL be concatenated into the message body and SHALL NOT be used as a format string or interpolated into any context where text becomes code, a query, or a shell command. The persona prompt SHALL NOT determine which tools the job has, because tool availability is decided from the job's own configuration.

#### Scenario: Subagent receives subagent-specific prompt
- **WHEN** a job with a non-null `parent_job_id` starts execution
- **THEN** the system prompt SHALL be built from the subagent prompt parts

#### Scenario: Persona prompt is included as its own section
- **WHEN** a subagent started from a persona begins execution
- **THEN** its system prompt SHALL contain the persona's prompt as a delimited section in addition to the subagent prompt parts

#### Scenario: A session's own persona is included the same way
- **WHEN** a top-level job runs on a session that has adopted a persona
- **THEN** its system prompt SHALL contain that persona's prompt as a delimited section in addition to the base prompt parts

#### Scenario: A persona prompt cannot grant a tool
- **WHEN** a persona's prompt instructs the model to use a tool that the persona's allowlist excluded, or to spawn a subagent
- **THEN** the tool SHALL NOT be available to the job, because tools are computed from configuration rather than read from prompt text

### Requirement: System prompt enforces tool usage discipline
The system prompt SHALL instruct the model to avoid speculative tool calls, prefer targeted tools, batch independent calls in a single round, and never repeat the same call twice in one job.

#### Scenario: No redundant tool calls in system prompt guidance
- **WHEN** the system prompt is rendered
- **THEN** it SHALL contain instructions against duplicate or speculative tool calls

### Requirement: System prompt enforces context discipline
The system prompt SHALL instruct the model that every tool result is appended verbatim to context and replayed in every future turn. It SHALL explicitly forbid calling the following tools directly in the main job: `get_game_state`, `search_cards_marvel_champions`, `export_game_state_snapshot`, `load_game_state_snapshot`, `reset_game`, and any tool returning a card list or full board JSON.

#### Scenario: Large-payload tools blacklisted in system prompt
- **WHEN** the system prompt is rendered
- **THEN** it SHALL name `get_game_state` and `search_cards_marvel_champions` as tools that must never be called directly in the main job

### Requirement: System prompt defines subagent use cases
The system prompt SHALL describe `spawn_subagent` and `wait_for_subagent`, list use cases that require subagent delegation (card catalog research, board state analysis, multi-card setup, play recommendation, rules look-up), and provide guidance on writing self-contained subagent prompts.

#### Scenario: Subagent section present in system prompt
- **WHEN** the system prompt is rendered
- **THEN** it SHALL contain a "Subagents" section describing `spawn_subagent` and `wait_for_subagent`

### Requirement: System prompt explains subagent nesting is blocked
The system prompt SHALL state that if `spawn_subagent` is not in the tool list, the job is already running as a subagent, and subagents SHALL call large-payload tools directly and return a concise answer rather than attempting further delegation.

#### Scenario: Subagent self-detection guidance present
- **WHEN** the system prompt is rendered
- **THEN** it SHALL contain the instruction to check whether `spawn_subagent` is available before attempting delegation

### Requirement: System prompt provides tool round limit recovery guidance
The system prompt SHALL instruct the model that if the tool round limit is exhausted mid-task, it SHALL summarise what was completed and what remains, and ask the user to send a follow-up message to continue.

#### Scenario: Tool round limit recovery guidance present
- **WHEN** the system prompt is rendered
- **THEN** it SHALL reference the tool round limit and a recovery action (follow-up message)

### Requirement: spawn_subagent tool description enforces delegation at tool-selection time
The `spawn_subagent` tool description SHALL state that it is only available to top-level jobs, name the tools that must always be delegated (at minimum `search_cards_marvel_champions`, `get_game_state`, `export_game_state_snapshot`, `load_game_state_snapshot`, `reset_game`), and explain that direct calls to those tools inject tokens permanently.

#### Scenario: spawn_subagent description names forbidden direct-call tools
- **WHEN** the tool catalog is presented to the model
- **THEN** the `spawn_subagent` description SHALL name `search_cards_marvel_champions` and `get_game_state` as tools that must be delegated

#### Scenario: spawn_subagent description states top-level-only availability
- **WHEN** the tool catalog is presented to the model
- **THEN** the `spawn_subagent` description SHALL state it is only available to top-level jobs

### Requirement: Reasoning enabled by default for dashboard sessions
New dashboard sessions SHALL have reasoning enabled by default. The default effort level SHALL be configurable via the `DEFAULT_REASONING_EFFORT` env var (default: `medium`). The default enabled state SHALL be configurable via `DEFAULT_REASONING_ENABLED` (default: `true`).

#### Scenario: New session draft has reasoning enabled
- **WHEN** a user opens the dashboard and creates a new session
- **THEN** the session draft SHALL have `reasoning.enabled = true` and `reasoning.effort` equal to the configured default

#### Scenario: Smoketest sessions have reasoning disabled
- **WHEN** the smoketest environment starts the dashboard stack
- **THEN** `DEFAULT_REASONING_ENABLED` SHALL be set to `false` so new smoketest sessions do not request reasoning

### Requirement: Token usage tracking per job
The system SHALL extract `usage.total_tokens` from the LLM API response and persist it as `tokens_used` on the `Job` row after each LLM call.

When the `usage` field is absent from the response, the system SHALL estimate token count using tiktoken and log a WARNING.

#### Scenario: Token usage extracted from response
- **WHEN** an LLM response includes a `usage.total_tokens` field
- **THEN** the job's `tokens_used` SHALL be set to that value

#### Scenario: Token usage estimated via fallback
- **WHEN** an LLM response does not include a `usage` field
- **THEN** the system SHALL estimate token count via tiktoken, set `tokens_used` to the estimate, and log a WARNING

### Requirement: CompactionRecord persistence
The system SHALL persist compaction results in a `CompactionRecord` table. Each record SHALL include: `session_id`, `summary_text`, `covers_up_to_job_id`, `tokens_used` (token count of the summary alone), `created_at`.

Raw `JobEvent` rows SHALL never be deleted as a result of compaction.

#### Scenario: Compaction creates a record
- **WHEN** compaction is triggered (manual or auto)
- **THEN** a `CompactionRecord` SHALL be created with the session's latest completed job as `covers_up_to_job_id` and the LLM-generated summary as `summary_text`

#### Scenario: Raw events preserved after compaction
- **WHEN** a `CompactionRecord` is created
- **THEN** all prior `JobEvent` rows SHALL remain in the database unmodified

### Requirement: Manual compaction endpoint
The system SHALL expose `POST /sessions/{session_id}/compact` that triggers immediate compaction.

Compaction SHALL: call the LLM with a summarization prompt instructing preservation of hero HP, threat levels, villain phase, encounter deck status, and all cards in play; create a `CompactionRecord`; return updated context metadata.

The history a compaction summarizes SHALL be bounded, and its size SHALL NOT grow with the session's total length:

1. When a previous `CompactionRecord` exists, compaction SHALL summarize only jobs created after that record's `covers_up_to_job_id`, on top of that record's `summary_text`, which SHALL be supplied to the summarizing model as prior context. It SHALL NOT re-read history the previous summary already covers.
2. The text a single tool call's arguments or a single tool result contributes to the summarization input SHALL be bounded by a configured character budget (`CONTEXT_COMPACTION_EVENT_CHAR_BUDGET`, int, default `20000`, which SHALL be positive). Where text is omitted, the input SHALL carry an explicit marker naming how much was omitted, so the summarizing model is not presented with a fragment as though it were complete. This bound applies to the summarization input only; a tool result replayed to the game agent SHALL NOT be truncated.
3. The assembled summarization request SHALL be estimated before it is sent and SHALL NOT be sent larger than `CONTEXT_COMPACTION_THRESHOLD` applied to the model's context window. Where entries must be dropped to satisfy that bound, the oldest SHALL be dropped first, and the number dropped SHALL be recorded on the log line and on the emitted `compaction` event.

The manual endpoint SHALL additionally accept a request body with `from_session_start`, which summarizes from the beginning of the session and ignores the previous checkpoint, so a user who believes a summary has lost information can rebuild it from the retained raw events. The body SHALL be optional and default to the checkpointed form. Automatic compaction SHALL always use the checkpointed form.

When there is nothing to summarize — no eligible completed job, or no history content in the span since the checkpoint — the endpoint SHALL return HTTP 422. When the summarizing model call fails, it SHALL return HTTP 502.

#### Scenario: Manual compaction succeeds
- **WHEN** a client sends `POST /sessions/{session_id}/compact`
- **THEN** the response SHALL be HTTP 200 with updated context metadata including incremented `compaction_count`

#### Scenario: Compaction on non-existent session
- **WHEN** a client sends `POST /sessions/{session_id}/compact` for a non-existent session
- **THEN** the response SHALL be HTTP 404

#### Scenario: Compaction when multi-turn memory is disabled
- **WHEN** a client sends `POST /sessions/{session_id}/compact` for a session with `multi_turn_memory: false`
- **THEN** the response SHALL be HTTP 409 with an error indicating compaction requires multi-turn memory

#### Scenario: Second compaction summarizes only the span since the checkpoint
- **WHEN** compaction runs for a session that already has a `CompactionRecord`
- **THEN** the summarization input SHALL contain the previous summary plus only the jobs created after that record's `covers_up_to_job_id`
- **AND** SHALL NOT contain the raw events of jobs the previous summary already covers

#### Scenario: Nothing new since the checkpoint
- **WHEN** compaction runs for a session with no job created since the previous `CompactionRecord`
- **THEN** the system SHALL NOT call the summarizing model
- **AND** the manual endpoint SHALL return HTTP 422

#### Scenario: An oversized tool payload is truncated with a marker
- **WHEN** a tool call's arguments or a tool result's content exceeds the configured per-event character budget
- **THEN** the summarization input SHALL carry that payload truncated to the budget followed by a marker stating how many characters were omitted

#### Scenario: A board-sized tool result is not truncated
- **WHEN** a tool result carries a full simplified game state, which is smaller than the configured budget
- **THEN** the summarization input SHALL carry it whole, with no marker

#### Scenario: The summarization request is never assembled over the ceiling
- **WHEN** the assembled summarization request estimates above the compaction threshold applied to the model's context window
- **THEN** the system SHALL drop history entries oldest-first until the estimate is within the bound
- **AND** SHALL record how many entries were dropped

#### Scenario: Rebuilding a summary from session start
- **WHEN** a client sends `POST /sessions/{session_id}/compact` with `from_session_start` set
- **THEN** compaction SHALL summarize every eligible job in the session regardless of any existing checkpoint

#### Scenario: The summarizing model call fails
- **WHEN** a client sends `POST /sessions/{session_id}/compact` and the summarizing model call fails
- **THEN** the response SHALL be HTTP 502 with the failure message
- **AND** no `CompactionRecord` SHALL be created

### Requirement: Auto-compaction at job start
Before sending the first model request for a new job, when `multi_turn_memory` is enabled, the system SHALL estimate the size of the request it is about to send and compact automatically if that estimate reaches `CONTEXT_COMPACTION_THRESHOLD` of the model's context window.

The estimate SHALL cover every part of the request, using the same tiktoken estimation the context metadata endpoint uses:

1. the system prompt built from the session's active skills, persona catalogue and persona state,
2. the tool definitions exposed to the model, built-in and MCP alike, gated as the job's own registry gates them,
3. the replayed prior message history, after compaction checkpoint and replay-window limits are applied, together with any conversation a restore attached to the session, which is prepended to every request and which compaction never rewrites,
4. the current turn's user message as the model will receive it, including the content of any skills the prompt loaded into itself.

The seat inbox is the one request component the estimate SHALL NOT include, because collecting it marks the messages it carries as delivered and they must be delivered exactly once, on the turn that sends them.

The estimate SHALL be produced by the same function the context metadata endpoint uses, so that the trigger and the reported usage cannot diverge. The estimate SHALL NOT be taken from cumulative `tokens_used` on job rows, which reflects per-job LLM consumption and underestimates the request.

The system SHALL NOT reconstruct the replayed history more than once per job for the purpose of this estimate.

Because compaction can only reduce part (3), the system SHALL NOT attempt compaction when the pressure comes from the parts it cannot reduce.

The history considered for this decision SHALL be the part compaction would actually replace: the replayed history less the carried-forward compaction summary — which the replay always includes as a system message and which the replay-window limits never drop — and less any restored conversation, which compaction does not rewrite either. The replayed history in total SHALL NOT be used, because it always contains that summary and comparing against it would leave the decision unreachable for any session that has compacted at least once.

The system SHALL also skip compaction when the parts it cannot reduce reach the context window on their own, since no summary can then produce a request that fits. It SHALL NOT skip merely because those parts reach the threshold while still fitting the window: compaction cannot bring such a session back under the threshold but does still reduce the request, and refusing it would leave a long session larger than it needs to be.

When the total estimate reaches the threshold but that compactable history is smaller than the summary that would replace it, the system SHALL skip compaction and SHALL log that the threshold was reached by fixed request cost rather than by history. The size of the summary that would replace it SHALL be the measured token length of the session's most recent `CompactionRecord` summary text where one exists, and otherwise `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS` (int, default `4000`, which SHALL NOT be negative). Cumulative `tokens_used` on a `CompactionRecord` SHALL NOT be used for this comparison, since it counts the summarized history as well as the summary.

Threshold is configured via `CONTEXT_COMPACTION_THRESHOLD` env var (float, default `0.8`). The window used as the denominator SHALL be the provider-reported context length for the session's model, falling back to the configured `CONTEXT_WINDOW_SIZE` (int, default `128000`) only when the provider reports none. A configured value SHALL NOT override what the provider reports, because one deployment serves models whose real windows differ by more than an order of magnitude.

Auto-compaction SHALL log an INFO entry recording the pre-compaction usage ratio and the component estimates it was computed from.

#### Scenario: Auto-compaction fires at threshold
- **WHEN** a job starts and the estimated request size divided by context window size reaches `CONTEXT_COMPACTION_THRESHOLD`, and the replayed history is large enough for compaction to reduce it
- **THEN** the system SHALL compact before sending the first model request
- **AND** SHALL log INFO with the pre-compaction ratio and its component estimates

#### Scenario: No auto-compaction below threshold
- **WHEN** a job starts and the estimated request size is below the threshold
- **THEN** the system SHALL proceed without compaction

#### Scenario: A request the replay alone would not have triggered
- **WHEN** a job's replayed history is below the threshold on its own but the system prompt, tool definitions and rendered user message bring the request to or above it, and the replayed history is large enough for compaction to reduce it
- **THEN** the system SHALL compact before sending the first model request

#### Scenario: Skills loaded into the turn count toward the estimate
- **WHEN** a job's prompt loaded skill content into its own user message
- **THEN** the estimate SHALL include that rendered content, not only the stored prompt text

#### Scenario: Tool definitions and system prompt count toward the estimate
- **WHEN** a session exposes tool definitions and an active-skill system prompt to the model
- **THEN** the estimate SHALL include both alongside the replayed history
- **AND** the tool definitions SHALL include the built-in tools as well as the MCP tools

#### Scenario: Fixed request cost alone does not trigger repeated compaction
- **WHEN** the total estimate reaches the threshold but the compactable history is smaller than the summary that would replace it
- **THEN** the system SHALL NOT call the summarizing model
- **AND** SHALL log that the threshold was reached by fixed request cost rather than by history

#### Scenario: A request whose fixed cost fills the window is not summarized
- **WHEN** the parts of the request compaction cannot reduce reach the context window on their own
- **THEN** the system SHALL NOT call the summarizing model, whatever the size of the history

#### Scenario: A restored conversation counts toward the estimate
- **WHEN** a session carries a conversation attached by a restore
- **THEN** that conversation SHALL count toward the estimate on both the trigger and the context metadata endpoint
- **AND** it SHALL NOT count as history compaction could reduce

#### Scenario: A session that has already compacted is still guarded
- **WHEN** a session whose fixed request cost alone reaches the threshold has a `CompactionRecord` and no new history since its checkpoint
- **THEN** the carried-forward summary in the replay SHALL NOT count as compactable history
- **AND** the system SHALL NOT call the summarizing model

#### Scenario: Trigger and reported usage agree
- **WHEN** the auto-compaction check and the context metadata endpoint run for the same session with no job in between
- **THEN** both SHALL estimate the same replay, system prompt, and tool-definition contributions

### Requirement: Context metadata endpoint
The system SHALL expose `GET /sessions/{session_id}/context` returning current context health metadata.

The session context metadata endpoint SHALL estimate context usage from the content the orchestrator would include in the next model request, rather than from cumulative historical job token totals.

That estimate SHALL include the system prompt generated from active skill summaries and the persona catalogue, replayed prior messages after compaction and replay-window limits are applied, any conversation a restore attached to the session, and every tool definition the next top-level job would be offered — built-in tools as well as those exposed from active MCP assignments, gated by the session's mode and seat as a real job's registry gates them.

The endpoint describes the next **top-level** job on the session. For a session whose jobs run as subagents, the reported figure is that of a top-level job on it and will exceed what those jobs send; the agreement required with the auto-compaction trigger is agreement for top-level jobs.

That estimate SHALL be produced by the same function the auto-compaction trigger uses, over the same components, so the number a user is shown is the number the trigger acts on.

That estimate SHALL NOT include prior history excluded by replay limits, inactive assignments, or a future user prompt that has not yet been submitted. Because the current turn's user message is the one request component this endpoint cannot know, the endpoint's total SHALL be the trigger's total less that component, and the response SHALL NOT carry a field for it.

Response SHALL include:
- `tokens_used`: estimated tokens for the next request envelope
- `context_window_size`: the provider-reported context length for the session's model where available, otherwise the configured `CONTEXT_WINDOW_SIZE`
- `usage_ratio`: `tokens_used / context_window_size` as float 0.0-1.0
- `compaction_count`: number of `CompactionRecord` rows for this session
- `last_compacted_at`: `created_at` of most recent `CompactionRecord`, or `null`
- `multi_turn_memory`: current value of the session flag
- `token_breakdown`: the estimate split into its system prompt, replay, and tool-definition parts

#### Scenario: Retrieve context metadata
- **WHEN** a client sends `GET /sessions/{session_id}/context`
- **THEN** the response SHALL be HTTP 200 with JSON containing all seven fields

#### Scenario: Reported window follows the session's model
- **WHEN** the provider reports a context length for the session's configured model
- **THEN** `context_window_size` SHALL be that length rather than the configured fallback

#### Scenario: Replay-limited session reports bounded context usage
- **WHEN** a session has replay-window limits configured and prior history exceeds those limits
- **THEN** the context metadata endpoint SHALL estimate tokens from only the retained replay subset plus the current system prompt and active tool definitions

#### Scenario: Skills and MCP tools count toward context usage
- **WHEN** a session has active skill assignments or MCP tool definitions available to the worker
- **THEN** the context metadata endpoint SHALL include their contribution in the estimated next-request context usage

#### Scenario: Built-in tools count toward context usage
- **WHEN** a session's next top-level job would be offered the built-in tools
- **THEN** the context metadata endpoint SHALL include their definitions in the `tools` part of the breakdown

#### Scenario: Historical job token totals do not override bounded replay estimate
- **WHEN** stored completed jobs report large `tokens_used` values that exceed what bounded replay would include next
- **THEN** the context metadata endpoint SHALL report the bounded next-request estimate rather than the historical aggregate

#### Scenario: Session not found
- **WHEN** a client sends `GET /sessions/{session_id}/context` for a non-existent session
- **THEN** the response SHALL be HTTP 404

### Requirement: Session transcript construction has one source of truth
The agent-orchestrator SHALL construct replay history, compaction checkpoint interpretation, and next-request context estimation from one session transcript Module.

#### Scenario: Worker and context metadata share transcript rules
- **WHEN** the worker builds the next model request and the context metadata endpoint estimates the next request envelope
- **THEN** both flows SHALL use the same session transcript Module Interface
- **AND** SHALL apply the same replay, compaction, and retained-tool semantics

#### Scenario: Compaction checkpoints are owned by the transcript Module
- **WHEN** the system creates or reads a compaction checkpoint for a session
- **THEN** the session transcript Module SHALL own the checkpoint semantics used to decide later replay eligibility

### Requirement: Persistent orchestration jobs
The system SHALL persist job lifecycle state, attempts, timestamps, errors, prompt inputs, generated outputs, and tool interaction events in a dedicated agent-orchestrator PostgreSQL database that is not shared with other services.

#### Scenario: Job completes
- **WHEN** a background worker completes a prompt job successfully
- **THEN** the system SHALL persist the completed status, final output, completion timestamp, and related orchestration events

#### Scenario: Dedicated database isolation
- **WHEN** the orchestrator is configured for persistence
- **THEN** it SHALL connect to its own PostgreSQL database instance or database name reserved for orchestrator data and SHALL NOT write orchestration tables into databases used by DragnCards or other services

#### Scenario: Job fails
- **WHEN** a background worker fails a prompt job
- **THEN** the system SHALL persist the failed status, error details, completion timestamp, and any events produced before failure

### Requirement: Job cancellation
The system SHALL allow clients to request cancellation for queued or running jobs. Cancellation SHALL be persisted, surfaced in job lifecycle state, observed by workers before any further model or MCP calls, and propagated from parent jobs to active spawned child jobs.

#### Scenario: Cancellation is requested for a queued or running job
- **WHEN** a client requests cancellation for a queued or running job
- **THEN** the system SHALL persist the cancellation request on that job

#### Scenario: Worker observes cancellation during execution
- **WHEN** a worker observes that cancellation has been requested for a job before another model or MCP call
- **THEN** the worker SHALL stop the job without performing further model or MCP calls
- **THEN** the system SHALL mark the job cancelled and persist a cancellation event

#### Scenario: Parent job cancellation propagates to active child jobs
- **WHEN** a cancelled job is the parent of one or more running subagent jobs
- **THEN** the system SHALL request cancellation for each still-running child job
- **AND** SHALL NOT leave spawned child jobs running after the parent job has been cancelled

#### Scenario: Cancelled child jobs are fully reconciled
- **WHEN** a child job is cancelled because its parent job was cancelled
- **THEN** the child job SHALL still reach a terminal cancelled state and its child session SHALL be terminated
- **THEN** the parent job transcript SHALL record that child outcome as a `subagent_failed` event with a cancellation reason

### Requirement: Bifrost gateway execution
The system SHALL route LLM prompt execution through Bifrost rather than calling provider SDKs directly.

#### Scenario: Execute through configured gateway
- **WHEN** a worker executes a prompt job for a configured session
- **THEN** the worker SHALL call Bifrost using the session provider and model configuration

#### Scenario: Gateway failure is recorded
- **WHEN** Bifrost returns an error during prompt execution
- **THEN** the system SHALL record the gateway error on the job and mark the job failed unless retry policy allows another attempt

### Requirement: Retryable orchestration failure classification
The worker SHALL classify orchestration failures as retryable or non-retryable before persisting final job state.

Retryable failures SHALL include transient provider failures surfaced by Bifrost retry metadata and MCP transport or timeout failures that do not indicate a permanent local configuration bug.

#### Scenario: Provider reports retryable error
- **WHEN** Bifrost raises an error marked `retryable`
- **THEN** the worker SHALL record a failure event with `retryable: true`
- **AND** SHALL pass that retryable state into job failure handling

#### Scenario: MCP transport failure treated as retryable
- **WHEN** an MCP tool call fails because of a timeout, connection interruption, or other transport-layer error
- **THEN** the worker SHALL classify the failure as retryable execution failure unless a permanent local configuration problem is identified

#### Scenario: Invalid local tool contract treated as non-retryable
- **WHEN** the worker encounters a local execution bug while trying to build or persist tool feedback for a model-requested tool call
- **THEN** the worker SHALL classify that failure as non-retryable and fail the job attempt terminally when no other retryable error applies

### Requirement: Streaming event API
The system SHALL expose a streaming-compatible API for clients to consume session and job events produced during orchestration.

#### Scenario: Stream job events
- **WHEN** a client subscribes to the event stream for a job
- **THEN** the system SHALL emit persisted events for prompt progress, model output chunks, tool calls, tool results, completion, failure, and cancellation as they become available
#### Scenario: Resume event stream
- **WHEN** a client reconnects with a last-seen event cursor
- **THEN** the system SHALL resume streaming from events after that cursor

### Requirement: Job event streaming owns replay-plus-live delivery
The agent-orchestrator SHALL deliver job event streams through one job event stream Module that owns persisted replay, live tailing, reconnect cursors, and terminal close behavior.

#### Scenario: SSE adapter delegates replay-plus-live delivery
- **WHEN** a client subscribes or reconnects to `GET /jobs/{job_id}/events/stream`
- **THEN** the API adapter SHALL delegate replay-plus-live delivery through the same job event stream Module Interface

#### Scenario: Stream closes only after replay and live tail are reconciled
- **WHEN** a job reaches a terminal state while a client is streaming events
- **THEN** the job event stream Module SHALL deliver any remaining persisted or live events required by the stream contract before closing the stream

### Requirement: Dashboard-readable session metadata
The agent-orchestrator SHALL expose enough session metadata for a dashboard client to list, select, inspect, and configure sessions without relying on internal storage details.

#### Scenario: Dashboard lists session summaries
- **WHEN** the dashboard requests agent sessions
- **THEN** the agent-orchestrator SHALL return session identifiers, lifecycle status, model/provider summary, assigned MCPs, assigned skills, and recent job summary suitable for display

#### Scenario: Dashboard retrieves session details
- **WHEN** the dashboard requests one agent session
- **THEN** the agent-orchestrator SHALL return the session configuration, assigned MCPs, assigned skills, lifecycle status, and recent orchestration job state

### Requirement: Dashboard session defaults contract
The agent-orchestrator SHALL accept session creation and update requests that include dashboard-provided default model/provider settings, skill assignments, and MCP assignments.

#### Scenario: Create session from dashboard defaults
- **WHEN** the dashboard creates a session with default model/provider, skills, and MCPs
- **THEN** the agent-orchestrator SHALL validate and persist those settings using the same rules as other session creation clients

#### Scenario: Reject invalid dashboard defaults
- **WHEN** the dashboard submits an unknown provider, skill, or MCP assignment
- **THEN** the agent-orchestrator SHALL reject the invalid value with a descriptive validation error and SHALL NOT partially persist the rejected assignment

### Requirement: Dashboard event stream compatibility
The agent-orchestrator SHALL expose streaming job events in a form that allows dashboard clients to render live chat output, progress summaries, tool calls, tool results, errors, and completion state.

#### Scenario: Stream dashboard event types
- **WHEN** a prompt job emits orchestration events
- **THEN** the agent-orchestrator SHALL provide event type, event identifier or cursor, timestamp, job identifier, and payload fields sufficient for the dashboard to render the event

#### Scenario: Resume dashboard event stream
- **WHEN** the dashboard reconnects with a last-seen event cursor
- **THEN** the agent-orchestrator SHALL stream only events after that cursor

### Requirement: Incremental streaming event persistence
The agent-orchestrator SHALL write streaming model output and reasoning events to the database incrementally during generation so that reconnecting clients can recover partial output without losing in-flight content.

#### Scenario: First chunk creates DB row
- **WHEN** the first model output or reasoning chunk arrives during streaming
- **THEN** the worker SHALL persist a DB event row immediately via append_event, capturing the initial partial text

#### Scenario: Subsequent chunks update DB row
- **WHEN** additional model output or reasoning chunks arrive
- **THEN** the worker SHALL update the existing DB row via update_event at regular intervals so the snapshot reflects accumulated text

#### Scenario: Reconnecting client receives partial output
- **WHEN** a client reconnects mid-stream after disconnecting
- **THEN** the event stream SHALL replay the latest DB snapshot of in-progress events so the client sees partial output without waiting for the stream to complete

### Requirement: Live event bus replay for late subscribers
The agent-orchestrator live event bus SHALL buffer recent events per job and deliver them to late subscribers so that clients reconnecting during active streaming do not miss events published between disconnect and reconnect.

#### Scenario: Late subscriber catches up
- **WHEN** a client subscribes to the live event bus after events have already been published for a job
- **THEN** the subscriber SHALL receive all buffered events up to the replay buffer limit before receiving new events

#### Scenario: Buffer evicts oldest events
- **WHEN** the number of buffered events for a job exceeds the configured replay buffer size
- **THEN** the oldest events SHALL be evicted and only the most recent events SHALL be replayed to new subscribers

#### Scenario: Subscriber cleanup on disconnect
- **WHEN** a subscriber closes its connection
- **THEN** the bus SHALL remove the subscriber from its active queue set and SHALL NOT deliver further events to it

### Requirement: Agent orchestrator OpenAPI availability
The agent-orchestrator SHALL expose an OpenAPI document suitable for dashboard aggregation.

#### Scenario: Fetch orchestrator OpenAPI
- **WHEN** the dashboard requests the agent-orchestrator OpenAPI document from the configured endpoint
- **THEN** the agent-orchestrator SHALL return a valid OpenAPI document for its HTTP API

### Requirement: Provider secrets are externalized
The system SHALL read provider credentials and gateway secrets from environment or local runtime configuration and SHALL NOT require secrets to be committed to the repository.

#### Scenario: Missing provider secret
- **WHEN** a worker attempts to execute a job for a provider without required runtime credentials
- **THEN** the system SHALL fail the job with a configuration error that does not expose secret values

### Requirement: Orchestrator health and readiness
The system SHALL expose health and readiness endpoints for the API, database connectivity, worker availability, and Bifrost connectivity.

#### Scenario: Readiness succeeds
- **WHEN** PostgreSQL is reachable and required orchestrator configuration is valid
- **THEN** the readiness endpoint SHALL report ready

#### Scenario: Readiness fails
- **WHEN** PostgreSQL is unreachable or required orchestrator configuration is invalid
- **THEN** the readiness endpoint SHALL report not ready with non-secret diagnostic details

### Requirement: Skill roots scoped to project skills directory
The agent-orchestrator SHALL load skills only from the project `skills/` directory by default. It SHALL NOT load skills from `.opencode/skills/` or any other AI tooling directory, as those contain agent-authoring tools not intended for game-bot use.

The default `SKILL_ROOTS` value SHALL be `../../skills` (relative to the service root). Operators MAY override this via the `SKILL_ROOTS` env var.

#### Scenario: Default skill roots exclude opencode skills
- **WHEN** the agent-orchestrator starts without a `SKILL_ROOTS` override
- **THEN** it SHALL discover skills only under `../../skills` and SHALL NOT load any skill from `.opencode/skills/`

#### Scenario: Operator override is respected
- **WHEN** `SKILL_ROOTS` is set to a custom path
- **THEN** the orchestrator SHALL discover skills from that path instead of the default

### Requirement: Provider model listing filtered to owning provider
When listing models for a provider, the orchestrator SHALL filter the raw Bifrost response to include only models that plausibly belong to that provider. This compensates for Bifrost fallback behaviour where a misconfigured provider (e.g. missing API key) may return models from another provider.

The filter rules SHALL be:
- A model whose `id` starts with `<provider_prefix>/` is always accepted.
- A model whose `id` does not start with `<provider_prefix>/` is excluded, even if the model ID is otherwise plausible for that provider.

#### Scenario: Same-provider prefixed model accepted
- **WHEN** Bifrost returns a model id starting with `<provider_prefix>/` for that provider
- **THEN** the orchestrator SHALL include it in the provider's model list

#### Scenario: Cross-provider model accepted for openrouter
- **WHEN** Bifrost returns a model id such as `openai/gpt-4o-mini` for the `openrouter` provider
- **THEN** the orchestrator SHALL exclude it because only `openrouter/...` IDs are surfaced in the provider catalog

#### Scenario: Cross-provider model rejected for non-openrouter provider
- **WHEN** Bifrost returns a model id containing `/` that does not start with the provider's own prefix, for a provider that is not `openrouter`
- **THEN** the orchestrator SHALL exclude it from that provider's model list

#### Scenario: Unprefixed model rejected
- **WHEN** Bifrost returns a model id without `/`, such as `gpt-4o-mini` or `qwen3.5-0.8b`
- **THEN** the orchestrator SHALL exclude it from the provider's model list because the catalog only surfaces prefixed model IDs

#### Scenario: Bifrost fallback leaks lmstudio models into openrouter
- **WHEN** `openrouter` has no API key configured and Bifrost falls back to returning lmstudio models
- **THEN** those `lmstudio/...` models SHALL be excluded from the `openrouter` provider catalog because they do not start with `openrouter/`

### Requirement: Bounded provider-listing latency
The provider/model listing endpoint SHALL bound the time spent listing models for any single provider so that a provider missing an API key or otherwise unreachable cannot stall the aggregate response.

Each per-provider model-listing HTTP request SHALL use a short, configurable timeout controlled by `BIFROST_LIST_MODELS_TIMEOUT_SECONDS` (default 8 seconds, which MUST be positive), separate from the general client timeout used for chat completions. The general completion timeout SHALL remain unchanged so normal completion behaviour does not regress.

The `/providers` endpoint SHALL additionally enforce a hard per-provider ceiling, no longer than the configured list-models timeout plus a small fixed margin, so that the total endpoint latency is bounded by that ceiling even when every provider is broken.

#### Scenario: Keyless provider fails fast
- **WHEN** a client requests `/providers` and one enabled provider's model listing does not respond within `BIFROST_LIST_MODELS_TIMEOUT_SECONDS`
- **THEN** the system SHALL stop waiting for that provider within the configured timeout (plus the fixed guard margin) and SHALL NOT wait the full general completion timeout

#### Scenario: Endpoint bounded when all providers are broken
- **WHEN** a client requests `/providers` and every enabled provider's model listing hangs
- **THEN** the system SHALL return a response whose total latency is bounded by the configured list-models timeout plus the fixed guard margin

### Requirement: Graceful per-provider listing failure
The provider/model listing endpoint SHALL isolate failures so that one slow or failing provider never prevents the working providers from returning their models.

When listing models for a provider fails or times out, the system SHALL return that provider with `available=false`, an empty model list, and a clear, non-empty error message, while still returning successful results for all other enabled providers in the same response.

#### Scenario: One failing provider does not block others
- **WHEN** a client requests `/providers` and one enabled provider raises an error while others succeed
- **THEN** the system SHALL return the successful providers with `available=true` and their models, and the failing provider with `available=false`, an empty model list, and a descriptive error message

#### Scenario: Timed-out provider reported as unavailable
- **WHEN** a provider's model listing exceeds the configured per-provider timeout
- **THEN** the system SHALL return that provider with `available=false`, an empty model list, and an error indicating the listing timed out

### Requirement: Cached unavailable providers
The system SHALL cache the unavailable result of a provider model listing so that repeated `/providers` calls do not re-incur the per-provider list-models timeout for a provider that is missing an API key or otherwise unreachable.

When a provider's model listing fails or times out, the system SHALL record a negative/unavailable marker in Valkey for that provider, distinguishable from a positive cache entry. The marker's time-to-live SHALL depend on whether the failure is retryable: a definitive (non-retryable) failure — such as a missing API key — SHALL use the long time-to-live controlled by `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` (default 600 seconds, which MUST be positive), while a transient (retryable) failure — a timeout, network error, 5xx, or 429 — SHALL use a much shorter time-to-live controlled by `BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS` (default 30 seconds, which MUST be positive) so that a provider which recovers from a brief blip is re-probed quickly rather than suppressed for the full definitive time-to-live.

While a provider's negative marker is live, the system SHALL report that provider as `available=false` with a clear error message and SHALL NOT make the slow underlying model-listing HTTP call. A negative marker SHALL expire after its time-to-live so the negative cache can never permanently hide a provider, and a subsequent successful listing for a provider SHALL clear that provider's negative marker.

#### Scenario: Unavailable provider is not re-probed within the TTL
- **WHEN** a provider's model listing fails and a client requests `/providers` again before the negative-cache time-to-live elapses
- **THEN** the system SHALL report that provider as `available=false` with a clear error message without making another model-listing HTTP call to that provider

#### Scenario: Transient failure uses the short retryable TTL
- **WHEN** a provider's model listing fails with a retryable error (timeout, network error, 5xx, or 429)
- **THEN** the system SHALL record the negative marker with the short `BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS` time-to-live rather than the long `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` time-to-live, so a recovered provider is re-probed within the short window

#### Scenario: Definitive failure uses the long TTL
- **WHEN** a provider's model listing fails with a non-retryable error (for example a missing API key returning a 4xx auth error)
- **THEN** the system SHALL record the negative marker with the long `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` time-to-live so the slow model-listing HTTP call is not re-incurred on every subsequent request

#### Scenario: Negative marker cleared on recovery
- **WHEN** a provider that was previously negatively cached returns a successful model listing
- **THEN** the system SHALL clear that provider's negative marker so it is reported as `available=true` with its models

### Requirement: Provider model-cache reset
The system SHALL provide an operator-facing capability to clear the cached provider model listings so that a provider which becomes available after configuration changes (such as adding an API key) is immediately re-probed rather than waiting for cache entries to expire.

The reset capability SHALL clear both positive and negative cache entries, including the per-provider listing, the per-provider unavailable marker, and the shared aggregate listing, for every enabled provider, and SHALL be exposed via an HTTP endpoint registered consistently with the other catalog routes. The provider listing endpoint MAY additionally accept a request parameter that bypasses the cache for a single call.

#### Scenario: Reset forces re-probe of a recovered provider
- **WHEN** an operator triggers the provider model-cache reset after a previously unavailable provider becomes available
- **THEN** the system SHALL clear the cached entries and the next `/providers` call SHALL re-probe the provider and report it as `available=true` with its models

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

The agent-orchestrator SHALL validate the supplied `conversation_context` before persisting it or mutating any session, because the context is replayed verbatim into the next turn's message list and sent to the LLM. The supplied `game_id` SHALL be a non-empty, length-bounded string. The `conversation_context` SHALL be rejected with a validation error when it contains more than a bounded number of messages, when any message is not an object or lacks a string `role` in the set {`system`, `user`, `assistant`, `tool`}, or when its serialized size exceeds a bounded byte limit. A well-formed context SHALL be accepted and resumed unchanged.

#### Scenario: Resume a session with a restored conversation context
- **WHEN** a restore supplies a conversation context and a restored `game_id` to the agent-orchestrator
- **THEN** the agent-orchestrator SHALL create or resume a session whose conversation context matches the supplied context and whose game binding is the restored `game_id`

#### Scenario: Resumed session can play forward
- **WHEN** a session resumed from a restored conversation context runs its next turn
- **THEN** the agent SHALL act on the restored context and game state as if continuing from the original moment

#### Scenario: Reject a malformed conversation context message
- **WHEN** a restore request supplies a `conversation_context` containing a message that is not an object or whose `role` is missing or not one of `system`, `user`, `assistant`, or `tool`
- **THEN** the agent-orchestrator SHALL reject the request with a validation error and SHALL NOT create or mutate any session

#### Scenario: Reject an oversized conversation context
- **WHEN** a restore request supplies a `conversation_context` that exceeds the bounded message count or the bounded serialized size
- **THEN** the agent-orchestrator SHALL reject the request with a validation error and SHALL NOT persist the context

### Requirement: Bounded request body size

The agent-orchestrator SHALL enforce a configurable maximum request body size
ahead of application handling, so that an oversized (or streamed-unbounded)
request body cannot exhaust process memory before per-endpoint validation runs.
A request whose declared `Content-Length` exceeds the limit SHALL be rejected
without buffering the body; a request without a declared length SHALL be
buffered only up to the limit and rejected as soon as the limit is crossed. In
both cases the service SHALL respond with HTTP `413` and SHALL NOT invoke the
route handler. A request within the limit SHALL be processed unchanged.

#### Scenario: Reject a request with an oversized declared Content-Length

- **WHEN** a request arrives whose `Content-Length` header exceeds the configured maximum request body size
- **THEN** the agent-orchestrator SHALL respond with `413` without reading the body and SHALL NOT invoke the route handler

#### Scenario: Reject a streamed body that exceeds the limit

- **WHEN** a request with no declared `Content-Length` streams a body whose total size exceeds the configured maximum
- **THEN** the agent-orchestrator SHALL stop buffering once the limit is crossed and respond with `413` without invoking the route handler

#### Scenario: Process a request within the limit unchanged

- **WHEN** a request body is within the configured maximum
- **THEN** the agent-orchestrator SHALL pass the body to the route handler unchanged

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

### Requirement: wait_for_subagent always terminates with an actionable outcome
`wait_for_subagent` SHALL always return a result, and SHALL NOT block indefinitely on a child that crashed, was cancelled, was orphaned by a dead worker, or simply stopped reporting.

The child job's persisted status SHALL be the authority for whether it ended. Live job events are ephemeral (the Valkey stream carrying them expires) and are not published on every terminal transition, so the wait SHALL re-read the child's status while waiting rather than trusting the event stream alone. Terminal statuses are `"completed"`, `"failed"`, `"cancelled"`, and `"interrupted"`. Terminal live events SHALL still end the wait immediately so an ordinary finish is not delayed to the next poll.

The wait budget SHALL be absolute rather than per event, so a child that keeps emitting non-terminal events cannot renew it indefinitely. The budget and the status re-read interval SHALL be configurable through `SUBAGENT_WAIT_TIMEOUT_SECONDS` and `SUBAGENT_WAIT_POLL_INTERVAL_SECONDS`, both of which MUST be positive.

A failed child SHALL be reported with its `error_code` and `error_message` so the parent can reason about the cause rather than only learning that something ended. An `"interrupted"` child SHALL return its partial `result_text` as a successful result, matching how the interrupt is announced on the live bus.

When the budget expires the returned text SHALL name the child job, state its last recorded status, and instruct the agent not to wait on it again. The abandoned wait SHALL also be recorded on the parent job as a `subagent_failed` event with `reason: "wait_timeout"` and published on the parent's live stream, so a stalled wait is visible in the session timeline and not only in the service log.

A wait SHALL end when cancellation has been requested for the parent job, so a cancelled parent is not held by a child that has not observed the cancellation yet. Giving up on a wait SHALL NOT cancel the child: only the waiting is abandoned.

#### Scenario: Child crashes while the parent is waiting
- **WHEN** a child job crashes during its run while its parent is blocked in `wait_for_subagent`
- **THEN** the wait SHALL return an error result naming the child and its failure code
- **AND** SHALL NOT wait for the full budget to expire

#### Scenario: Child crash never reaches the live event stream
- **WHEN** a child job's own failure handling raises, so only the worker's last-resort guard records the outcome
- **THEN** the waiting parent SHALL still be told the child failed with `error_code = "worker_crash"`

#### Scenario: Child reached its tool round limit
- **WHEN** `wait_for_subagent` is called for a child whose status is `"interrupted"`
- **THEN** the wait SHALL return the child's partial `result_text` as a non-error result

#### Scenario: Child orphaned by a dead worker
- **WHEN** a child job stays in status `"running"` because the worker executing it was killed
- **THEN** the wait SHALL end when its budget expires
- **AND** the returned text SHALL state that the child is still recorded as running and that the parent must stop waiting on it

#### Scenario: A child streaming continuously cannot hold the parent forever
- **WHEN** a child keeps publishing non-terminal events for longer than the wait budget
- **THEN** the wait SHALL end at the budget rather than renewing it on each event

#### Scenario: Abandoned wait is recorded on the parent job
- **WHEN** a wait is abandoned because its budget expired
- **THEN** a `subagent_failed` event SHALL be appended to the parent job with `reason: "wait_timeout"`, the `child_job_id`, and the child's last recorded status

#### Scenario: Parent cancellation releases the wait
- **WHEN** cancellation is requested for a parent job that is blocked in `wait_for_subagent`
- **THEN** the wait SHALL return an error result explaining that the job was cancelled

### Requirement: A crashed job announces its failure as well as recording it
When a prompt run crashes out of its own failure handling, the worker SHALL publish a `failure` live event and append a `failure` job event in addition to marking the job `"failed"` with `error_code = "worker_crash"`, and SHALL terminate the session if the crashed job was a child.

Announcing is what a blocked parent, the child monitor, and the dashboard's event stream depend on: a database-only failure leaves every live consumer waiting for an event that never arrives. Each step SHALL be guarded independently, because this is the last line of defence and a second failure here MUST NOT undo the steps that already succeeded.

#### Scenario: Crash guard publishes the failure
- **WHEN** a job crashes outside prompt-run failure handling
- **THEN** a `failure` event with `code = "worker_crash"` SHALL be published on the job's live event stream
- **AND** the same failure SHALL be persisted as a job event

#### Scenario: Crashed child session is released
- **WHEN** the crashed job is a child job
- **THEN** its session SHALL be terminated rather than left active

### Requirement: Agent persona persistence
The agent-orchestrator SHALL let a client define named agent personas and SHALL persist them in PostgreSQL rather than in process memory, in a repository file, or in the runtime skills directory. A persona SHALL be a reusable bundle of a system prompt, a skill selection, and a tool configuration, and SHALL carry: a name that identifies it, an optional display name and description, a system prompt, an optional provider id and model name, gateway and provider option overrides, a skill list, and a tool allowlist.

A persona SHALL be scoped to the deployment rather than to a session or a user, because a persona exists precisely to be reused across sessions and because the service carries no user identity to scope to. A persona's name SHALL be its identity, so a persona is addressable by name in an API path and nameable by an agent in a tool argument.

Because a persona is deployment-global, which personas a **given** session may start a subagent from SHALL be a per-session selection from this catalogue rather than a property of the catalogue itself. A persona SHALL therefore be usable by a session that has selected it and unavailable to one that has not, without either session being able to change the catalogue.

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

#### Scenario: One deployment catalogue, per-session selection
- **WHEN** two sessions exist and only one allows a given persona
- **THEN** both SHALL be able to read that persona from the catalogue
- **AND** only the session that allows it SHALL be able to start a subagent from it

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

### Requirement: The agent can ask the user a question with fixed choices
The orchestrator SHALL offer a built-in `ask_user` tool to top-level prompt jobs, taking a question and between one and eight labelled choices, and optionally permitting a free-text answer. Child jobs and compaction jobs SHALL NOT be offered the tool, because no user surface is attached to them; a child job that calls it anyway SHALL receive an error result rather than a question nobody can see.

The tool SHALL validate the model's arguments before recording anything: the question must be non-empty, the number of choices must be within the permitted bound, every choice must carry a non-empty label and a non-empty value, choice values must be unique so that an answer identifies exactly one choice, and the question, labels, values, and descriptions must be within their length limits. A violation SHALL return an error result naming the problem so the model can correct itself, and SHALL NOT record a question.

The choices recorded for a question SHALL be exactly those the model offered, and SHALL be the authority against which a later answer is checked.

#### Scenario: Ask a question with choices
- **WHEN** a top-level job calls `ask_user` with a question and two valid choices
- **THEN** the system SHALL record a pending question carrying that question text and those two choices
- **AND** the system SHALL record and publish a `user_question` event carrying the question, its identifier, and the offered choices

#### Scenario: The tool is not offered to a child job
- **WHEN** the effective tool list is built for a child job
- **THEN** `ask_user` SHALL NOT appear in it

#### Scenario: Reject a question with no choices
- **WHEN** a job calls `ask_user` with an empty choice list
- **THEN** the system SHALL return an error result describing the problem and SHALL NOT record a question

#### Scenario: Reject duplicate choice values
- **WHEN** a job calls `ask_user` with two choices sharing the same value
- **THEN** the system SHALL return an error result describing the problem and SHALL NOT record a question

### Requirement: A pending question and its answer are durably stored
A question the agent is waiting on SHALL be stored in the relational database, together with the choices offered and, once given, the answer. It SHALL NOT be held in process memory, because the run that asks and the request that answers are separate processes that may be separate replicas, and because a pending question SHALL survive both a browser reload and a stream reconnect.

A stored question SHALL be in exactly one of three states: awaiting an answer, answered, or closed without an answer. Both transitions out of the awaiting state SHALL be applied conditionally on the question still awaiting an answer, so that exactly one caller can ever make each transition.

A question SHALL be removed when the job or session that owns it is deleted.

#### Scenario: A pending question outlives the request that created it
- **WHEN** a question has been recorded and the asking run is still waiting
- **THEN** the question and its offered choices SHALL be readable from the database by a different process

#### Scenario: A question is removed with its session
- **WHEN** the session owning a job with a recorded question is deleted
- **THEN** the question SHALL be removed as well

### Requirement: An answer is validated against the choices that were offered
The orchestrator SHALL expose an endpoint that records the user's answer to a specific question of a specific job. The endpoint SHALL accept exactly one of a chosen value or a free-text answer, and SHALL reject a request carrying both or neither as a bad request.

A chosen value SHALL be checked against the choices read back from the stored question. A value that was not offered SHALL be rejected as a bad request, so that a client cannot answer with something the model never offered and cannot widen the set of answers the model asked for. A free-text answer SHALL be rejected as a bad request unless the stored question permits free text.

An answer to an unknown job or an unknown question SHALL be rejected as not found. A question of a different job SHALL NOT be answerable through that job.

On success the endpoint SHALL record the answer, transition the question to answered, and record and publish a `user_question_answered` event naming the question and the answer given.

#### Scenario: Answer by choosing an offered value
- **WHEN** a client submits a chosen value that appears in the stored question's choices
- **THEN** the system SHALL record the answer, mark the question answered, and publish a `user_question_answered` event

#### Scenario: Reject a value that was never offered
- **WHEN** a client submits a chosen value that does not appear in the stored question's choices
- **THEN** the system SHALL reject the request as a bad request and the question SHALL remain awaiting an answer

#### Scenario: Reject free text the question did not permit
- **WHEN** a client submits a free-text answer to a question that does not permit free text
- **THEN** the system SHALL reject the request as a bad request and the question SHALL remain awaiting an answer

#### Scenario: Reject an answer carrying both forms
- **WHEN** a client submits both a chosen value and a free-text answer
- **THEN** the system SHALL reject the request as a bad request

### Requirement: A question is answered at most once
A question that is no longer awaiting an answer SHALL NOT be answerable. A second answer to a question that has already been answered, or an answer to a question that has been closed, SHALL be rejected as a conflict, and SHALL NOT alter the recorded answer.

An answer SHALL also be rejected as a conflict when the job that asked has reached a terminal status, because nothing is waiting to read it. This is what prevents an answer being accepted for a question whose run died without closing it.

The model SHALL therefore observe exactly one answer to any question it asked.

#### Scenario: The second answer is refused
- **WHEN** a question has been answered and a second answer is submitted for it
- **THEN** the system SHALL reject the second request as a conflict and the recorded answer SHALL be unchanged

#### Scenario: A closed question is not answerable
- **WHEN** a question has been closed without an answer and an answer is then submitted for it
- **THEN** the system SHALL reject the request as a conflict

#### Scenario: A question of a finished job is not answerable
- **WHEN** the job that asked a still-pending question has reached a terminal status and an answer is submitted
- **THEN** the system SHALL reject the request as a conflict

### Requirement: A run waiting on a question always resumes
The `ask_user` tool SHALL block the calling run until the question is answered or the wait ends, and SHALL always return a result the model can act on. The run SHALL NOT be suspended: the wait happens inside the tool call, and the answer re-enters the model's context as an ordinary tool result in the same message history every other tool result uses. No separate channel SHALL be introduced for it.

While waiting, the run SHALL treat the stored question as the authority and re-read it at a bounded interval, so that an answer recorded by another replica is observed even when no live event reaches the waiting run.

The wait SHALL be bounded by an absolute timeout, configurable together with the polling interval. When the timeout expires the run SHALL close the question, record and publish a `user_question_closed` event giving the reason as a timeout, and return a result stating that nobody answered and that the model should proceed on its own judgement or report that it is blocked. That result SHALL NOT be an error result, so the model does not read it as a transient failure to retry.

When the job's cancellation has been requested while waiting, the run SHALL close the question, record and publish a `user_question_closed` event giving the reason as cancellation, and stop waiting.

Closing a question SHALL happen before the run stops waiting on it, so that an answer submitted afterwards is refused rather than recorded against a question nobody is reading.

#### Scenario: The answer reaches the model as a tool result
- **WHEN** a user answers a pending question by choosing an offered value
- **THEN** the waiting `ask_user` call SHALL return a result naming the chosen answer
- **AND** that result SHALL be appended to the run's message history as the tool result for that call

#### Scenario: Nobody answers
- **WHEN** the wait for an answer reaches its timeout
- **THEN** the system SHALL close the question with a timeout reason, publish a `user_question_closed` event, and return a non-error result telling the model that nobody answered

#### Scenario: A late answer to a timed-out question is refused
- **WHEN** an answer is submitted for a question that the wait already closed on timeout
- **THEN** the system SHALL reject it as a conflict

#### Scenario: The job is cancelled while waiting
- **WHEN** cancellation is requested for a job that is waiting on a question
- **THEN** the system SHALL close the question with a cancellation reason and the run SHALL stop waiting

### Requirement: Question activity appears on the job's event timeline
The events `user_question`, `user_question_answered`, and `user_question_closed` SHALL each be both persisted against the job and published on the live event bus, following the existing pairing used by every other job event. None of them SHALL be treated as a terminal event, so the event stream stays open while the user decides.

Because each of the three is both persisted and published, each published copy SHALL carry the identifier of the durable row it copies, so that a client receiving both copies recognises them as one event and renders the question, its answer, or its closure once. Publishing a question without that identifier SHALL be regarded as a defect: the two copies then differ only by an identifier the client keys on, and the question is rendered twice.

Each event SHALL carry the question identifier, so that a consumer can match an answer or a closure to the question it resolves. The answered event SHALL carry the answer given and whether it came from a choice or from free text; the closed event SHALL carry the reason it was closed.

Because these events are persisted, a consumer that replays a job's events SHALL be able to reconstruct every question's current state without any additional endpoint.

#### Scenario: The timeline reconstructs a question's state
- **WHEN** a consumer replays a job's persisted events from the beginning
- **THEN** it SHALL find the `user_question` event and, if the question was resolved, the matching `user_question_answered` or `user_question_closed` event carrying the same question identifier

#### Scenario: A question does not close the event stream
- **WHEN** a `user_question` event is published for a running job
- **THEN** the job's event stream SHALL remain open

#### Scenario: One asked question is one event to a streaming client
- **WHEN** a running job records a question and publishes it while a client is streaming
- **THEN** the persisted copy and the published copy SHALL reach that client under the same identifier
- **AND** the client SHALL be able to reduce them to a single question awaiting an answer

### Requirement: Generated display names are deterministic and stored
The orchestrator SHALL derive a display name for an agent from two halves: a codename chosen by hashing a seed, and a topic taken from the prompt the agent was given. The codename SHALL be one adjective and one animal drawn from fixed word lists, so that agents seeded differently are told apart at a glance. The topic SHALL be the prompt's content words, so that the name says what the agent was asked to do. A name with no usable topic SHALL be the codename alone.

Name generation SHALL be a pure function of its inputs. The same seed and the same prompt SHALL always produce the same name, and generating a name SHALL NOT call a language model, read the clock, or consult any random source.

A generated name SHALL be stored — on the session it names, and in every event payload that mentions it — and readers SHALL use the stored name rather than recomputing it. A generated name SHALL be bounded in length so that it fits the column that stores it and the controls that display it.

The topic SHALL be built only from text that reads as words. The orchestrator SHALL split the prompt into runs of letters, digits and underscores, and SHALL reject such a run entirely unless every underscore-separated part of it is alphabetic and is all lower case, all upper case, or capitalised. Identifiers, numbers and mixed-case opaque strings SHALL therefore contribute nothing to a name, so that a prompt carrying a credential cannot donate a fragment of it to a name that is stored and displayed. Function words and the orchestrator's own instruction boilerplate SHALL be excluded from the topic, and a word SHALL appear in a topic at most once.

#### Scenario: The same inputs always produce the same name
- **WHEN** a name is generated twice from one seed and one prompt
- **THEN** the two names SHALL be identical
- **AND** generating them SHALL NOT have called a language model

#### Scenario: Different seeds are told apart
- **WHEN** names are generated from many different seeds
- **THEN** the codenames SHALL differ across substantially all of them

#### Scenario: Two identical prompts still get different names
- **WHEN** two agents are seeded differently and given the same prompt
- **THEN** their names SHALL differ

#### Scenario: The topic comes from the prompt, not its boilerplate
- **WHEN** a prompt opens with instruction boilerplate and then states its task
- **THEN** the name SHALL contain words from the task
- **AND** SHALL NOT contain the boilerplate's own words

#### Scenario: A tool name contributes its words
- **WHEN** a prompt names a tool such as `search_cards_marvel_champions`
- **THEN** the name SHALL contain that tool's words

#### Scenario: Identifiers contribute nothing
- **WHEN** a prompt contains a UUID, a card id, a group name such as `player1Play`, or a number
- **THEN** none of them SHALL appear in the generated name

#### Scenario: An opaque letter run is not mined for words
- **WHEN** a prompt contains a credential-shaped mixed-case string
- **THEN** no part of that string SHALL appear in the generated name

#### Scenario: A prompt with no content words still yields a name
- **WHEN** a prompt consists only of function words, or there is no prompt at all
- **THEN** the name SHALL be the codename alone

#### Scenario: A very long prompt yields a bounded name
- **WHEN** a name is generated from a prompt of many thousands of words
- **THEN** the name SHALL be no longer than the generator's documented bound
- **AND** SHALL NOT end part-way through a word

### Requirement: An unnamed session is named from its first prompt
The prompt submission endpoint SHALL give a session a generated name when that session has no name and has no prior job, deriving it from the session's identifier and the prompt being submitted, within the same request that enqueues the job.

A session that already carries a name SHALL NOT be renamed, so a name chosen by whoever created the session is never overwritten. A session that has already run a job SHALL NOT be renamed, so only the first prompt names a session. The name SHALL be persisted, so that every client reads the same name for that session rather than deriving one of its own.

#### Scenario: The first prompt names an unnamed session
- **WHEN** a prompt is submitted to a session that has no name and no prior job
- **THEN** the session SHALL be given a generated name derived from its identifier and that prompt
- **AND** that name SHALL be readable from the session immediately after the request returns

#### Scenario: A later prompt does not rename the session
- **WHEN** a second prompt is submitted to a session that has already run a job
- **THEN** the session's name SHALL be unchanged

#### Scenario: A chosen name is never overwritten
- **WHEN** a prompt is submitted to a session whose creator gave it a name
- **THEN** that name SHALL be unchanged

### Requirement: A failed compaction degrades the turn instead of failing it
Automatic compaction runs to protect a job from exceeding its context window, so its own failure SHALL NOT be the reason that job fails. When automatic compaction cannot complete, the worker SHALL log the failure with the usage ratio that triggered it, SHALL record a transcript-visible `compaction_failed` event carrying the failure code, its message and that ratio, and SHALL continue the job with the message history it already has.

A compaction attempt that finds nothing to summarize is not a failure: when the session has no eligible completed job or no history content since the checkpoint, the worker SHALL treat it as a no-op, SHALL NOT record a failure event, and SHALL proceed.

Recording the degradation SHALL NOT be able to fail the job either: a failure to persist or publish the event SHALL be logged and SHALL NOT propagate.

Any event type the worker emits for this SHALL be registered in the dashboard's stream event list, because the browser subscribes per named event type and silently drops any type absent from that list.

#### Scenario: The summarizing model call fails during a turn
- **WHEN** automatic compaction is triggered and the summarizing model call fails
- **THEN** the worker SHALL log the failure with the triggering usage ratio
- **AND** SHALL record a transcript-visible `compaction_failed` event naming the failure
- **AND** SHALL continue the job with its existing message history rather than marking the job failed

#### Scenario: Nothing to compact is not a failure
- **WHEN** automatic compaction is triggered for a session with no eligible completed job or no history content
- **THEN** the worker SHALL proceed with the job
- **AND** SHALL NOT record a failure event

#### Scenario: Manual compaction still reports its errors
- **WHEN** a client triggers compaction through `POST /sessions/{session_id}/compact` and it fails
- **THEN** the endpoint SHALL return an error response, because the caller asked for compaction directly and is entitled to be told it did not happen

### Requirement: Recoverable model-cache failures log without a stack trace
A Valkey transport failure in the `BifrostClient` model cache SHALL be logged as a
single warning line naming the exception type and message, and SHALL NOT be logged with
exception info.

The model cache is an optimisation. Every reader already falls through to a live
Bifrost fetch when a read misses, so a transport failure changes latency and nothing
else. Emitting a stack trace presented a fully handled condition as a crash and
contributed to the log flood reported in DRA-35.

This requirement governs logging only. The existing degradation behaviour SHALL be
unchanged: a failed cache read SHALL still return no value and SHALL still allow the
caller to fetch live, and a failed cache write SHALL still be non-fatal.

#### Scenario: A failed cache read degrades quietly to a live fetch
- **WHEN** a cache read raises a connection error during `list_models`
- **THEN** the client SHALL log one warning without exception info and SHALL fetch the listing live from Bifrost

#### Scenario: A failed cache write does not fail the request
- **WHEN** a cache write raises a connection error after a successful live fetch
- **THEN** the client SHALL log one warning without exception info and SHALL return the fetched listing

### Requirement: A live event and the durable row it copies are one event to a client

The agent-orchestrator SHALL deliver an event that it both persists and publishes in
a form that lets a streaming client recognise the two copies as one event.

The job event stream has two sources for the same event: it replays persisted rows
and it forwards the live event bus. Because almost every event the orchestrator
publishes is also appended to the job's event list, most live events are a second,
earlier copy of a row the same stream will also yield from storage. That earliness
is the point of the bus and SHALL be preserved.

Where a
publisher has already persisted the event, the published copy SHALL carry the
identifier of that durable row, and the stream SHALL present the copy to the client
under that identifier rather than under an identifier belonging to the bus. A bus
identifier — a stream entry id, or a counter — identifies a delivery, not an event,
and SHALL NOT be what a client keys on when a durable identifier exists.

A publisher that has persisted nothing of its own SHALL publish without a durable
identifier, and such an event SHALL keep the bus identifier, because no replay will
ever repeat it. Two cases SHALL be treated this way: an event whose durable home is
a different job, and an in-progress streaming chunk, which is a growing prefix of an
unfinished row rather than a copy of a finished one and is reconciled by its own
snapshot identifier.

An event that the orchestrator both persists and publishes SHALL carry the same
payload in both copies, since the two collapse into one and a consumer SHALL NOT see
less after a reload than it saw live.

Where the durable row is appended by a component that has no access to the event bus,
the event SHALL NOT be published a second time from elsewhere. The stream's own replay
SHALL be relied on to deliver it.

Every SSE frame the stream emits SHALL carry an event identifier, whether it came from
replay or from the live bus.

#### Scenario: A live copy of a persisted event reuses its identifier

- **WHEN** the orchestrator appends an event to a job's event list and publishes the
  same event on the live bus
- **THEN** the stream SHALL deliver both copies to the client under the identifier of
  the persisted row
- **AND** a client that de-duplicates on that identifier SHALL be left with one event

#### Scenario: A published event with no persisted row keeps the bus identifier

- **WHEN** an event is published on the live bus without a corresponding row in the
  job's event list
- **THEN** the stream SHALL deliver it under the bus's own identifier
- **AND** SHALL NOT suppress it, because no replay will repeat it

#### Scenario: A question renders once

- **WHEN** a job asks the user a question while a client is streaming its events
- **THEN** the client SHALL receive one identifiable `user_question` event
- **AND** a transcript built from those events SHALL contain one question for it

#### Scenario: A stream in flight across a deploy is still read

- **WHEN** a subscriber reads a live event that was published before the durable
  identifier was carried
- **THEN** it SHALL treat the identifier as absent and deliver the event under the
  bus identifier, rather than failing to read it

### Requirement: Publishing a live job event is best-effort against its durable row
Publishing to the live job-event bus SHALL NOT be able to fail its caller. A transport
failure while publishing SHALL be logged and SHALL return no event, and the caller
SHALL proceed as though the publish had succeeded.

This is safe because of an invariant the job runtime already maintains: every event it
publishes has first been written to `job_events` in PostgreSQL, and the job event
stream polls that table as well as forwarding the live bus. A failed publish therefore
delays an event to the stream's next poll rather than losing it. The durable row is the
source of truth and the live bus is a latency optimisation, so the bus SHALL NOT be
able to cost a job its run.

Because a publish is issued once per streaming model delta, and each publish sits
inside the block whose handler marks the job failed, an unguarded publish made every
delta a chance to kill an otherwise healthy job — which is what DRA-42 reported as
orchestrator mode failing.

The tolerance SHALL be structural rather than per-call-site: the bus handed to the job
runtime SHALL be best-effort however that runtime was constructed, not only when it is
assembled by the application factory.

The scope of the tolerance SHALL be exactly this: publishing to the live bus. Writes to
PostgreSQL SHALL continue to raise, `append_event` included, since the durable row is
the thing being relied upon. `asyncio.CancelledError` SHALL NOT be caught, so worker
shutdown continues to cancel in-flight jobs.

One published event has no durable twin — the `compaction` summary, whose durable home
is the compaction job created alongside it rather than a row on the job being
compacted. Dropping its live copy SHALL be tolerated on the same terms: the running
transcript then shows the summary only after the session is reloaded, which is a
smaller loss than failing a job mid-compaction, and the drop SHALL be logged.

#### Scenario: A failed publish during a streaming delta does not fail the job
- **WHEN** every live publish raises a connection error while a prompt job streams a model response
- **THEN** the job SHALL reach status `"completed"` with its result text intact
- **AND** the `model_output` and `completion` events SHALL still be present as durable job events

#### Scenario: A publish failure is reported, not hidden
- **WHEN** a live publish fails
- **THEN** the service SHALL log the failure, naming the event type and the job

#### Scenario: A failing durable write still fails
- **WHEN** appending a job event to PostgreSQL raises
- **THEN** the error SHALL propagate to existing job failure handling rather than being tolerated

### Requirement: The job event stream degrades to durable polling when the live bus fails
A transport failure while reading the live event bus SHALL NOT terminate a job event
stream. The stream SHALL continue serving durable events from `list_events`, SHALL
retry the live bus, and SHALL resume live delivery once a read succeeds.

Propagating such a failure ended the streaming HTTP response, which surfaced to the
browser as `GET /jobs/{job_id}/events/stream` returning 500 and the live transcript
stopping mid-run (DRA-42). Since `list_events` yields every durable event, a client on
a degraded stream loses delivery latency and nothing else.

A live-bus failure SHALL be handled the same way a subscriber timeout is handled, so a
job that reaches a terminal status while the bus is unavailable SHALL still have its
remaining durable events delivered and its stream closed, rather than being left open.

While degraded, the retry delay SHALL be short enough that the durable poll — then the
stream's only source — keeps the transcript current, SHALL grow with consecutive
failures so a sustained outage is bounded in cost, SHALL be capped below the interval a
healthy stream blocks for so that degrading never increases latency, and SHALL be reset
by the first successful live read so a recovered stream returns to its normal, cheap
idle behaviour.

The retry SHALL reuse the existing subscriber rather than replacing it. A subscriber's
stream cursor advances only on a successful read, so retrying resumes exactly where it
stopped, whereas a replacement would restart from the beginning of the retained stream
and re-deliver events the client already has.

Backoff and failure counting for a degraded stream SHALL live with that stream and be
discarded when it ends. No shared or module-level registry SHALL be introduced.

#### Scenario: Durable events keep arriving while the live bus is down
- **WHEN** every live-bus read for a streaming client raises a connection error
- **THEN** the stream SHALL keep yielding events appended to `job_events`
- **AND** SHALL NOT raise out of the response

#### Scenario: A terminal job still closes a degraded stream
- **WHEN** a job reaches a terminal status while the live bus is unavailable
- **THEN** the stream SHALL deliver the remaining durable events and close

#### Scenario: Live delivery resumes after recovery
- **WHEN** the live bus fails and then succeeds for a stream that is still open
- **THEN** subsequently published events SHALL be delivered live again

### Requirement: A subagent wait falls back to the child's row when the live bus fails
A transport failure while consuming a child job's live events SHALL NOT propagate out
of a subagent wait. The wait SHALL fall back to re-reading the child's persisted row,
SHALL retry the live bus on a bounded backoff, and SHALL remain bounded by the same
absolute deadline.

The child's persisted status is already the authority for this wait; live events are
consumed only so the wait can return the moment the child finishes rather than on the
next poll. Losing them therefore costs the wait its early return and nothing else.
Before DRA-42 that read was unguarded, so a reset on a *child's* event stream escaped
`wait_for_subagent` and the tool dispatch and reached the *parent* job's failure
handler — a blip on one job's stream failing a different job, on the orchestrated
multi-agent path the issue was reported against.

#### Scenario: The child's live stream fails for the whole wait
- **WHEN** every live-bus read fails while a parent waits for a child, and the child then reaches `"completed"`
- **THEN** the wait SHALL return a `completed` outcome carrying the child's result
- **AND** SHALL NOT raise into the parent job

#### Scenario: The wait is still bounded
- **WHEN** the live bus fails repeatedly and the child never reaches a terminal status
- **THEN** the wait SHALL still end at its absolute deadline with a `timeout` outcome

### Requirement: A failing event-stream TTL refresh does not undo a published event

A publish SHALL NOT be able to fail *after* the event has reached the job's stream. Appending the event and refreshing that stream's time-to-live SHALL be one command, so there is no point in a publish at which the append has happened and the refresh has not.

DRA-42 reached the same outcome by tolerance: the refresh was a second command, a
reset on it aborted a publish whose event every subscriber had already received,
and that abort killed the model call that was mid-response. The guard that
swallowed it is removed here rather than kept, because the single command it is
replaced by leaves nothing for it to catch. Tolerance of a window is strictly
worse than not having the window, and a guard over an unreachable branch is
misleading to the next reader.

Appending the event SHALL continue to raise on failure. Losing the event itself is
a real failure, and the decision to tolerate it belongs to the layer that knows a
durable row was written — the best-effort wrapper every consumer in the running
service is handed, which turns it into a `None` return and a counted log line.

#### Scenario: The stream's expiry cannot fail apart from the append
- **WHEN** the Valkey-backed live event bus publishes an event
- **THEN** the expiry refresh SHALL be carried inside the same single command as the append
- **AND** no separate expiry command SHALL be issued that could fail on its own

#### Scenario: Appending the event still fails
- **WHEN** the single publish command raises a connection error
- **THEN** the publish SHALL raise to its caller
- **AND** the best-effort wrapper SHALL absorb it, returning no event rather than failing the job

### Requirement: Recoverable live-bus failures log one traceback per outage
Repeated failures of the same live-bus operation SHALL NOT emit one stack trace each.
The first failure of a streak SHALL be logged with exception info, later failures SHALL
be logged as counted warnings at a rate that grows sub-linearly with the streak length,
and the end of a streak SHALL be logged once with the number of failures it contained.

This extends the discipline established in DRA-35 to a call rate that change did not
face. The ingest loop it fixed is paced by a retry sleep, so one line per retry is
bounded; a live publish is paced by nothing and is issued once per streaming delta.
Emitting a line per failure there would replace a crash with a log flood, which was the
outcome DRA-35 set out to prevent.

#### Scenario: A long streak of failures is a handful of lines
- **WHEN** the same live-bus operation fails twenty consecutive times
- **THEN** exactly one log record SHALL carry exception info
- **AND** the number of warning records SHALL be substantially fewer than the number of failures

#### Scenario: Recovery is visible
- **WHEN** a live-bus operation succeeds after a streak of failures
- **THEN** one record SHALL report the recovery and the length of the streak

### Requirement: The live-event path's Valkey cost is proportional to work, not to tokens or to elapsed time

The agent-orchestrator live-event path SHALL keep its Valkey command count proportional to the work actually done, rather than to the number of tokens a model streamed or the number of seconds a job has been open.

The client this path uses opens a fresh TCP connection and emits one command span
for every command, so a Valkey command, a TCP connection and a span are one unit
of cost rather than three.

Three properties SHALL hold.

**Publishing one live event SHALL cost one Valkey round trip.** Appending the
event to the job's stream and re-arming that stream's expiry SHALL be performed
as a single command. The expiry SHALL be re-armed on every append, because a job
that publishes nothing for longer than the expiry loses its stream key and the
next append would recreate that key with no expiry at all and leak it. Splitting
the append and the expiry into separate commands SHALL be regarded as a defect:
a streamed model response publishes one live event per token, so it doubles the
cost of the busiest path in the service.

**A live-event subscriber SHALL read multiple stream entries per command.** A
read SHALL request a bounded batch and SHALL retain entries it has taken off the
stream but not yet handed to its caller, serving them without issuing a further
command. The subscriber's public contract SHALL remain one event per call, so no
caller changes. That retained batch SHALL belong to the single subscription that
fetched it — one SSE request or one subagent wait — SHALL be bounded by the batch
size, and SHALL be discarded when the subscription closes; it SHALL NOT be
process-lifetime state. The cursor a subscriber resumes from SHALL be the last
entry it handed to its caller, so a subsequent read never replays a buffered
batch.

**An idle event stream SHALL NOT poll at the worker's job-claim rate.** How long a
quiet stream waits on the live event bus before re-reading a job's status from the
database SHALL be its own configured value, and SHALL NOT be taken from the
setting that governs how quickly the worker claims a queued job. That value is a
fallback interval and not a delivery-latency budget: a published event ends the
wait immediately, so no event a client receives is delayed by lengthening it. What
it bounds is only the detection of a job that reached a terminal status while
publishing nothing.

#### Scenario: One live event is one Valkey command

- **WHEN** the agent-orchestrator publishes a live job event to the Valkey live
  event bus
- **THEN** it SHALL issue exactly one Valkey command, that command SHALL both
  append the event and re-arm the stream's expiry, the stream key SHALL be passed
  as a declared key rather than interpolated into a script body, and the returned
  event SHALL carry the entry identifier the append produced

#### Scenario: A burst of streamed events is drained in far fewer commands than events

- **WHEN** a subscriber consumes a burst of live events published for one job
- **THEN** the number of Valkey commands it issues SHALL be bounded by the number
  of batches rather than the number of events, and each event SHALL still be
  handed to the caller individually and in publication order

#### Scenario: A subscription's buffered entries do not outlive it

- **WHEN** a live-event subscription is closed
- **THEN** any stream entries it had fetched and not yet delivered SHALL be
  discarded, so no entry is retained beyond the request or wait that fetched it

#### Scenario: The idle stream interval is configured separately from the worker tick

- **WHEN** the agent-orchestrator constructs the job event stream
- **THEN** the interval an idle stream waits on the live event bus SHALL come from
  a dedicated setting with its own environment variable and its own
  positive-value validation, and SHALL NOT be the worker's job-claim poll interval

#### Scenario: A terminal event already delivered from the database closes the stream without waiting

- **WHEN** a job event stream has delivered a terminal event that it read from the
  database
- **THEN** it SHALL make its remaining persisted-event pass and close, without
  first waiting the idle fallback interval on the live event bus, so that
  lengthening that interval never makes closing a finished stream slower

### Requirement: An event a client waits on is published, not left to the stream's fallback poll

An event the agent-orchestrator persists SHALL also be published on the live event bus whenever a client's view of the job depends on receiving it promptly.

Because the SSE stream serves both the live bus and a periodic `list_events` read,
a durable row with no matching publish still reaches the client — but only on the
stream's next fallback pass. That interval is a cost control, not a delivery
mechanism, and SHALL NOT be relied on to deliver anything a user waits on. Two
consequences are normative.

**A terminal event SHALL be published.** Until a terminal event is *delivered* the
client's stream stays open, so an unpublished one leaves a user who has just
cancelled a job watching a stream that never closes. This binds every writer of a
terminal row, including the cancellation of a queued job no worker will ever run,
and including each active child job cancelled alongside its parent, since a child
may have its own reader.

**A tool call and its result SHALL be published.** A tool call is recorded before
the tool runs, which is exactly when the live bus falls quiet, so leaving these to
the fallback pass makes a slow tool indistinguishable from a stalled agent.

Every such publish SHALL carry the identifier of the durable row it copies, so the
live copy and the copy the fallback pass yields are one event to the client rather
than two. A repository method that appends such a row SHALL surface that
identifier to its caller, which is what holds the bus, and SHALL NOT be given the
bus itself.

An event no client waits on MAY be left to the fallback pass, and where that
choice is made it SHALL be recorded as deliberate rather than left to be
rediscovered.

#### Scenario: Cancelling a job reaches an open stream without waiting the fallback interval

- **WHEN** a job with an open event stream is cancelled, with the stream's idle
  fallback interval configured longer than a user would wait
- **THEN** the `cancellation` SHALL reach that stream at once rather than on its
  next fallback pass, and SHALL carry the identifier of the durable `cancellation`
  row so the client renders one cancellation and not two

#### Scenario: Requesting cancellation surfaces an identifier per affected job

- **WHEN** cancellation is requested for a job that has active child jobs
- **THEN** the repository SHALL report the durable `cancellation` row it appended
  for the job and for each affected child, so the caller can announce each on that
  job's own stream

#### Scenario: A tool call is visible before the tool has finished running

- **WHEN** the orchestrator records a tool call and then invokes a tool that takes
  longer than the stream's idle fallback interval to return
- **THEN** the `tool_call` SHALL already have reached an open stream, so the
  transcript shows the call in progress rather than nothing, and the matching
  `tool_result` SHALL reach it on the same terms

### Requirement: The skill catalogue reports each skill's reference files

The agent-orchestrator's skill catalogue SHALL report, for each discovered skill, the relative paths of that skill's markdown reference files. A skill with no reference files SHALL report an empty list rather than omitting the field, so a consumer never has to distinguish "no references" from "not reported".

The reported paths SHALL be exactly the names the skill's reference loader accepts, so a consumer can offer a listed reference for selection and have that selection resolve.

#### Scenario: A skill with references lists them

- **WHEN** the skill catalogue is read for a skill that has markdown files beside its `SKILL.md`
- **THEN** the catalogue entry SHALL list each of those files by its path relative to the skill directory

#### Scenario: A skill without references reports an empty list

- **WHEN** the skill catalogue is read for a skill whose directory holds only `SKILL.md`
- **THEN** the catalogue entry SHALL report an empty reference list

### Requirement: A session's own agent may run as a persona
A session SHALL be able to name a persona its **own** agent runs as, distinct from the persona its subagents are started from. The name SHALL be recorded on the session as a first-class field rather than inside the client-writable metadata blob, SHALL be accepted when the session is created and when it is updated, and SHALL be reported on every session response.

A session persona SHALL contribute exactly two things to that session's jobs: the persona's system prompt, delivered as its own clearly delimited section of the assembled system prompt placed after the base rules it cannot override, and the persona's tool allowlist, narrowing that session's tool surface by the same filter a subagent's persona applies. It SHALL NOT change the session's provider, model, gateway options, provider options, or enabled skills, because each of those is set by its own control on the same session and a persona overwriting what those controls write would make them misreport what the agent runs with.

Naming a persona that does not exist SHALL be rejected when the session is written, rather than discovered when a job runs.

#### Scenario: A session records and reports its persona
- **WHEN** a client creates or updates a session naming an existing persona as its own
- **THEN** the session SHALL record that persona
- **AND** every response for that session SHALL report it

#### Scenario: The persona's instructions reach the session's own agent
- **WHEN** a job runs on a session that has adopted a persona
- **THEN** the assembled system prompt SHALL contain that persona's prompt as a delimited section in addition to the base prompt parts

#### Scenario: The persona's tool allowlist narrows the session's tools
- **WHEN** a job runs on a session whose persona carries a tool allowlist
- **THEN** the tools offered to the model and the mapping used to dispatch a call SHALL both exclude every tool outside that allowlist

#### Scenario: The persona does not override the session's model
- **WHEN** a job runs on a session whose persona names a provider and a model
- **THEN** the request SHALL use the provider and model recorded on the session's own model configuration

#### Scenario: A session without a persona is unchanged
- **WHEN** a job runs on a session that has adopted no persona
- **THEN** the assembled system prompt SHALL contain no persona section

#### Scenario: An unknown session persona is rejected
- **WHEN** a client names a persona that does not exist as a session's own persona
- **THEN** the request SHALL be rejected with a client error naming the persona

### Requirement: A session persona is captured when it is assigned
The persona a session adopts SHALL be resolved and captured at the moment the name is set, and the captured record SHALL be what a job reads. Nothing at job run time SHALL re-read the persona table for the session's own persona.

Editing or deleting the persona afterwards SHALL NOT change a session that has already adopted it, for the same reason it does not change a subagent already started from it: a conversation that has taken turns as one agent must not be retroactively rewritten into a different one. Deleting the persona SHALL clear the session's persona **name**, so nothing re-adopts or reports a persona that is gone, and SHALL leave the captured record intact, so the turns already taken stay interpretable.

The captured record SHALL be owned by the server. A client SHALL change a session's persona by naming it, and a client-supplied metadata write SHALL be able neither to introduce a captured record the server did not write nor to remove one the server did write.

The captured record SHALL hold only the fields a session applies, so that it cannot suggest that a provider, a model, or a skill list was captured and then ignored.

#### Scenario: A persona edited later does not change the session
- **WHEN** a session has adopted a persona and that persona's prompt and tool allowlist are then changed
- **THEN** the session SHALL keep the prompt and allowlist captured when it adopted the persona

#### Scenario: A deleted persona clears the name and keeps the record
- **WHEN** a persona a session has adopted is deleted
- **THEN** the session SHALL no longer report that persona as its own
- **AND** the captured record SHALL remain on the session

#### Scenario: A metadata write cannot forge a captured persona
- **WHEN** a client updates a session's metadata with a captured persona record of its own
- **THEN** the server's captured record SHALL be kept and the client's SHALL be discarded

#### Scenario: A metadata write cannot drop a captured persona
- **WHEN** a client updates a session's metadata with a body that omits the captured persona record
- **THEN** the session SHALL keep the captured record and SHALL still report its persona

### Requirement: A session allowlists the personas its agent may spawn
A session SHALL record which personas its agent may start a subagent from. The allowlist SHALL be a per-session selection from the deployment-global persona catalogue, shaped like the session's skill selection: one entry per persona, an entry that is switched off SHALL NOT permit that persona, and an entry SHALL name a persona that exists.

**An empty allowlist SHALL mean that no persona may be spawned.** It SHALL NOT be interpreted as permitting every persona. Spawning a subagent with no persona at all — which copies the session's own configuration — SHALL be unaffected by the allowlist and SHALL remain available to every session.

The allowlist SHALL be manageable both as a whole, in the same request as the session fields it constrains, and one persona at a time, so a client holding a complete configuration and a client making a single change are both served.

Deleting a persona SHALL remove it from every session's allowlist, so no session is left permitting a name that no longer resolves.

#### Scenario: A new session permits no persona
- **WHEN** a session is created without an allowlist
- **THEN** its allowlist SHALL be empty and no persona SHALL be permitted

#### Scenario: A persona is allowed and reported
- **WHEN** a client allows a persona for a session
- **THEN** the session SHALL report that persona as allowed

#### Scenario: A switched-off entry does not permit the persona
- **WHEN** a session's entry for a persona is switched off
- **THEN** the session SHALL NOT report that persona as allowed and SHALL NOT permit spawning it

#### Scenario: Allowing an unknown persona is rejected
- **WHEN** a client allows a persona that does not exist
- **THEN** the request SHALL be rejected with a client error naming the persona

#### Scenario: Deleting a persona withdraws every allowance
- **WHEN** a persona that sessions have allowlisted is deleted
- **THEN** no session SHALL report it as allowed

### Requirement: The empty allowlist is stated, never inferred
Because an empty allowlist is the most restrictive state and an empty list is the shape most easily misread as "unrestricted", the API SHALL make the meaning explicit rather than leaving a caller to interpret an empty array.

Listing a session's permitted subagents SHALL return every persona in the catalogue together with whether that session allows it, rather than returning only the permitted names. Every field that carries the allowlist SHALL state in its published schema description that an empty list means no persona may be spawned.

#### Scenario: The listing states allowed and not allowed per persona
- **WHEN** a client lists a session's permitted subagents and personas exist that the session does not allow
- **THEN** the response SHALL include every persona
- **AND** each SHALL carry whether this session allows it

#### Scenario: The rule is published with the field
- **WHEN** a client or a model reads the schema of a field carrying the allowlist
- **THEN** the description SHALL state that an empty list means no persona may be spawned

### Requirement: The subagent allowlist is enforced when a subagent is started
The allowlist SHALL be enforced by the server at the point a spawn resolves which persona to use, not by whichever client displays it. A spawn naming a persona the session does not allow SHALL be refused, and the refusal SHALL apply however the persona was chosen: named by the agent in the tool call, or reached through the session's recorded default when the agent named none.

A refused spawn SHALL create no child session, no child job, and no subagent-started event. The refusal SHALL state that the restriction is enforced by the server and SHALL name the personas that are permitted, so an agent can correct the call rather than repeat it; when none are permitted the refusal SHALL say so plainly and point at spawning without a persona.

The catalogue of personas offered to an agent in its system prompt SHALL be the session's allowlist rather than the whole deployment catalogue, so an agent is not invited to name something that would be refused. That narrowing SHALL NOT be relied on as the enforcement, because an agent may name a persona the catalogue never mentioned.

#### Scenario: A persona off the allowlist is refused
- **WHEN** an agent calls the spawn tool naming a persona its session does not allow
- **THEN** the spawn SHALL be refused with an error result
- **AND** no child session, child job, or subagent-started event SHALL be created

#### Scenario: An empty allowlist refuses every persona
- **WHEN** an agent of a session with an empty allowlist names any persona on a spawn
- **THEN** the spawn SHALL be refused

#### Scenario: The session default is subject to the allowlist
- **WHEN** an agent spawns without naming a persona and the session's recorded default is not on the allowlist
- **THEN** the spawn SHALL be refused rather than falling through to that persona

#### Scenario: A direct API caller cannot bypass the allowlist
- **WHEN** a caller drives a prompt over the HTTP API whose agent names a persona the session does not allow
- **THEN** the spawn SHALL be refused by the server and no child SHALL be created

#### Scenario: An allowed persona still spawns
- **WHEN** an agent names a persona its session allows
- **THEN** the child SHALL be started from that persona as before

#### Scenario: The offered catalogue is the allowlist
- **WHEN** a top-level job's system prompt is assembled for a session that allows some but not all personas
- **THEN** the persona catalogue in that prompt SHALL list only the allowed personas

#### Scenario: An empty allowlist offers no catalogue
- **WHEN** a top-level job's system prompt is assembled for a session with an empty allowlist
- **THEN** the prompt SHALL contain no persona catalogue

### Requirement: The session default and the allowlist cannot contradict each other
A session's default subagent persona SHALL be one the session allows. A configuration in which the default is not permitted SHALL be rejected rather than stored, because its only observable effect would be a refusal on every plain spawn.

Both fields SHALL be validated against the state the request produces rather than the state already stored, so a single request that allows a persona and makes it the default SHALL succeed. A rejected combination SHALL leave the session unchanged, with neither field written.

Withdrawing a persona SHALL always be possible, but SHALL take the default with it: revoking the persona a session still defaults to SHALL be refused unless the same request also clears the default.

#### Scenario: A default outside the allowlist is rejected
- **WHEN** a client sets a default subagent persona that the resulting allowlist does not contain
- **THEN** the request SHALL be rejected with a client error
- **AND** neither the allowlist nor the default SHALL be changed

#### Scenario: Allowing and defaulting in one request succeeds
- **WHEN** a client allows a persona and names it as the default in the same request
- **THEN** the request SHALL succeed

#### Scenario: Revoking the default persona alone is refused
- **WHEN** a client revokes the persona that is still the session's default
- **THEN** the request SHALL be rejected and the allowlist SHALL be unchanged

#### Scenario: Revoking with the default cleared succeeds
- **WHEN** a client revokes that persona and clears the default in the same request
- **THEN** the request SHALL succeed and the session SHALL permit no persona by default

### Requirement: The session persona and the subagent allowlist stay editable
Neither a session's own persona nor its subagent allowlist SHALL be frozen once the session has run a job, unlike the session mode. No persistent record is keyed to either, so changing either abandons nothing, and the capture rule already guarantees that the turns a session has taken keep the configuration they ran under.

The allowlist in particular SHALL remain editable for the life of the session, because a permission that cannot be withdrawn while a session is running cannot be used at the moment it matters most. A tightened allowlist SHALL take effect on the next spawn.

#### Scenario: The persona changes after the first job
- **WHEN** a client changes the persona of a session that has already run a job
- **THEN** the change SHALL be accepted

#### Scenario: A permission is withdrawn mid-session
- **WHEN** a client removes a persona from the allowlist of a session that has already spawned a subagent from it
- **THEN** the change SHALL be accepted
- **AND** a later spawn naming that persona SHALL be refused

### Requirement: The reason a model stopped is captured on every response shape

The gateway client SHALL carry the model's stop reason on every chat response it
returns, so that a caller can distinguish a model that finished its answer from
one the provider cut off. A caller SHALL NOT have to inspect the raw response
body to learn it, because that body has two different shapes — a list of
streamed chunks when streaming and the whole response document when not — and a
caller that has to know which is a caller that will eventually handle only one.

The stop reason SHALL be read from one choice in a fixed priority order: the
OpenAI-compatible `finish_reason` first, then OpenRouter's `native_finish_reason`
passthrough of the upstream provider's own value, then an Anthropic-shaped
`stop_reason` at either the choice or the message level. A normalised value
therefore always wins over a vendor spelling of the same thing.

When streaming, the stop reason SHALL be taken from the **last** chunk that
carries a non-null one, because providers differ over whether they send it on the
final chunk or earlier.

A response that carries no stop reason in any of those positions SHALL report
none, rather than a guess inferred from the response's content.

#### Scenario: A streamed response reports why it stopped
- **WHEN** the gateway streams a completion whose final chunk carries `finish_reason` of `"length"`
- **THEN** the returned response SHALL report a stop reason of `"length"`

#### Scenario: A non-streamed response reports why it stopped
- **WHEN** the gateway returns a completion whose choice carries `finish_reason` of `"stop"`
- **THEN** the returned response SHALL report a stop reason of `"stop"`

#### Scenario: A vendor spelling is not lost
- **WHEN** a choice carries no `finish_reason` but carries `native_finish_reason` or an Anthropic-shaped `stop_reason`
- **THEN** the returned response SHALL report that value

#### Scenario: A normalised reason wins over a vendor one
- **WHEN** a choice carries both `finish_reason` and `native_finish_reason`
- **THEN** the returned response SHALL report the `finish_reason` value

#### Scenario: No stop reason is reported as none
- **WHEN** a response carries no stop reason in any recognised position
- **THEN** the returned response SHALL report no stop reason, and SHALL NOT infer one from the content

### Requirement: A turn truncated at the provider's output cap is continued automatically

A response carrying no tool calls SHALL NOT on its own be treated as the end of a
turn. A response truncated at the provider's output-token cap has exactly that
shape — some partial content, or none at all when a reasoning model spent its
whole budget thinking, and no tool calls — and completing the job on it reports a
turn the provider cut off as a turn the model finished.

When a response carries no tool calls **and** a stop reason meaning the output cap
was reached, the worker SHALL continue the same turn rather than complete the job:
it SHALL append the partial assistant content to the in-flight messages and a
continuation instruction as a user message, and take another round of the existing
tool-round loop.

The partial assistant content SHALL be appended only when it is non-empty, because
a provider may reject an assistant message with empty content and a reasoning model
can legitimately return none.

The vocabulary of stop reasons that mean truncation SHALL be matched
case-insensitively across vendors and SHALL cover at least OpenAI's `length`,
Anthropic's `max_tokens`, Gemini and Vertex's `MAX_TOKENS` and `max_output_tokens`,
and `max_completion_tokens`. Every other value — `stop`, `end_turn`, `tool_calls`,
`content_filter`, an unrecognised value, the empty string, and no value at all —
SHALL NOT be treated as truncation, so a model that chose to end its turn is never
forced onward.

The worker SHALL NOT infer truncation from the shape of the output — empty content,
absent tool calls, or content that does not end in sentence punctuation. Those fire
on legitimate short answers and would force a model onward for reasons unrelated to
any provider limit.

A turn that was continued and then finished SHALL reach status `completed`, because
it did finish. Its result text SHALL be every segment the turn produced joined in
order, not only the final one.

The tool-round-limit interrupt SHALL be unaffected: exhausting the round budget
SHALL still end the job as `interrupted` with its own message.

#### Scenario: A truncated turn is resumed rather than reported as finished
- **WHEN** a response carries no tool calls and a stop reason of `"length"`
- **THEN** the worker SHALL continue the turn with the partial content and a continuation instruction in the messages
- **AND** SHALL NOT mark the job completed on that response

#### Scenario: A model that chose to stop is left alone
- **WHEN** a response carries no tool calls and a stop reason of `"stop"`, `"end_turn"`, an unrecognised value, or none at all
- **THEN** the worker SHALL complete the job on that response

#### Scenario: A continued turn returns the whole answer
- **WHEN** a turn is truncated once and the continuation finishes it
- **THEN** the job SHALL reach status `completed`
- **AND** its result text SHALL contain both the partial segment and the continued segment, in order

#### Scenario: An empty partial output is not sent back as an empty assistant message
- **WHEN** a truncated response carries no content at all
- **THEN** the worker SHALL append only the continuation instruction, and SHALL NOT append an assistant message with empty content

### Requirement: Automatic continuation is bounded and can be disabled

Automatic continuation calls a paid provider without being asked, so it SHALL be
bounded and SHALL be switchable off.

The worker SHALL support a per-turn maximum number of automatic continuations,
configurable through `AUTO_CONTINUE_MAX_CONTINUATIONS`, defaulting to 3, and
rejected at startup when configured below 1. When the maximum is reached, the turn
SHALL complete exactly as it does with the behaviour absent, leaving the manual
follow-up available.

The counter SHALL be per turn and SHALL reset on any round that produced tool
calls, so what it bounds is consecutive truncations — a model that will not stop
being truncated — rather than unrelated truncations spread across a long turn.

The worker SHALL support disabling the behaviour entirely through
`AUTO_CONTINUE_TRUNCATED_TURNS`, defaulting to enabled. When disabled, a truncated
turn SHALL complete exactly as it does today.

Continuations SHALL consume rounds of the existing tool-round budget, so a
misconfigured continuation cap can never make a turn outlive that budget.

A cancellation requested during a continuation chain SHALL be honoured at the next
round boundary, with the same latency as a cancellation requested during a tool
call.

#### Scenario: A model that truncates every time still terminates
- **WHEN** every response is truncated and carries no tool calls
- **THEN** the worker SHALL continue the turn at most the configured maximum number of times
- **AND** SHALL then complete the job

#### Scenario: The behaviour can be switched off
- **WHEN** automatic continuation is disabled and a truncated response carries no tool calls
- **THEN** the worker SHALL complete the job on that response
- **AND** SHALL NOT record a continuation event

#### Scenario: A cancel during a continuation chain is honoured
- **WHEN** a cancellation is requested while a turn is being continued
- **THEN** the job SHALL reach status `cancelled` at the next round boundary

#### Scenario: A continuation cap below one is rejected
- **WHEN** `AUTO_CONTINUE_MAX_CONTINUATIONS` is configured as 0 or negative
- **THEN** configuration SHALL be rejected with a validation error

### Requirement: An automatic continuation never sends an over-window request

A continuation SHALL NOT be made when the request it would send does not fit the
model's context window. Each continuation makes the request strictly longer, and a
request can already approach or exceed that window before any continuation happens.
Continuing into that produces a truncate-continue-truncate spiral in which every
extra call is both futile and paid for.

Before each continuation the worker SHALL estimate the request it is about to send —
the in-flight messages including the partial content and the continuation
instruction — and SHALL refuse the continuation when that estimate reaches the same
budget automatic compaction uses, the model's context window multiplied by the
compaction threshold. A refused continuation SHALL complete the turn normally and
SHALL be logged with the estimate and the budget.

The estimate SHALL be produced by the service's existing context estimation, not by
a second estimator, so "too big to continue" and "too big to send" cannot drift
apart.

The context window SHALL be resolved from the gateway's model metadata, falling
back to the configured default window when the gateway cannot say, and SHALL be
resolved only when a truncation actually occurs so the ordinary path pays nothing
for it.

Automatic compaction SHALL NOT be invoked to make room. Compaction rewrites
persisted history and cannot shrink a message list already assembled for the turn
in progress, and shrinking it would discard the partial output the continuation
depends on.

#### Scenario: A request at the context budget is not continued
- **WHEN** a truncated response arrives and the request that a continuation would send is estimated at or above the context budget
- **THEN** the worker SHALL complete the turn
- **AND** SHALL NOT record a continuation event

#### Scenario: An unknown context window falls back rather than refusing everything
- **WHEN** the gateway reports no context length for the model
- **THEN** the worker SHALL apply the configured default context window size

### Requirement: An automatic continuation is recorded as its own event

The user SHALL be able to see that the service resumed a turn rather than that the
model produced one unbroken answer. Each automatic continuation SHALL be recorded
as a durable `turn_continued` job event, persisted and published under the durable
row's id so a live copy collapses into it rather than rendering twice.

Its payload SHALL carry the reason for the continuation, the raw provider stop
reason that triggered it, the 1-based continuation number, and the configured
maximum.

`turn_continued` SHALL NOT be a terminal event type in the job event stream: a
continued turn has not ended, and closing the stream on it would strand every
client watching the rest of the turn.

The partial output SHALL remain in the transcript as its own `model_output` event,
so the transcript reads as partial output, continuation marker, continued output.

Any event type the worker emits SHALL be registered in the dashboard's stream event
list, because the browser subscribes per named event type and silently drops any
type absent from that list.

A `turn_continued` event SHALL be replayed into a later turn's message history as a
note that the service resumed the turn, so the model is not shown two adjacent
assistant segments with no account of why they are separate.

#### Scenario: The seam is durably recorded
- **WHEN** a truncated turn is continued
- **THEN** a `turn_continued` job event SHALL be persisted with the provider stop reason, the continuation number and the configured maximum
- **AND** SHALL be published under the durable row's id

#### Scenario: A continuation does not close the event stream
- **WHEN** a client is streaming a job's events and a `turn_continued` event is emitted
- **THEN** the stream SHALL remain open and SHALL continue delivering the rest of the turn

#### Scenario: The partial output survives
- **WHEN** a truncated turn is continued
- **THEN** the partial segment SHALL remain a `model_output` event preceding the `turn_continued` event
- **AND** the continued segment SHALL be a separate `model_output` event following it

#### Scenario: A later turn is told the service resumed the earlier one
- **WHEN** a session whose history contains a `turn_continued` event is replayed for a later turn
- **THEN** the replayed history SHALL state that the service continued the turn automatically

