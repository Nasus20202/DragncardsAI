## 1. Configurable list-models timeout

- [x] 1.1 Add `BIFROST_LIST_MODELS_TIMEOUT_SECONDS` setting (default `8`, must be positive) to `config.py`
- [x] 1.2 Thread a `list_models_timeout_seconds` parameter into `BifrostClient` and apply it as a per-request timeout on the model-listing GET calls, keeping the shared 60s client timeout for completions

## 2. Bounded, isolated provider listing

- [x] 2.1 Wrap each per-provider response build in `_build_provider_response` with an `asyncio.wait_for` guard bounded by the list-models timeout plus a small margin
- [x] 2.2 Return `available=false` with a clear error when a provider times out, and confirm `asyncio.gather` isolates per-provider failures
- [x] 2.3 Wire `BIFROST_LIST_MODELS_TIMEOUT_SECONDS` through `runtime/app.py`

## 3. Docs

- [x] 3.1 Document `BIFROST_LIST_MODELS_TIMEOUT_SECONDS` in `.env.example` and the service `AGENTS.md`

## 4. Tests and verification

- [x] 4.1 Add unit tests: one provider fails/hangs while others return models, the broken provider is `available=false`, and the call does not wait the long timeout
- [x] 4.2 Run unit tests and lint

## 5. Negative caching of unavailable providers

- [x] 5.1 Add `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` setting (default `600`, must be positive) to `config.py` and wire it through `runtime/app.py`
- [x] 5.2 In `BifrostClient.list_models`, store a distinct negative marker in Valkey (`agent-orchestrator:model-cache:unavailable:{id}`) on failure/timeout, fast-fail subsequent calls within the TTL without the slow HTTP call, and clear the marker on a successful listing
- [x] 5.3 Confirm `_build_provider_response` still reports `available=false` with a clear error for a negatively-cached provider, now returning fast

## 6. Provider model-cache reset

- [x] 6.1 Add `BifrostClient.clear_model_cache` to delete positive, negative, and `:all` cache entries for the enabled providers
- [x] 6.2 Add a `POST /providers/refresh` endpoint (registered with the other catalog routes) that flushes the cache and returns a simple result; accept `?refresh=true` on `GET /providers` for a single-call bypass

## 7. Docs and tests for caching/reset

- [x] 7.1 Document `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` and the reset route in `.env.example` and the service `AGENTS.md`
- [x] 7.2 Add unit tests: an unavailable provider is negatively cached so a second `/providers` does not re-probe; the reset endpoint clears the cache so a now-available provider appears; the negative TTL setting is validated
