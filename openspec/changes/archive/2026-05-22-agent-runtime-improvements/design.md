## Context

The agent-orchestrator runs LLM jobs by building a system prompt, wiring tools, and executing a tool-call loop. Before this change:

- The system prompt was three lines ("You are an agent orchestrator…", "Use tools…", "Rely on function schema.") — insufficient to guide the model on tool selection, context discipline, or subagent delegation.
- The tool round limit was 32 and, when hit, raised a `RuntimeError` that marked the job `"failed"`. Failed jobs were excluded from context replay, so the next turn had no knowledge of what had been partially done.
- `spawn_subagent`'s tool description said nothing about which tools require delegation or that the tool is unavailable to child jobs. Children attempted to call it and either got a tool-not-found error or silently failed.
- Reasoning was disabled by default across all dashboard sessions.

## Goals / Non-Goals

**Goals:**
- System prompt gives the model actionable guidance at every decision point: identity, tool usage, context discipline, subagent use cases, game-service specifics, error handling, response style.
- `spawn_subagent` tool description enforces delegation policy at tool-selection time (where it actually matters).
- Tool round limit hits are recoverable: job is marked `"interrupted"`, partial work is preserved and replayed into the next turn with a synthetic note.
- Real failures (`"failed"` jobs from exceptions) also replay partial work into context.
- Reasoning is on by default for all dashboard sessions; smoketest opts out via env var.

**Non-Goals:**
- Changing the multi-turn memory or compaction architecture.
- Modifying how the LLM provider (Bifrost) handles reasoning tokens.
- Adding per-session tool round limits (remains process-global).

## Decisions

### 1. Interrupted vs Failed as distinct statuses

**Decision**: Introduce `"interrupted"` as a new terminal job status for tool-round-limit hits, separate from `"failed"` (unexpected exceptions).

**Rationale**: The two cases have different semantics for context replay. An interrupted job's partial work is valid and the model should continue from it. A failed job's partial work may be broken mid-tool-call and the model should treat it cautiously. Using the same status would require heuristics to distinguish them at replay time. A separate status is explicit and lets the replay layer apply the right synthetic note.

**Alternative considered**: Mark all non-completions as `"failed"` with an error code. Rejected because it conflates two distinct recovery paths.

### 2. Synthetic assistant notes in replay

**Decision**: Append a `role: assistant` message at the end of an interrupted or failed job's replay items, explaining the status in plain language.

**Rationale**: The model needs to understand why a prior turn ended abnormally. A synthetic note in the assistant role is the natural position in the conversation flow (after the last tool result, before the next user message). Using `role: system` was considered but would inject outside the expected turn structure.

### 3. Tool description as the primary enforcement mechanism for subagent delegation

**Decision**: The `spawn_subagent` tool description explicitly names the tools that must be delegated and states it is only available to top-level jobs.

**Rationale**: The system prompt is read once at job start. Tool selection decisions happen turn-by-turn based on the tool schema. A model that has "forgotten" the system prompt's delegation rules will still read the tool description when choosing between `search_cards_marvel_champions` and `spawn_subagent`. Putting the enforcement there is more reliable than relying solely on system prompt recall.

### 4. Reasoning default via dashboard config, not agent-orchestrator

**Decision**: `DEFAULT_REASONING_ENABLED` is a dashboard env var that controls the session draft default, not an agent-orchestrator setting.

**Rationale**: Reasoning is a per-session model config option (`gateway_options.reasoning`), set when a session is created. The agent-orchestrator has no concept of "default gateway options" — it accepts whatever the client sends. Keeping the default in the dashboard (the session creation UI) is architecturally clean and consistent with how other session defaults (`DEFAULT_PROVIDER_ID`, `DEFAULT_MODEL_NAME`) already work.

## Risks / Trade-offs

- **Interrupted jobs in replay add context tokens**: Replaying failed/interrupted jobs increases context usage per turn. Mitigated by the existing state-heavy exchange eviction logic and compaction.
- **Synthetic notes could confuse some models**: A `role: assistant` message that doesn't come from the model itself is unusual. Kept terse and bracketed (`[Previous turn was interrupted…]`) to signal it is metadata, not a real model output.
- **Raising tool round limit to 64 doubles worst-case loop length**: A runaway tool loop now costs twice as many LLM calls before terminating. Acceptable because the subagent delegation guidance significantly reduces main-thread tool usage for well-behaved runs.
- **Reasoning may not be supported by all providers/models**: `gateway_options.reasoning` is spread into the Bifrost request payload. Providers that don't support it will likely ignore the field. If a provider errors on unknown fields, the session will fail to complete — but this was already true for any misconfigured `gateway_options`.
