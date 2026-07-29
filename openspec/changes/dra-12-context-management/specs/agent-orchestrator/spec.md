## MODIFIED Requirements

### Requirement: Manual compaction endpoint
The system SHALL expose `POST /sessions/{session_id}/compact` that triggers immediate compaction.

Compaction SHALL: call the LLM with a summarization prompt instructing preservation of hero HP, threat levels, villain phase, encounter deck status, and all cards in play; create a `CompactionRecord`; return updated context metadata.

The history a compaction summarizes SHALL be bounded, and its size SHALL NOT grow with the session's total length:

1. When a previous `CompactionRecord` exists, compaction SHALL summarize only jobs created after that record's `covers_up_to_job_id`, on top of that record's `summary_text`, which SHALL be supplied to the summarizing model as prior context. It SHALL NOT re-read history the previous summary already covers.
2. The text a single tool call or tool result contributes to the summarization input SHALL be bounded by a configured character budget. Where text is omitted, the input SHALL carry an explicit marker naming how much was omitted, so the summarizing model is not presented with a fragment as though it were complete.
3. The assembled summarization request SHALL be estimated before it is sent and SHALL NOT be sent larger than the compaction threshold applied to the model's context window. Where entries must be dropped to satisfy that bound, the oldest SHALL be dropped first, and the number dropped SHALL be recorded.

The manual endpoint SHALL additionally accept a request to summarize from the beginning of the session, ignoring the previous checkpoint, so a user who believes a summary has lost information can rebuild it from the retained raw events. Automatic compaction SHALL always use the checkpointed form.

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

#### Scenario: An oversized tool payload is truncated with a marker
- **WHEN** a tool call's arguments or a tool result's content exceeds the configured per-event character budget
- **THEN** the summarization input SHALL carry that payload truncated to the budget followed by a marker stating how many characters were omitted

#### Scenario: The summarization request is never assembled over the ceiling
- **WHEN** the assembled summarization request estimates above the compaction threshold applied to the model's context window
- **THEN** the system SHALL drop history entries oldest-first until the estimate is within the bound
- **AND** SHALL record how many entries were dropped

#### Scenario: Rebuilding a summary from session start
- **WHEN** a client sends `POST /sessions/{session_id}/compact` requesting summarization from the beginning of the session
- **THEN** compaction SHALL summarize every eligible job in the session regardless of any existing checkpoint

### Requirement: Auto-compaction at job start
Before sending the first model request for a new job, when `multi_turn_memory` is enabled, the system SHALL estimate the size of the request it is about to send and compact automatically if that estimate reaches `CONTEXT_COMPACTION_THRESHOLD` of the model's context window.

The estimate SHALL cover every part of the request, using the same tiktoken estimation the context metadata endpoint uses:

1. the system prompt built from the session's active skills and persona state,
2. the tool definitions exposed to the model, built-in and MCP alike,
3. the replayed prior message history, after compaction checkpoint and replay-window limits are applied,
4. the current turn's user message as the model will receive it, including the content of any skills the prompt loaded into itself.

The estimate SHALL NOT be taken from cumulative `tokens_used` on job rows, which reflects per-job LLM consumption and underestimates the request.

Because compaction can only reduce part (3), the system SHALL NOT attempt compaction when the pressure comes from the parts it cannot reduce. When the total estimate reaches the threshold but the replayed history is too small for a summary to be smaller than it, the system SHALL skip compaction and SHALL log that the threshold was reached by fixed request cost rather than by history.

Threshold is configured via `CONTEXT_COMPACTION_THRESHOLD` env var (float, default `0.8`). The context window SHALL be the provider-reported context length for the session's model where available, falling back to `CONTEXT_WINDOW_SIZE` (int, default `128000`).

Auto-compaction SHALL log an INFO entry recording the pre-compaction usage ratio and the component estimates it was computed from.

#### Scenario: Auto-compaction fires at threshold
- **WHEN** a job starts and the estimated request size divided by context window size reaches `CONTEXT_COMPACTION_THRESHOLD`, and the replayed history is large enough for compaction to reduce it
- **THEN** the system SHALL compact before sending the first model request
- **AND** SHALL log INFO with the pre-compaction ratio and its component estimates

#### Scenario: No auto-compaction below threshold
- **WHEN** a job starts and the estimated request size is below the threshold
- **THEN** the system SHALL proceed without compaction

#### Scenario: Skills loaded into the turn count toward the estimate
- **WHEN** a job's prompt loaded skill content into its own user message
- **THEN** the estimate SHALL include that rendered content, not only the stored prompt text

#### Scenario: Tool definitions and system prompt count toward the estimate
- **WHEN** a session exposes tool definitions and an active-skill system prompt to the model
- **THEN** the estimate SHALL include both alongside the replayed history

#### Scenario: Fixed request cost alone does not trigger repeated compaction
- **WHEN** the total estimate reaches the threshold but the replayed history is too small for a summary to be smaller than it
- **THEN** the system SHALL NOT call the summarizing model
- **AND** SHALL log that the threshold was reached by fixed request cost rather than by history

#### Scenario: Trigger and reported usage agree
- **WHEN** the auto-compaction check and the context metadata endpoint run for the same session with no job in between
- **THEN** both SHALL estimate the same replay, system prompt, and tool-definition contributions

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
Automatic compaction runs to protect a job from exceeding its context window, so its own failure SHALL NOT be the reason that job fails. When automatic compaction cannot complete, the worker SHALL log the failure with the usage ratio that triggered it, SHALL record a transcript-visible event naming the failure, and SHALL continue the job with the message history it already has.

A compaction attempt that finds nothing to summarize is not a failure: when the session has no eligible completed job or no history content, the worker SHALL treat it as a no-op, SHALL NOT record a failure event, and SHALL proceed.

Any event type the worker emits for this SHALL be registered in the dashboard's stream event list, because the browser subscribes per named event type and silently drops any type absent from that list.

#### Scenario: The summarizing model call fails
- **WHEN** automatic compaction is triggered and the summarizing model call fails
- **THEN** the worker SHALL log the failure with the triggering usage ratio
- **AND** SHALL record a transcript-visible event naming the failure
- **AND** SHALL continue the job with its existing message history rather than marking the job failed

#### Scenario: Nothing to compact is not a failure
- **WHEN** automatic compaction is triggered for a session with no eligible completed job or no history content
- **THEN** the worker SHALL proceed with the job
- **AND** SHALL NOT record a failure event

#### Scenario: Manual compaction still reports its errors
- **WHEN** a client triggers compaction through `POST /sessions/{session_id}/compact` and it fails
- **THEN** the endpoint SHALL return an error response, because the caller asked for compaction directly and is entitled to be told it did not happen
