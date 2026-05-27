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

#### Scenario: Assign known skill
- **WHEN** a client assigns a skill identifier that exists under `skills/<skill_name>` in a configured skill root
- **THEN** the system SHALL persist the skill assignment for the session

#### Scenario: Reject unknown skill
- **WHEN** a client assigns a skill identifier that cannot be resolved from configured skill roots
- **THEN** the system SHALL reject the assignment and SHALL NOT persist it

### Requirement: System prompt construction uses skill summaries
The worker SHALL build the system prompt by including only a short skill summary for each assigned skill rather than the full `SKILL.md` content. Full skill content SHALL be delivered on demand through the built-in skill-loading tools.

#### Scenario: System prompt with assigned skills
- **WHEN** a job starts with skills assigned to the session
- **THEN** the system prompt SHALL contain an "Available skills" section listing each skill name and summary
- **THEN** the system prompt SHALL instruct the agent to call `load_skill` before using a skill and `load_skill_reference` only for the specific reference files it chooses to inspect
- **THEN** the system prompt SHALL NOT include the full body of any assigned `SKILL.md`

#### Scenario: System prompt with no assigned skills
- **WHEN** a job starts with no skills assigned
- **THEN** the system prompt SHALL contain the base identity and tool-usage instructions only

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
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, name the child session from the prompt, and return a tool result immediately containing the `child_job_id` and derived `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task SHALL monitor the child job, append the child outcome to the parent job's event log, and terminate the child session when the child reaches a terminal state.

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

#### Scenario: Background task monitors child and emits outcome
- **WHEN** the child job reaches a terminal state
- **THEN** a background coroutine SHALL append `subagent_completed` or `subagent_failed` to the parent job's event log
- **THEN** the background coroutine SHALL terminate the child session

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

### Requirement: Subagent jobs use a dedicated system prompt
Top-level jobs (where `parent_job_id` is null) SHALL receive the full system prompt built by `build_system_prompt`, which includes the subagent delegation section, context discipline rules, and large-payload tool blacklist.

Subagent jobs (where `parent_job_id` is not null) SHALL receive a separate, leaner prompt built by `build_subagent_system_prompt`, which:
- Identifies the job as a subagent with a bounded task
- Instructs it to call large-payload tools directly (`get_game_state`, `search_cards_marvel_champions`, etc.)
- Explicitly states that `spawn_subagent` and `wait_for_subagent` are unavailable and nesting is blocked
- Instructs it to return a concise, structured answer only

The subagent prompt SHALL NOT contain the top-level context-discipline rules that forbid large-payload tool calls, nor the `spawn_subagent`/`wait_for_subagent` usage guidance.

The system prompt SHALL identify the agent as an AI assistant for Marvel Champions on DragnCards and state its core responsibilities: set up games, manage the board, recommend plays, explain rules, and take game actions via tools.

#### Scenario: Top-level job receives full prompt
- **WHEN** a job with `parent_job_id = null` is started
- **THEN** the system prompt SHALL contain the subagent delegation section and the large-payload tool blacklist

#### Scenario: Subagent job receives lean prompt
- **WHEN** a job with `parent_job_id != null` is started
- **THEN** the system prompt SHALL NOT contain `spawn_subagent` delegation instructions
- **AND** SHALL instruct the agent to call large-payload tools directly
- **AND** SHALL state that `spawn_subagent` is unavailable

#### Scenario: System prompt contains domain identity
- **WHEN** a job is started for any session
- **THEN** the system prompt SHALL contain "DragnCardsAI" and reference "Marvel Champions"

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

Compaction SHALL: call the LLM with all replayed history and a summarization prompt instructing preservation of hero HP, threat levels, villain phase, encounter deck status, and all cards in play; create a `CompactionRecord`; return updated context metadata.

#### Scenario: Manual compaction succeeds
- **WHEN** a client sends `POST /sessions/{session_id}/compact`
- **THEN** the response SHALL be HTTP 200 with updated context metadata including incremented `compaction_count`

#### Scenario: Compaction on non-existent session
- **WHEN** a client sends `POST /sessions/{session_id}/compact` for a non-existent session
- **THEN** the response SHALL be HTTP 404

#### Scenario: Compaction when multi-turn memory is disabled
- **WHEN** a client sends `POST /sessions/{session_id}/compact` for a session with `multi_turn_memory: false`
- **THEN** the response SHALL be HTTP 409 with an error indicating compaction requires multi-turn memory

### Requirement: Auto-compaction at job start
Before building the messages list for a new job, when `multi_turn_memory` is enabled, the system SHALL estimate the replay context size by reconstructing the message history (using the same tiktoken estimation used by the context metadata endpoint) and computing the ratio against the configured context window size. If the ratio exceeds `CONTEXT_COMPACTION_THRESHOLD`, the system SHALL compact automatically before proceeding.

The system SHALL NOT use cumulative `tokens_used` from job rows as the threshold signal, since that value reflects per-job LLM consumption and underestimates the actual replay message size.

Threshold is configured via `CONTEXT_COMPACTION_THRESHOLD` env var (float, default `0.8`). Context window size via `CONTEXT_WINDOW_SIZE` (int, default `128000`).

Auto-compaction SHALL log an INFO entry recording the pre-compaction usage ratio.

#### Scenario: Auto-compaction fires at threshold
- **WHEN** a job starts and the estimated replay message token count divided by context window size exceeds `CONTEXT_COMPACTION_THRESHOLD`
- **THEN** the system SHALL compact before building the messages list
- **AND** SHALL log INFO with the pre-compaction ratio

#### Scenario: No auto-compaction below threshold
- **WHEN** a job starts and the estimated replay message token count is below the threshold
- **THEN** the system SHALL proceed without compaction

### Requirement: Context metadata endpoint
The system SHALL expose `GET /sessions/{session_id}/context` returning current context health metadata.

The session context metadata endpoint SHALL estimate context usage from the content the orchestrator would include in the next model request, rather than from cumulative historical job token totals.

That estimate SHALL include the system prompt generated from active skill summaries, replayed prior messages after compaction and replay-window limits are applied, and tool definitions exposed from active MCP assignments.

That estimate SHALL NOT include prior history excluded by replay limits, inactive assignments, or a future user prompt that has not yet been submitted.

Response SHALL include:
- `tokens_used`: estimated tokens for the next request envelope
- `context_window_size`: configured `CONTEXT_WINDOW_SIZE`
- `usage_ratio`: `tokens_used / context_window_size` as float 0.0-1.0
- `compaction_count`: number of `CompactionRecord` rows for this session
- `last_compacted_at`: `created_at` of most recent `CompactionRecord`, or `null`
- `multi_turn_memory`: current value of the session flag

#### Scenario: Retrieve context metadata
- **WHEN** a client sends `GET /sessions/{session_id}/context`
- **THEN** the response SHALL be HTTP 200 with JSON containing all six fields

#### Scenario: Replay-limited session reports bounded context usage
- **WHEN** a session has replay-window limits configured and prior history exceeds those limits
- **THEN** the context metadata endpoint SHALL estimate tokens from only the retained replay subset plus the current system prompt and active tool definitions

#### Scenario: Skills and MCP tools count toward context usage
- **WHEN** a session has active skill assignments or MCP tool definitions available to the worker
- **THEN** the context metadata endpoint SHALL include their contribution in the estimated next-request context usage

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
- A model whose `id` contains `/` but does not start with `<provider_prefix>/` is accepted only if `provider_id` is `openrouter`, because OpenRouter legitimately resells models from other cloud providers (e.g. `openai/gpt-4o-mini`).
- A model whose `id` contains no `/` is accepted for `openai` and `lmstudio` providers (which return unprefixed IDs), and for any provider whose `id` or prefix matches the model `id` prefix.

#### Scenario: Same-provider prefixed model accepted
- **WHEN** Bifrost returns a model id starting with `<provider_prefix>/` for that provider
- **THEN** the orchestrator SHALL include it in the provider's model list

#### Scenario: Cross-provider model accepted for openrouter
- **WHEN** Bifrost returns a model id such as `openai/gpt-4o-mini` for the `openrouter` provider
- **THEN** the orchestrator SHALL include it because OpenRouter legitimately resells cross-provider models

#### Scenario: Cross-provider model rejected for non-openrouter provider
- **WHEN** Bifrost returns a model id containing `/` that does not start with the provider's own prefix, for a provider that is not `openrouter`
- **THEN** the orchestrator SHALL exclude it from that provider's model list

#### Scenario: Bifrost fallback leaks lmstudio models into openrouter
- **WHEN** `openrouter` has no API key configured and Bifrost falls back to returning lmstudio models
- **THEN** those `lmstudio/...` models SHALL still appear under `openrouter` (accepted by the cross-provider rule) until a valid OpenRouter API key is configured — the correct fix is the environment, not the filter
