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

#### Scenario: Configure supported provider
- **WHEN** a client configures a session with one of OpenRouter, Mistral, Claude, OpenAI, LM Studio, or Gemini
- **THEN** the system SHALL persist the provider configuration and validate that the provider is known to the Bifrost gateway configuration

#### Scenario: Reject unsupported provider
- **WHEN** a client configures a session with an unknown provider identifier
- **THEN** the system SHALL reject the request with a validation error and SHALL NOT change the session model configuration

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

### Requirement: MCP assignment
The system SHALL allow clients to assign and remove MCP server/tool configurations for an agent session, including the game-service MCP.

#### Scenario: Assign game-service MCP
- **WHEN** a client assigns the game-service MCP to an agent session
- **THEN** prompt jobs for that session SHALL be able to call the assigned game-service MCP tools during orchestration

#### Scenario: Inspect MCP assignments
- **WHEN** a client retrieves an agent session
- **THEN** the response SHALL include the MCP assignments available to prompt jobs for that session

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

### Requirement: Prior job event replay
When `multi_turn_memory` is enabled, the job worker SHALL replay prior job events for the session into the messages list before the current user prompt.

Replay order SHALL be: for each prior job in chronological order - user prompt, assistant output, tool calls and results interleaved, then continue to next job.

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
Before building the messages list for a new job, when `multi_turn_memory` is enabled, the system SHALL compute the estimated context size from `tokens_used` across jobs since the last compaction. If the ratio exceeds `CONTEXT_COMPACTION_THRESHOLD`, the system SHALL compact automatically before proceeding.

Threshold is configured via `CONTEXT_COMPACTION_THRESHOLD` env var (float, default `0.8`). Context window size via `CONTEXT_WINDOW_SIZE` (int, default `128000`).

Auto-compaction SHALL log an INFO entry recording the pre-compaction usage ratio.

#### Scenario: Auto-compaction fires at threshold
- **WHEN** a job starts and estimated usage ratio exceeds `CONTEXT_COMPACTION_THRESHOLD`
- **THEN** the system SHALL compact before building the messages list
- **AND** SHALL log INFO with the pre-compaction ratio

#### Scenario: No auto-compaction below threshold
- **WHEN** a job starts and estimated usage ratio is below `CONTEXT_COMPACTION_THRESHOLD`
- **THEN** the system SHALL proceed without compaction

### Requirement: Context metadata endpoint
The system SHALL expose `GET /sessions/{session_id}/context` returning current context health metadata.

The session context metadata endpoint SHALL estimate context usage from the content the orchestrator would include in the next model request, rather than from cumulative historical job token totals.

That estimate SHALL include the system prompt generated from active skills, replayed prior messages after compaction and replay-window limits are applied, and tool definitions exposed from active MCP assignments.

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

#### Scenario: Job is cancelled
- **WHEN** a client requests cancellation for a queued or running job
- **THEN** the system SHALL persist the cancellation request and the worker SHALL stop the job before any further model or MCP calls when cancellation is observed

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
