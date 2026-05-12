## Why

The orchestrator currently treats provider timeouts, 429s, invalid tool calls, and MCP transport failures as terminal too early, which makes long-running agent sessions brittle even when the failure is transient or recoverable on a later attempt. It also replays too much raw history into prompt context by default, and operators cannot tune how many recent conversational messages and tool exchanges are retained for the next model call.

## What Changes

- Add resilient execution handling so prompt jobs retry on transient provider and tool failures instead of stopping on the first recoverable error
- Turn invalid or unavailable tool invocations into error tool results returned to the model instead of terminal job failures
- Distinguish retryable and non-retryable execution failures for provider errors, MCP timeouts, and genuine local execution bugs, while still logging each failure attempt for observability
- Add configurable replay controls for orchestrator sessions, including how many recent conversational messages and how many recent tool exchanges are retained in model context
- Keep tool-output retention small by default and treat state-heavy game-service calls as the most replaceable historical tool context when newer state exists
- Expose the new context controls in the dashboard session configuration UI and return them in session detail APIs
- Update message-history construction to honor the configured limits while preserving enough recent conversation and tool context for coherent agent behavior

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-orchestrator`: Change job execution requirements to support recoverable retries and configurable replay limits for multi-turn context construction
- `dashboard`: Change session configuration requirements to expose context replay controls alongside existing model settings

## Non-Goals

- Replacing the existing compaction model or removing compaction records
- Adding provider-specific retry policies beyond the shared transient-failure behavior needed for this change
- Introducing a new prompt-authoring UX or changing how prompts are submitted
- Perfect token-optimized summarization of all historical tool payloads in this first pass
- Per-tool custom formatting policies in the first version of replay controls

## Impact

- **agent-orchestrator**: worker retry classification, invalid-tool recovery, job-attempt logging, session configuration schema, context replay builder, and API serializers
- **dashboard**: session settings drawer, draft state, client API types, and save flows for replay limits
- **tests**: unit coverage for invalid-tool recovery, retry classification, recency-based replay trimming, and dashboard configuration flows
