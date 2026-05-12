## 1. Session Replay Settings Contract

- [x] 1.1 Add durable `AgentSession` fields and migration for `context_recent_message_limit` and `context_recent_tool_exchange_limit`
- [x] 1.2 Extend orchestrator session request/response schemas, serializers, and repository methods to read and persist the replay settings alongside `multi_turn_memory`
- [x] 1.3 Add unit tests for session create/read/update flows covering unlimited replay defaults and explicit replay-window values

## 2. Retryable Failure Classification In The Worker

- [x] 2.1 Add a worker-side execution failure classifier that produces `code`, `message`, and `retryable` for Bifrost, MCP, and local execution errors
- [x] 2.2 Update job failure handling so retryable failures append failure events, close the current attempt, and re-queue the job when `max_attempts` allows
- [x] 2.3 Convert invalid model tool invocations into `tool_result` error feedback that keeps the job running instead of failing the attempt
- [x] 2.4 Add worker unit tests for retryable provider failures, retryable MCP transport failures, invalid-tool recovery, and non-retryable local execution bugs

## 3. Exchange-Based Context Replay Limiting

- [x] 3.1 Refactor replay reconstruction so tool context is tracked and retained as exchanges made of assistant tool calls plus matching tool results
- [x] 3.2 Update message-history reconstruction to apply `context_recent_message_limit` by recency after compaction-aware replay is built
- [x] 3.3 Update replay trimming to enforce `context_recent_tool_exchange_limit` by recency while preserving exchange integrity
- [x] 3.4 Add state-heavy tool-exchange classification so newer state-producing game-service exchanges displace older state-producing exchanges when tool memory is tight
- [x] 3.5 Add unit tests for unlimited replay, message-limited replay, tool-exchange-limited replay, state-heavy exchange displacement, and compaction-summary preservation

## 4. Dashboard Replay Controls

- [x] 4.1 Extend dashboard shared types, session draft helpers, and client API payloads to include the new replay-window settings
- [x] 4.2 Add structured recent-message and recent-tool-exchange controls to the play settings panel with validation and clear unlimited-state behavior
- [x] 4.3 Add dashboard component and draft tests covering existing-session load, save validation, and unlimited replay display

## 5. End-To-End Verification

- [ ] 5.1 Add or update orchestrator API tests to confirm session detail responses include replay settings, invalid tool calls stay in-band, and retryable failures preserve attempt history while re-queueing jobs
- [x] 5.2 Run the relevant unit test suites for `agent-orchestrator` and `dashboard`, fixing any regressions introduced by the new retry and replay-limit behavior

## 6. Context Usage Envelope Accuracy

- [x] 6.1 Update orchestrator context metadata calculation to estimate the next request envelope from system prompt, bounded replay history, and active tool definitions instead of cumulative historical job totals
- [x] 6.2 Add or update orchestrator tests covering replay-limited context usage, compaction-summary inclusion, and active skill/tool contribution in context metadata
- [ ] 6.3 Update dashboard context-health behavior or tests as needed to reflect the bounded next-request estimate returned by the orchestrator
