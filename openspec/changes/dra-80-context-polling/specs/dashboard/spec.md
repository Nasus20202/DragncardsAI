## MODIFIED Requirements

### Requirement: Context health indicator

The dashboard UI SHALL display a context health indicator for the active session. The indicator SHALL show: a token usage progress bar, usage percentage, `tokens_used` / `context_window_size`, compaction count, and last-compacted timestamp (or "Never").

The dashboard SHALL present context usage as an estimate of the next orchestrator model request envelope, not as cumulative historical job usage.

The indicator SHALL update by re-fetching `GET /sessions/{session_id}/context` after each of the following events:
- A job completes, fails, or is cancelled
- A compaction fires
- The user saves session configuration, including model, skill, MCP, or replay-limit changes
- A generation starts, immediately and then periodically while that generation remains active

While a generation is active, the dashboard SHALL schedule the next context refresh only after the previous refresh settles, so context requests for the same session SHALL NOT overlap. The active-generation polling SHALL stop and its timer SHALL be cleaned up when generation ends, the selected session changes, or the Play workspace unmounts. Existing loading and non-fatal error behavior SHALL remain unchanged.

The progress bar SHALL change color based on usage ratio:
- Below 70%: neutral
- 70-85%: amber
- Above 85%: red

#### Scenario: Indicator shown for active session
- **WHEN** a session is active in the dashboard
- **THEN** the context health indicator SHALL be visible with all fields populated

#### Scenario: Indicator color reflects usage level
- **WHEN** `usage_ratio` exceeds 0.85
- **THEN** the progress bar SHALL render in red

#### Scenario: Indicator updates after compaction
- **WHEN** a compaction completes (manual or auto)
- **THEN** the indicator SHALL refresh and reflect reduced `tokens_used` and incremented `compaction_count`

#### Scenario: Indicator refreshes after configuration save
- **WHEN** the user saves session configuration
- **THEN** the context health indicator SHALL re-fetch `GET /sessions/{session_id}/context` immediately after the save completes successfully
- **THEN** the displayed token estimate SHALL reflect the updated system prompt, tool definitions, and replay window resulting from the new configuration

#### Scenario: Multi-turn memory disabled
- **WHEN** `multi_turn_memory` is `false` for the active session
- **THEN** the indicator SHALL display a "Memory off" state and the Compact button SHALL be disabled

#### Scenario: Context usage includes active prompt and tool scaffolding
- **WHEN** the dashboard displays context usage for an active session
- **THEN** the displayed estimate SHALL account for the active system prompt content, retained replay history, and active tool definitions returned by the agent-orchestrator

#### Scenario: Context usage respects replay limits
- **WHEN** replay-window settings exclude older history from the next request
- **THEN** the dashboard SHALL reflect the bounded estimate returned by the agent-orchestrator instead of implying that all prior messages still count equally

#### Scenario: Context usage refreshes while generation is active
- **WHEN** a selected session has an active generation
- **THEN** the dashboard SHALL refresh context metadata immediately
- **AND** SHALL re-fetch the context endpoint periodically until that generation ends
- **AND** SHALL display each settled response in the context health indicator

#### Scenario: Polling does not overlap context requests
- **WHEN** a context refresh takes longer than the polling interval
- **THEN** the dashboard SHALL wait for that request to settle before scheduling the next poll
- **AND** SHALL NOT issue concurrent context requests for the same active generation

#### Scenario: Polling cleans up when generation ends
- **WHEN** an active generation completes, fails, or is cancelled
- **THEN** the dashboard SHALL stop scheduling active-generation polls and SHALL immediately perform the existing terminal refresh
- **AND** SHALL clear the polling timer

#### Scenario: Polling cleans up when its dependencies change
- **WHEN** the selected session changes or the Play workspace unmounts while polling
- **THEN** the dashboard SHALL clear the active-generation timer
- **AND** SHALL NOT schedule another poll for the previous session

#### Scenario: Context refresh errors remain non-fatal
- **WHEN** a context metadata request fails during initial refresh or polling
- **THEN** the dashboard SHALL preserve the existing context display and continue the Play workspace without surfacing a new fatal error
