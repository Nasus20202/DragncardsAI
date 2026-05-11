## 1. Multi-Turn Memory — Session Flag

- [x] 1.1 Add `multi_turn_memory` boolean column to `AgentSession` DB model (default `true`), with migration
- [x] 1.2 Expose `multi_turn_memory` in session create request schema and `SessionDetail` response schema
- [x] 1.3 Add repository method to read and update `multi_turn_memory` on a session
- [x] 1.4 Write unit tests for session creation with `multi_turn_memory` true/false and default behavior

## 2. Multi-Turn Memory — Job Event Replay

- [x] 2.1 Implement `build_message_history(session_id)` function: queries prior job events in order and reconstructs messages list
- [x] 2.2 Handle `CompactionRecord` in replay: inject summary as system message, replay only jobs after `covers_up_to_job_id`
- [x] 2.3 Update job worker to call `build_message_history` at job start when `multi_turn_memory` is enabled
- [x] 2.4 Write unit tests for replay with no prior jobs, with prior jobs, and with a compaction checkpoint

## 3. Token Usage Tracking

- [x] 3.1 Add `tokens_used` integer column to `Job` DB model, with migration
- [x] 3.2 Extract `usage.total_tokens` from `ChatResponse.raw` after each LLM call in the worker
- [x] 3.3 Persist extracted token count to `Job.tokens_used`; fall back to tiktoken estimate when absent and log WARNING
- [x] 3.4 Write unit tests for token extraction (present, absent/fallback)

## 4. CompactionRecord

- [x] 4.1 Create `CompactionRecord` DB model and migration: `id`, `session_id`, `summary_text`, `covers_up_to_job_id`, `tokens_used`, `created_at`
- [x] 4.2 Implement `create_compaction_record(session_id)` repository method: calls LLM with summarization prompt, persists record
- [x] 4.3 Write summarization prompt that instructs preservation of: hero HP, threat levels, villain phase, encounter deck status, cards in play
- [x] 4.4 Write unit tests for compaction record creation and that raw `JobEvent` rows are not deleted

## 5. Manual Compaction Endpoint

- [x] 5.1 Implement `POST /sessions/{session_id}/compact` router and handler
- [x] 5.2 Return 409 when `multi_turn_memory` is disabled on the session
- [x] 5.3 Return updated context metadata on success (reuse context metadata query)
- [x] 5.4 Write unit tests for manual compaction (success, 404, 409)

## 6. Auto-Compaction at Job Start

- [x] 6.1 Implement `estimate_usage_ratio(session_id)`: sums `tokens_used` across jobs since last compaction divided by `CONTEXT_WINDOW_SIZE`
- [x] 6.2 Read `CONTEXT_COMPACTION_THRESHOLD` (default `0.8`) and `CONTEXT_WINDOW_SIZE` (default `128000`) from env/settings
- [x] 6.3 Add pre-job check in worker: if ratio exceeds threshold, compact before building message history; log INFO with ratio
- [x] 6.4 Write unit tests for auto-compaction trigger (above threshold, below threshold, memory disabled)

## 7. Context Metadata Endpoint

- [x] 7.1 Implement `GET /sessions/{session_id}/context` returning `tokens_used`, `context_window_size`, `usage_ratio`, `compaction_count`, `last_compacted_at`, `multi_turn_memory`
- [x] 7.2 Write unit tests for context metadata endpoint (active session, no compactions, post-compaction, 404)

## 8. Dashboard — Context Health Indicator

- [x] 8.1 Add context health widget to the session detail panel: progress bar, usage %, token counts, compaction count, last-compacted timestamp
- [x] 8.2 Color progress bar: neutral below 70%, amber 70–85%, red above 85%
- [x] 8.3 Fetch `GET /sessions/{id}/context` on session load and after each job completion; update indicator
- [x] 8.4 Show "Memory off" state and disable Compact button when `multi_turn_memory` is false
- [x] 8.5 Write component tests for indicator rendering, color thresholds, and memory-off state

## 9. Dashboard — Compact Button

- [x] 9.1 Add Compact button to context health widget; disable during active job
- [x] 9.2 On click: POST to `/sessions/{id}/compact`, refresh indicator on success, show error on failure
- [x] 9.3 Write component tests for button enabled/disabled states and post-compaction indicator refresh
