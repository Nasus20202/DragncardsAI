## ADDED Requirements

### Requirement: Multi-turn memory session flag
The agent-orchestrator SHALL support a `multi_turn_memory` boolean flag on `AgentSession` (default `true`). When `false`, job workers SHALL build a fresh messages list with no replay of prior job events, preserving existing behavior.

#### Scenario: Session created with multi-turn memory enabled
- **WHEN** a session is created without specifying `multi_turn_memory`
- **THEN** `multi_turn_memory` SHALL default to `true`

#### Scenario: Session created with multi-turn memory disabled
- **WHEN** a session is created with `multi_turn_memory: false`
- **THEN** each job for that session SHALL start with a fresh messages list containing only the current system prompt and user input

### Requirement: Prior job event replay
When `multi_turn_memory` is enabled, the job worker SHALL replay prior job events for the session into the messages list before the current user prompt.

Replay order SHALL be: for each prior job in chronological order — user prompt, assistant output, tool calls and results interleaved, then continue to next job.

If a `CompactionRecord` exists for the session, the worker SHALL:
1. Inject the compaction summary as a system message
2. Replay only jobs created **after** the `CompactionRecord.covers_up_to_job_id`

#### Scenario: No prior jobs, no compaction record
- **WHEN** a job starts for a session with no prior jobs and `multi_turn_memory: true`
- **THEN** the messages list SHALL contain only the system prompt and current user prompt

#### Scenario: Prior jobs exist, no compaction record
- **WHEN** a job starts for a session with N prior completed jobs and no `CompactionRecord`
- **THEN** the messages list SHALL begin with the system prompt, followed by all prior job events replayed in order, then the current user prompt

#### Scenario: Compaction record exists
- **WHEN** a job starts and a `CompactionRecord` exists for the session
- **THEN** the messages list SHALL begin with the original system prompt, then the compaction summary as a second system message, then only events from jobs after `covers_up_to_job_id`, then the current user prompt

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

Response SHALL include:
- `tokens_used`: sum of `tokens_used` across jobs since last compaction (or all jobs if no compaction)
- `context_window_size`: configured `CONTEXT_WINDOW_SIZE`
- `usage_ratio`: `tokens_used / context_window_size` as float 0.0–1.0
- `compaction_count`: number of `CompactionRecord` rows for this session
- `last_compacted_at`: `created_at` of most recent `CompactionRecord`, or `null`
- `multi_turn_memory`: current value of the session flag

#### Scenario: Retrieve context metadata
- **WHEN** a client sends `GET /sessions/{session_id}/context`
- **THEN** the response SHALL be HTTP 200 with JSON containing all six fields

#### Scenario: Session not found
- **WHEN** a client sends `GET /sessions/{session_id}/context` for a non-existent session
- **THEN** the response SHALL be HTTP 404
