## 1. Extract shared Valkey connection

- [x] 1.1 Create `services/agent-orchestrator/src/agent_orchestrator/storage/valkey.py` by moving `_RespConnection` (and its helpers `_RespError`) out of `live_events.py` into the new module
- [x] 1.2 Update `live_events.py` to import `_RespConnection` from `storage.valkey` instead of defining it locally
- [x] 1.3 Verify existing unit tests for `ValkeyLiveEventBus` still pass after the extraction

## 2. Valkey-backed cache in BifrostClient

- [x] 2.1 Remove `self._models_cache: dict[str, CachedModelListing]` and `self._all_models_cache: CachedModelListing | None` from `BifrostClient.__init__`
- [x] 2.2 Remove the `CachedModelListing` dataclass (no longer needed)
- [x] 2.3 Add `valkey: _RespConnection | None = None` parameter to `BifrostClient.__init__`
- [x] 2.4 Implement `_cache_get(key: str) -> list | None` helper on `BifrostClient` — calls `GET` on Valkey, deserialises JSON, returns `None` on miss or error (logs warning on error)
- [x] 2.5 Implement `_cache_set(key: str, data: list, ttl: int)` helper — calls `SETEX`; silently swallows and logs on Valkey error
- [x] 2.6 Rewrite `list_models` to: read from Valkey key `agent-orchestrator:model-cache:provider:<provider_id>`, on miss fetch from Bifrost and write back with SETEX, skip cache entirely when `valkey` is None or TTL is 0
- [x] 2.7 Rewrite `_fetch_all_models` to: read from Valkey key `agent-orchestrator:model-cache:all`, on miss fetch from Bifrost and write back, skip cache when `valkey` is None or TTL is 0

## 3. Wire Valkey connection at startup

- [x] 3.1 In `runtime/app.py`, construct a `_RespConnection` from `settings.valkey_url` before creating `BifrostClient`
- [x] 3.2 Pass the `_RespConnection` instance as `valkey=` when constructing `BifrostClient`
- [x] 3.3 Ensure the connection is closed in the app lifespan teardown alongside `BifrostClient.aclose()` (no-op: `_RespConnection` is stateless — opens/closes TCP per command)

## 4. Tests

- [x] 4.1 Add unit tests for `_cache_get` and `_cache_set` helpers with a mock `_RespConnection` covering: hit, miss, Valkey error (should not raise)
- [x] 4.2 Add unit tests for `list_models` with Valkey: cache hit returns without calling Bifrost HTTP; cache miss calls Bifrost and writes to Valkey
- [x] 4.3 Add unit test for `list_models` with `valkey=None`: always calls Bifrost, never calls Valkey
- [x] 4.4 Add unit test for `list_models` with TTL=0: always calls Bifrost, never calls Valkey
- [x] 4.5 Add unit test: Valkey unavailable during `list_models` — falls through to live fetch, no exception raised

## 5. Documentation

- [x] 5.1 No change needed to root `AGENTS.md` — the "Services must NOT store any state in memory / Use Valkey for ephemeral data" rule already exists at line 46-48
- [x] 5.2 Update `services/agent-orchestrator/AGENTS.md` — reinforce the same rule with a concrete example (model cache → Valkey, not instance dict)
