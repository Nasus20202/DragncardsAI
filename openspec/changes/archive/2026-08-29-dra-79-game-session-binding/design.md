## Context

See `proposal.md` for the motivation. Prompt execution resolves the current session and a mapping of exposed MCP tool names to their assigned servers before processing each model tool call. The same loop performs seat scoping and turn/phase preflight, and the existing history-correlation path captures a game identifier after a successful game-service response.

The security decision must happen at the orchestrator boundary. Calling game-service to resolve or inspect an untrusted identifier before deciding whether it is allowed would preserve the confused-deputy path and could return another game's state.

## Goals / Non-Goals

**Goals:**

- Enforce the stored per-agent `metadata.game_id` binding on every mapped game-service tool call carrying an existing-game `session_id`.
- Run the binding check before seat checks, turn checks, and MCP transport dispatch so no preflight or downstream operation observes a cross-game target.
- Preserve the current first-call behavior for sessions that have not yet captured a game identifier.
- Keep rejected calls replayable by recording the attempted tool call and a local error tool result without copying a downstream response.

**Non-Goals:**

- Changing game-service authorization, seat identity, or turn/phase rules.
- Resolving room-slug aliases to canonical game IDs at the orchestrator layer.
- Restricting game creation or other lifecycle discovery calls that do not supply an existing-game `session_id`.

## Decisions

### Check at the prompt dispatch boundary

The prompt loop already has the authoritative session record and the resolved `SessionToolDefinition`, including the assigned server name. A pure guard runs immediately after the assistant tool call is added to the in-memory transcript and before seat/turn preflight or either builtin/MCP dispatch branch. It compares a non-empty direct `session_id` argument with the session's stored `metadata.game_id` only for the `game-service` assignment.

An alternative was to put the check in `McpToolCatalog.call_tool`. That layer has no agent session and is also used by internal best-effort state reads, so it would either lack the binding context or conflate trusted preflight reads with model calls. Keeping policy in the prompt loop makes every model dispatch path share one gate.

### Permit unbound first-call discovery

When `metadata.game_id` is absent, the guard returns no violation. The existing `_capture_game_id` path remains responsible for binding an identifier from a successful lifecycle/read result or the call's `session_id` argument. This preserves sessions that begin by creating, attaching, or discovering a game instead of requiring a preconfigured ID.

An alternative was to require an identifier to be provisioned before the first call. That would break the current create/attach workflow and would not satisfy the existing session-correlation contract.

### Refuse locally without a target-specific payload

A mismatch produces a generic local error tool result and skips `_mcp_tool_catalog.call_tool`. The refusal records a normal `tool_call`/`tool_result` pair so replayed provider messages remain well-formed. The refusal does not include either game identifier or a downstream result; the attempted arguments remain in the tool-call transcript because they are already model-authored input, not target state.

An alternative was to emit a new durable violation event. That would require extending every event consumer's stream type catalogue for no additional authorization value. The ordinary replayable error pair is sufficient to show the model that the call was refused while keeping this change confined to the orchestrator.

### Compare identifiers without resolving aliases

The guard performs an exact comparison against the stored identifier and does not call game-service to canonicalize a room slug. Game-service accepts room slugs as identifiers, but resolving one before authorization would make the authorization decision depend on an untrusted target request and could leak existence. Callers using the bound canonical identifier continue to work; alias support remains a separate capability decision.

### Preserve server-owned binding metadata

The session update endpoint treats `game_id`, `platform`, restored conversation
context, seat identity, and the orchestrator identity as server-owned metadata.
An ordinary metadata update removes client-supplied values for these keys and
restores the values already stored on the session. The protected keys are merged
inside the repository transaction, rather than only in the router's earlier
snapshot, so a concurrent first-call capture cannot be erased by a stale update.
This prevents a caller from forging a binding and also prevents a harmless
metadata edit from erasing the binding that later dispatch checks rely on.
Controlled restore and first-call capture paths continue to write these keys
directly.

### Serialize prompt execution per session

The worker wraps each prompt run in a Valkey lock keyed by the agent session
identifier. The lock is acquired before the run reloads session metadata and
therefore covers the binding check, seat and turn preflight, MCP dispatch, and
post-result capture. A lease and owner-token-checked release prevent a crashed
worker from holding the session forever or deleting a successor's lock. Direct
runtime unit tests may inject the disabled lock; deployed PostgreSQL-backed
workers use the shared Valkey connection.

### Keep player sessions on the parent game

An orchestrated parent must be bound before `prompt_player_agent` can create or
reuse a seat session. A reused child with a different game or explicit platform
is refused without enqueueing a job. An unbound child is filled with the parent's
binding through the repository's protected metadata merge, then re-read so a
concurrent child capture cannot silently replace it.

## Risks / Trade-offs

- A caller that supplies a room slug for a game stored by canonical UUID will receive a local mismatch refusal even when the slug denotes that same room. This conservative behavior avoids a pre-authorization lookup and leaves alias normalization to a future explicitly scoped change.
- The upstream game-service may independently reject or normalize identifiers, and its DragnCards WebSocket transport can report delayed state updates. This guard does not replace those checks; it prevents the request from reaching that transport unless the orchestrator already has an exact binding.
- Calls made by an unbound session remain able to choose their first target by design. The first-call contract is needed for game creation/attachment workflows, so operators must treat the initial successful binding as the session's security boundary thereafter.
