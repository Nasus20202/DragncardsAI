## Context

The current worker already has most of the building blocks for resilient execution, but it stops short of using them consistently. `BifrostError` already carries a `retryable` flag and `mark_job_failed()` already re-queues jobs when `retryable` is true and attempts remain, yet the worker still treats MCP failures and model-emitted invalid tool calls as terminal `execution_error`s. That makes prompt jobs fragile during normal provider throttling, network instability, or tool transport hiccups even though the job model and repository can support retries.

The current multi-turn memory path also replays all eligible prior job events after compaction without a session-level bound, and game-service tool results can be large because state reads, action responses, and card search responses often include substantial payloads. That was acceptable for the first memory release, but now that the dashboard exposes more session configuration and the replay code reconstructs tool traffic verbatim, operators need a way to budget how much recent conversation and how many recent tool exchanges are carried forward. The design should fit the existing session model, serializer, and dashboard draft flow rather than introducing a separate context-settings resource.

Stakeholders are the orchestrator worker, the dashboard session settings UI, and operators running long Marvel Champions sessions where context pressure and transient provider faults are common. We do not control upstream DragnCards behavior, so retries must stay inside the orchestrator's provider and MCP boundaries.

## Goals / Non-Goals

**Goals:**
- Retry prompt jobs when the failure is transient or recoverable, including provider timeouts, 429s, MCP transport errors, and selected invalid tool-call states that can be surfaced back to the model on a later attempt
- Preserve per-attempt observability by recording failure events and attempt logs even when the job is re-queued
- Convert invalid tool invocations into structured tool-error feedback to the model without failing the job attempt
- Add session-level replay controls that bound how many recent conversational messages and tool exchanges are replayed
- Prefer the newest state-heavy tool exchanges over older ones so game-state payloads do not crowd out all other recent tool context
- Expose those controls through existing session APIs and the dashboard configuration panel
- Keep the replay builder deterministic so tests can validate exactly which messages and tool results are kept
- Make context-health metadata reflect the estimated next request envelope rather than cumulative historical usage

**Non-Goals:**
- Replacing compaction with a different memory architecture
- Building adaptive retry policies per provider or exponential backoff infrastructure outside the worker/job queue model
- Adding token-aware compression of arbitrary tool payloads in this change
- Adding provider- or tool-specific summarizers in the first iteration
- Changing DragnCards room behavior, Phoenix session semantics, or upstream plugin protocols

## Decisions

### D1: Introduce a first-class retryability classifier for worker execution failures

**Decision**: Add a small worker-side classification layer that maps runtime exceptions and error states to `{code, message, retryable}` before persisting failure events and calling `mark_job_failed()`. `BifrostError.retryable` remains authoritative for provider failures. MCP transport/timeouts become retryable execution failures. Irrecoverable repository/serialization problems remain non-retryable. Invalid model-requested tool usage is handled separately as in-band tool feedback instead of a job failure.

**Alternatives considered**:
- *Keep the existing split of `BifrostError` retryable and everything else fatal*: rejected because it preserves the current brittleness and ignores the repository's existing retry support.
- *Move retry classification into the repository layer*: rejected because retryability depends on runtime exception types and tool/provider semantics that the repository should not own.
- *Retry every exception until `max_attempts` is exhausted*: rejected because it would hide deterministic bugs and produce noisy repeated failures.

**Rationale**: The worker already owns execution semantics and knows whether an error came from the provider, MCP transport, or model/tool exchange. A classifier keeps the change local, makes tests straightforward, and lets the job repository continue to handle status transitions without embedding transport-specific knowledge.

### D2: Treat invalid tool invocations as tool feedback, not attempt failure

**Decision**: When the model requests an unknown tool, malformed arguments that fail local validation, or a tool assignment that is no longer callable in the current session, the worker will append a `tool_result` event with `is_error: true` and a compact explanation, then continue the round so the model can recover within the same job attempt. This path does not mark the job failed unless a deeper local execution bug prevents constructing the error result itself.

**Alternatives considered**:
- *Fail the whole attempt immediately*: rejected because it punishes recoverable model mistakes and prevents the agent from correcting itself.
- *Silently drop the invalid tool call*: rejected because the model needs explicit feedback to change behavior.
- *Convert every invalid tool call into a retry of the whole job*: rejected because the problem is usually local to the model turn, not the entire attempt.

**Rationale**: Invalid tool invocation is agent behavior, not infrastructure failure. The most useful response is to tell the model what went wrong in the tool channel it already understands, then let it continue.

### D3: Keep retries job-based rather than adding inline round retries

**Decision**: A recoverable failure re-queues the whole job for another attempt instead of retrying only the failing LLM round or tool call inline. Each attempt rebuilds messages from persisted history, including prior failure/tool-result context when appropriate.

**Alternatives considered**:
- *Retry only the provider request inline inside the same attempt*: rejected because it complicates streaming state, partial DB writes, and cancellation handling.
- *Retry only MCP tool calls inline*: rejected because the worker would need separate backoff and idempotency rules for every tool surface.
- *Introduce a dedicated retry queue with delayed scheduling*: rejected for this change because the existing queue and attempt counters already solve the immediate requirement.

**Rationale**: The current job model already persists attempts, failures, and queued/running state transitions. Re-queuing the whole job gives one consistent recovery path and avoids partial-attempt semantics that would be difficult to reason about with streaming output and tool events.

### D4: Add session-level replay window controls as explicit fields on `AgentSession`

**Decision**: Store replay controls directly on `AgentSession` as durable session configuration, alongside `multi_turn_memory`. The minimum set is:
- `context_recent_message_limit`: maximum number of recent prior conversational messages to replay; `null` or `0` means unlimited
- `context_recent_tool_exchange_limit`: maximum number of recent tool exchanges to replay; `null` or `0` means unlimited

The replay builder applies these limits after compaction summary injection and before appending the current user prompt.

**Alternatives considered**:
- *Store replay limits in `gateway_options` or `provider_options`*: rejected because replay policy is orchestrator behavior, not provider configuration.
- *Store replay limits in session metadata JSON*: rejected because it weakens validation and makes the dashboard contract implicit.
- *Use token estimation only, with no explicit counts*: rejected because operators asked for a simple knob for “how many messages” and replay tests need deterministic boundaries.

**Rationale**: These limits are session behavior, need first-class validation, and belong in the same API surface as other session controls. Explicit fields also make the dashboard form simpler than burying the values in generic JSON editors.

### D5: Retain tool context by exchange, not by raw result message

**Decision**: Replay retention is based on tool exchanges, not bare `tool_result` messages. A tool exchange means the assistant tool call plus its matching tool result. If a tool exchange is retained, both sides are replayed together. If it is not retained, both sides are dropped from replay together.

**Alternatives considered**:
- *Retain only tool results and not the matching assistant tool-call structure*: rejected because replay would become structurally inconsistent and harder for the model to follow.
- *Retain tools purely as individual message tails*: rejected because the logical unit the model reasons about is the exchange, not one half of it.

**Rationale**: The model needs to see why a tool was called and what came back. Treating the exchange as the atomic replay unit keeps history coherent while still letting us keep tool retention small.

### D6: Trim replay by recency, with state-heavy tool exchanges treated as the most replaceable tool context

**Decision**: Replay trimming is recency-based. The builder reconstructs the full ordered history for eligible jobs, then keeps the newest prior conversational messages up to `context_recent_message_limit` and the newest prior tool exchanges up to `context_recent_tool_exchange_limit`. Within tool exchanges, state-heavy game-service calls such as full state reads and state-returning actions are treated as highly replaceable once newer state-heavy exchanges exist, so replay favors the newest state-heavy exchange plus the most recent non-state exchanges when the tool budget is tight.

**Alternatives considered**:
- *Trim by job count*: rejected because one job can contain many tool turns and would not match the user’s request to control “how many messages” go into context.
- *Trim by estimated tokens only*: rejected because it is harder to explain in the UI and less deterministic for tests.
- *Summarize old tool results on the fly*: rejected because it adds a second memory transformation path on top of compaction.
- *Treat all tool exchanges identically*: rejected because repeated full game-state responses can crowd out more useful recent lookup or action-support context.

**Rationale**: Recent turns are usually the most relevant for agent continuity. In this repo, game-state-producing calls are also the most redundant once a newer state exists. Small, recent tool memory works better when we preserve at most the newest state-heavy exchange and let the remaining budget capture other recent tool context.

### D7: Surface replay controls in the dashboard as structured form fields, not only advanced JSON

**Decision**: Extend the existing session draft/UI with dedicated fields for replay controls near reasoning and memory settings. The advanced JSON editors remain available, but recent-message and recent-tool-exchange limits are shown as normal inputs with validation and sensible empty-state semantics for “unlimited”.

**Alternatives considered**:
- *Expose replay controls only through raw JSON*: rejected because the user explicitly wants them configurable in the UI and they are core orchestrator controls, not obscure overrides.
- *Create a separate context-settings modal*: rejected because the current config drawer already owns session-level knobs.

**Rationale**: The dashboard already edits session-level reasoning and MCP settings. Replay limits fit that mental model and should be easy to discover without asking users to know internal JSON shapes.

### D8: Context-health metadata should estimate the next request envelope, not raw historical totals

**Decision**: The context metadata endpoint should estimate tokens from the same categories the next prompt execution would send to the model: the generated system prompt including active skill markdown, the bounded replay message list after compaction and replay-window trimming, and the active tool definitions exposed from MCP assignments. It should not sum persisted `Job.tokens_used` across prior jobs as the primary usage metric once replay windows exist, because those totals represent past executions rather than the next request payload.

**Alternatives considered**:
- *Keep reporting cumulative post-compaction `Job.tokens_used`*: rejected because it overstates context usage once replay windows exclude older history.
- *Report replay history only and ignore skills/tools*: rejected because the system prompt and tool schema payloads are part of the actual Bifrost request budget.
- *Report separate numbers for history, skills, and tools only in the UI while leaving backend metadata unchanged*: rejected because the source-of-truth estimate should live in the orchestrator, not be reconstructed independently in the dashboard.

**Rationale**: Operators use the context widget to judge whether the next prompt is likely to fit. The only defensible estimate is one based on what the worker would actually send next. Skills and MCP tool definitions consume tokens just like replayed messages do, so they belong in that estimate.

## Risks / Trade-offs

- **[Risk] Retryable classification could mark deterministic tool-contract bugs as recoverable** -> Mitigation: keep unknown local tool names, schema violations, and serialization failures non-retryable; cover edge cases with worker unit tests.
- **[Risk] Even one retained state-heavy tool exchange may still be large** -> Mitigation: keep tool exchange retention very small by default and preserve compaction as the broader history control.
- **[Risk] Re-queued jobs may replay prior failure/tool context in a way that nudges the model into loops** -> Mitigation: include only the persisted failure context needed for the next attempt and continue to cap total attempts with the existing `max_attempts` guard.
- **[Risk] Message-count limits are simpler than token limits but do not perfectly predict actual prompt size** -> Mitigation: keep compaction and token metadata in place; replay limits are an operator-facing coarse control, not a replacement for token tracking.
- **[Risk] Context metadata estimation may still differ slightly from provider-side accounting** -> Mitigation: use the same approximate local token estimator already used elsewhere, and make sure the estimate follows the same prompt-construction categories as the worker.
- **[Risk] Dropping older tool exchanges may omit details still needed for DragnCards reasoning** -> Mitigation: keep recency ordering, preserve compaction summaries, and favor the newest state-heavy exchange plus the newest non-state exchanges when the tool budget is tight.
- **[Risk] Upstream DragnCards or MCP behavior may produce repeated transient failures outside our control** -> Mitigation: retries stay bounded by `max_attempts`, failures are logged per attempt, and no retry logic depends on modifying upstream Phoenix or plugin behavior.

## Migration Plan

- Add database fields and schema updates for the new session replay-window controls
- Update session serializers and dashboard client types so existing sessions receive default unlimited behavior when values are absent or null
- Deploy invalid-tool recovery, worker retry classification, and replay trimming together so the UI and backend stay aligned on the new configuration contract
- Rollback by ignoring the new session fields in code; existing persisted values are additive and do not require data backfill cleanup

## Open Questions

- Which MCP-declared tool errors, if any, should remain in-band tool feedback versus escalating to retryable attempt failure?
- Should the dashboard show helper text about the interaction between replay limits and compaction so operators understand which control to reach for first?
