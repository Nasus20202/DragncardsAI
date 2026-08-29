## MODIFIED Requirements

### Requirement: Context metadata endpoint
The system SHALL expose `GET /sessions/{session_id}/context` returning current context health metadata.

The session context metadata endpoint SHALL estimate context usage from the content the orchestrator would include in the next model request, rather than from cumulative historical job token totals.

That estimate SHALL include the system prompt generated from active skill summaries and the persona catalogue, replayed prior messages after compaction and replay-window limits are applied, any conversation a restore attached to the session, any currently running job's prompt and recorded job events (including in-progress tool calls, tool results, and model outputs), and every tool definition the next top-level job would be offered — built-in tools as well as those exposed from active MCP assignments, gated by the session's mode and seat as a real job's registry gates them.

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

#### Scenario: Running job events count toward context usage
- **WHEN** a session has an active job with status `running` that has recorded a prompt and one or more `JobEvent`s
- **THEN** `GET /sessions/{session_id}/context` SHALL include the running job's prompt and recorded events in the estimated next-request context usage
