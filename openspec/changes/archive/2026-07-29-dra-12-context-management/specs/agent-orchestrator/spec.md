## MODIFIED Requirements

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

### Requirement: Context metadata endpoint
The system SHALL expose `GET /sessions/{session_id}/context` returning current context health metadata.

The session context metadata endpoint SHALL estimate context usage from the content the orchestrator would include in the next model request, rather than from cumulative historical job token totals.

That estimate SHALL include the system prompt generated from active skill summaries, replayed prior messages after compaction and replay-window limits are applied, and tool definitions exposed from active MCP assignments.

That estimate SHALL NOT include prior history excluded by replay limits, inactive assignments, or a future user prompt that has not yet been submitted.

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

#### Scenario: Historical job token totals do not override bounded replay estimate
- **WHEN** stored completed jobs report large `tokens_used` values that exceed what bounded replay would include next
- **THEN** the context metadata endpoint SHALL report the bounded next-request estimate rather than the historical aggregate

#### Scenario: Session not found
- **WHEN** a client sends `GET /sessions/{session_id}/context` for a non-existent session
- **THEN** the response SHALL be HTTP 404

## ADDED Requirements

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
