## Context

`BifrostClient` (in `integrations/bifrost.py`) caches provider model listings using two instance-level dicts: `self._models_cache` (keyed by `provider_id`) and `self._all_models_cache`. TTL is enforced by comparing `monotonic()` timestamps stored in `CachedModelListing`. This is pure in-process state — invisible to other replicas, lost on restart, and inconsistent with the project rule that services must not store state in memory.

The agent-orchestrator already uses Valkey for job-event streaming via `ValkeyLiveEventBus`. The Valkey URL is available in settings as `valkey_url`, and a raw RESP connection is managed by `_RespConnection` in `live_events.py`.

## Goals / Non-Goals

**Goals:**
- Replace the two in-memory cache dicts in `BifrostClient` with Valkey-backed GET/SETEX calls
- Make `BifrostClient` stateless (no mutable instance fields after construction)
- Reuse the existing Valkey connection infrastructure already present in the service
- Update `AGENTS.md` files to make the no-in-memory-state rule explicit

**Non-Goals:**
- Changing how the Valkey connection is managed at the infrastructure level
- Caching `chat_completion` responses
- Modifying the Bifrost HTTP API or provider configuration
- Adding cache invalidation endpoints

## Decisions

### D1: Use Valkey native TTL (`SETEX`) instead of `monotonic()` comparisons

**Decision**: Store cached model listings in Valkey keys with `SETEX <key> <ttl> <json>`. Read with `GET`. A missing key (expired or never set) means cache miss.

**Why**: Valkey handles TTL atomically; no clock-drift issues between replicas. Simpler code — no `CachedModelListing` dataclass or timestamp comparisons needed.

**Alternatives considered**:
- Keep `monotonic()` + push to Valkey: more complex, still has per-replica drift; rejected.
- Use a Valkey hash with a separate TTL field: more complex without benefit; rejected.

### D2: Reuse `_RespConnection` from `live_events.py`

**Decision**: Extract `_RespConnection` into a shared module (e.g., `storage/valkey.py`) and reuse it in both `ValkeyLiveEventBus` and `BifrostClient`.

**Why**: Avoids duplicating the low-level RESP client or introducing a new dependency like `redis-py` / `valkey-py`. The existing `_RespConnection` already handles `GET`, `SET`, `EXPIRE`, and `XADD`.

**Alternatives considered**:
- Add `redis-py` or `valkey-py` as a dependency: would work but adds a new dep for something already implemented; rejected given `_RespConnection` covers the needed commands.
- Give `BifrostClient` a reference to `ValkeyLiveEventBus`: wrong abstraction, event bus shouldn't be the cache backend; rejected.

### D3: Cache key schema

**Decision**:
- Per-provider: `agent-orchestrator:model-cache:provider:<provider_id>`
- All-models: `agent-orchestrator:model-cache:all`

**Why**: Namespaced under `agent-orchestrator:` to avoid collisions with other services sharing the same Valkey instance. Separate keys per provider match the existing lookup pattern.

### D4: `BifrostClient` receives a Valkey client, not the URL

**Decision**: `BifrostClient.__init__` takes an optional `valkey: _RespConnection | None` parameter. When `None`, caching is disabled (TTL 0 behaviour is preserved). `app.py` passes the shared connection.

**Why**: Keeps `BifrostClient` testable without a real Valkey instance — unit tests pass `None` to skip caching, integration tests pass a real connection. No change to the public API.

## Risks / Trade-offs

- **Valkey unavailability**: If Valkey is down, cache reads fail and every model-listing request hits Bifrost directly. This is acceptable — same as TTL=0 today, and Bifrost is the source of truth.
  → Mitigation: wrap GET/SETEX in try/except; log warning and fall through to a live fetch on error.

- **Serialisation size**: Model listings are small JSON arrays (dozens of entries). No size concern.

- **`_RespConnection` extraction**: `_RespConnection` is currently private in `live_events.py`. Extracting it into a shared module is a small refactor but must be done cleanly to avoid breaking `ValkeyLiveEventBus`.
  → Mitigation: move the class, update the import in `live_events.py`, add a unit test for the shared module.

## Migration Plan

1. Extract `_RespConnection` to `storage/valkey.py`; update `live_events.py` import — no behaviour change.
2. Add `valkey: _RespConnection | None` parameter to `BifrostClient`; replace in-memory cache logic with Valkey GET/SETEX; keep fallback to live fetch on error.
3. Update `app.py` to construct and pass a `_RespConnection` to `BifrostClient`.
4. Update `AGENTS.md` (root + agent-orchestrator).
5. Update/add unit tests for the new cache paths.

No migration of existing cache data is needed — in-memory caches are ephemeral by nature. On deploy, the first request per provider/scope fetches live and populates Valkey.

**Rollback**: Revert is safe at any point before step 3. After step 3, reverting means passing `None` to `BifrostClient`, which restores TTL=0 (no caching) behavior — functionally equivalent to the status quo minus caching.

## Open Questions

- None. All required information is available from the existing codebase.
