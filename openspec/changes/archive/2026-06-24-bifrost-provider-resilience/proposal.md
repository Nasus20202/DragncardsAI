## Why

The `/providers` endpoint lists models for every enabled provider concurrently, but each Bifrost `list_models` call inherits the shared 60s httpx client timeout. When a provider configured in Bifrost lacks an API key (or is otherwise broken), its model-listing request hangs for the full 60s. Because `asyncio.gather` waits for every coroutine, a single keyless provider stalls the whole `/providers` response, the WebUI takes ~60s to load, and model selection breaks.

## What Changes

- **Add** a short, configurable per-provider model-listing timeout (`BIFROST_LIST_MODELS_TIMEOUT_SECONDS`, default `8`) applied specifically to the `list_models` HTTP request, so a keyless/broken provider fails fast instead of hanging for the shared 60s gateway timeout.
- **Keep** the general 60s `httpx.AsyncClient` timeout for actual chat completions; the model-listing timeout is passed per-request and does not regress completion behaviour.
- **Guard** each per-provider response build in the `/providers` handler with an `asyncio.wait_for` ceiling (list-models timeout plus a small margin) so one slow or hanging provider can never block the aggregate response, regardless of the client implementation. A failing provider returns promptly with `available=false` and a clear error.
- **Cache** the unavailable result of a failed/timed-out provider listing in Valkey under a distinct `:unavailable:{id}` marker with a configurable TTL (`BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS`, default `600`, must be positive), so repeat `/providers` calls fast-fail instead of re-incurring the list-models timeout. The marker expires and is cleared on a successful listing, so it can never permanently hide a provider.
- **Reset** the cache via `POST /providers/refresh` (and an optional `GET /providers?refresh=true` single-call bypass), which clears positive and negative entries plus the shared `:all` listing so an operator can force an immediate re-probe after adding an API key.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `agent-orchestrator`: the provider/model listing endpoint gains bounded latency, graceful per-provider failure guarantees, negative caching of unavailable providers, and an operator-facing cache reset.

## Impact

- **Affected code**:
  - `services/agent-orchestrator/src/agent_orchestrator/integrations/bifrost.py` (per-request list-models timeout, negative caching, cache reset)
  - `services/agent-orchestrator/src/agent_orchestrator/api/routers/catalog.py` (per-provider guard, `POST /providers/refresh`, `?refresh=true` bypass)
  - `services/agent-orchestrator/src/agent_orchestrator/config.py` (`BIFROST_LIST_MODELS_TIMEOUT_SECONDS`, `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS`)
  - `services/agent-orchestrator/src/agent_orchestrator/schemas/catalog.py` (refresh response)
  - `services/agent-orchestrator/src/agent_orchestrator/runtime/app.py` (wiring)
- **Configuration**: new `BIFROST_LIST_MODELS_TIMEOUT_SECONDS` and `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` settings documented in `.env.example` and the service `AGENTS.md`.
- **Tests**: unit tests assert the endpoint still returns working providers when one fails/hangs, marks the broken provider `available=false`, returns promptly rather than waiting the long timeout, negatively caches an unavailable provider so it is not re-probed within the TTL, and that the reset endpoint clears the cache so a recovered provider is re-probed.
- **Backwards compatibility**: defaults preserve existing behaviour for healthy providers; only broken/slow providers fail faster and are briefly cached as unavailable.
