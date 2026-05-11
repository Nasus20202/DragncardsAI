## ADDED Requirements

### Requirement: Context health indicator
The dashboard UI SHALL display a context health indicator for the active session. The indicator SHALL show: a token usage progress bar, usage percentage, `tokens_used` / `context_window_size`, compaction count, and last-compacted timestamp (or "Never").

The indicator SHALL update after each job completes or compaction fires by re-fetching `GET /sessions/{session_id}/context`.

The progress bar SHALL change color based on usage ratio:
- Below 70%: neutral
- 70–85%: amber
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

#### Scenario: Multi-turn memory disabled
- **WHEN** `multi_turn_memory` is `false` for the active session
- **THEN** the indicator SHALL display a "Memory off" state and the Compact button SHALL be disabled

### Requirement: Compact button
The dashboard UI SHALL display a "Compact" button within the context health indicator widget. Clicking it SHALL send `POST /sessions/{session_id}/compact` and refresh the indicator on success.

#### Scenario: Compact button triggers compaction
- **WHEN** a user clicks the Compact button for an active session
- **THEN** the dashboard SHALL POST to `/sessions/{session_id}/compact`
- **AND** the indicator SHALL refresh with updated context metadata on success

#### Scenario: Compact button disabled during job
- **WHEN** a job is currently running for the session
- **THEN** the Compact button SHALL be disabled until the job completes
