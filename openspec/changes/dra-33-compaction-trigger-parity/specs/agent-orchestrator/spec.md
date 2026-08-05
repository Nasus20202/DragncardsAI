## MODIFIED Requirements

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
