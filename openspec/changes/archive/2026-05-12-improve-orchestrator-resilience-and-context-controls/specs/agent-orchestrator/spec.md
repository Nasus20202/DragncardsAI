## MODIFIED Requirements

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

### Requirement: Context metadata reflects the next request envelope
The session context metadata endpoint SHALL estimate context usage from the content the orchestrator would include in the next model request, rather than from cumulative historical job token totals.

That estimate SHALL include the system prompt generated from active skills, replayed prior messages after compaction and replay-window limits are applied, and tool definitions exposed from active MCP assignments.

That estimate SHALL NOT include prior history excluded by replay limits, inactive assignments, or a future user prompt that has not yet been submitted.

#### Scenario: Replay-limited session reports bounded context usage
- **WHEN** a session has replay-window limits configured and prior history exceeds those limits
- **THEN** the context metadata endpoint SHALL estimate tokens from only the retained replay subset plus the current system prompt and active tool definitions

#### Scenario: Skills and MCP tools count toward context usage
- **WHEN** a session has active skill assignments or MCP tool definitions available to the worker
- **THEN** the context metadata endpoint SHALL include their contribution in the estimated next-request context usage

#### Scenario: Historical job token totals do not override bounded replay estimate
- **WHEN** stored completed jobs report large `tokens_used` values that exceed what bounded replay would include next
- **THEN** the context metadata endpoint SHALL report the bounded next-request estimate rather than the historical aggregate

## ADDED Requirements

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
