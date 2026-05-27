## Why

The agent-orchestrator's `BifrostClient` caches provider model listings in instance memory (`self._models_cache`, `self._all_models_cache`). This violates the project's stateless service rule and breaks correctness when multiple replicas run: each replica maintains its own stale or warm cache independently, and a restart silently drops all cached data. Moving the cache to Valkey makes it shared, replica-safe, and consistent with how the rest of the service handles transient state.

## What Changes

- Remove `self._models_cache` and `self._all_models_cache` dict/field from `BifrostClient`
- Add a Valkey-backed cache implementation for model listings (keyed by provider/scope, TTL-managed natively by Valkey)
- `BifrostClient` receives a Valkey client (or abstraction) at construction time instead of holding in-memory dicts
- `list_models` and `_fetch_all_models` read/write Valkey instead of instance fields
- `AGENTS.md` (root and agent-orchestrator) updated to reinforce the no-in-memory-state rule

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: Provider model cache storage changes from in-process memory to Valkey; `BifrostClient` construction gains a required Valkey dependency

## Impact

- `services/agent-orchestrator/src/agent_orchestrator/integrations/bifrost.py` — remove in-memory cache fields; add Valkey read/write
- `services/agent-orchestrator/src/agent_orchestrator/runtime/app.py` — pass Valkey client when constructing `BifrostClient`
- `services/agent-orchestrator/src/agent_orchestrator/storage/db.py` (or Valkey init module) — ensure Valkey client is available at startup
- `AGENTS.md` (root) and `services/agent-orchestrator/AGENTS.md` — add explicit rule: services must not store state in memory; use Valkey for ephemeral shared state
- Unit and integration tests for `BifrostClient` model-listing paths
