## Why

The AI agent has no memory across prompt runs — each job starts with a blank message history. For a game like Marvel Champions that unfolds over many turns, this means the agent can't reason about what it did two rounds ago, can't learn from prior tool calls, and can't maintain coherent strategy across a session. Additionally, as multi-turn history accumulates, there's no visibility into context window pressure and no mechanism to prevent silent degradation when the window fills.

## What Changes

- Add optional multi-turn memory to agent sessions: prior job events are replayed into each new job's message history
- Track token usage per job from LLM response metadata and persist it
- Introduce compaction: a persistent `CompactionRecord` that summarizes history up to a point, used as a checkpoint for future replay
- Support both manual compaction (user-triggered via dashboard button) and auto-compaction (fires before job start when usage exceeds threshold)
- Expose context metadata via API so the dashboard can display real-time context health
- Add a context health indicator and Compact button to the dashboard UI

## Capabilities

### Modified Capabilities

- `agent-orchestrator`: Multi-turn memory, token tracking, compaction records, context metadata API, and auto-compaction
- `dashboard`: Add context health indicator and Compact button surfacing agent-orchestrator context metadata

## Non-Goals

- Modifying the DragnCards backend or upstream plugin
- Deleting raw `JobEvent` rows after compaction (kept for audit)
- Per-session configurable auto-compaction threshold (env var default only for v1)
- Multi-model token counting (targets the configured model only)

## Impact

- **agent-orchestrator**: New `multi_turn_memory` session flag; token usage extraction from LLM responses; new `CompactionRecord` DB table; new `/sessions/{id}/compact` and `/sessions/{id}/context` endpoints; worker updated to replay history and check threshold at job start
- **Dashboard UI**: New context health indicator (token bar, usage %, compaction count, last compacted); Compact button
- **No breaking changes** to existing session, job, or action APIs
