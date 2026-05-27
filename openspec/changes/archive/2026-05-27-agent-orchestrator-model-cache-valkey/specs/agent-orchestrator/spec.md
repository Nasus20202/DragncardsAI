## ADDED Requirements

### Requirement: Valkey-backed model listing cache
The model cache SHALL store provider model listings in Valkey using native key TTL so that all replicas share a single consistent cache.

Each cached entry SHALL be stored as a JSON-serialised list of model objects under a namespaced key and SHALL expire automatically after `PROVIDER_MODELS_CACHE_TTL_SECONDS` seconds.

The cache SHALL use the following key schema:
- Per-provider listing: `agent-orchestrator:model-cache:provider:<provider_id>`
- All-models listing: `agent-orchestrator:model-cache:all`

#### Scenario: Cache hit for provider listing
- **WHEN** `list_models` is called for a `provider_id` whose Valkey key has not yet expired
- **THEN** the system SHALL return the cached model list without issuing any HTTP request to Bifrost

#### Scenario: Cache miss triggers live fetch
- **WHEN** `list_models` is called for a `provider_id` whose Valkey key is absent or expired
- **THEN** the system SHALL fetch the listing from Bifrost, store the result in Valkey with `SETEX`, and return the result

#### Scenario: Cache hit for all-models listing
- **WHEN** `_fetch_all_models` is called and the `agent-orchestrator:model-cache:all` key has not expired
- **THEN** the system SHALL return the cached model list without issuing any HTTP request

#### Scenario: Valkey unavailability falls through to live fetch
- **WHEN** Valkey is unavailable and `list_models` or `_fetch_all_models` is called
- **THEN** the system SHALL log a warning and fall through to fetch the listing live from Bifrost, returning the result without caching

#### Scenario: Caching disabled via zero TTL
- **WHEN** `PROVIDER_MODELS_CACHE_TTL_SECONDS` is set to `0`
- **THEN** the system SHALL skip all Valkey read and write operations and always fetch live from Bifrost

### Requirement: Shared Valkey connection module
The low-level Valkey RESP connection SHALL be extracted into a shared module (`storage/valkey.py`) so that it can be reused across `ValkeyLiveEventBus` and `BifrostClient` without duplication.

#### Scenario: Live event bus uses shared connection
- **WHEN** `ValkeyLiveEventBus` is constructed
- **THEN** it SHALL obtain a `_RespConnection` from the shared module and operate identically to before the extraction

#### Scenario: BifrostClient uses shared connection
- **WHEN** `BifrostClient` is constructed with a non-None Valkey connection
- **THEN** it SHALL use the shared `_RespConnection` to read and write cache keys

## MODIFIED Requirements

### Requirement: Model and provider configuration
The system SHALL allow each agent session to configure the model provider, model name, gateway options, and provider-specific non-secret settings used for prompt execution.

Provider model listings SHALL be cached in Valkey (not in process memory) so that all replicas share a consistent cache. The cache TTL SHALL be controlled by `PROVIDER_MODELS_CACHE_TTL_SECONDS`. When Valkey is unavailable, the system SHALL fall through to a live Bifrost fetch and SHALL NOT raise an error to the caller.

`BifrostClient` SHALL NOT hold any mutable in-process state after construction. In particular, `self._models_cache` and `self._all_models_cache` SHALL NOT exist.

#### Scenario: Configure supported provider
- **WHEN** a client configures a session with one of OpenRouter, Mistral, Claude, OpenAI, LM Studio, or Gemini
- **THEN** the system SHALL persist the provider configuration and validate that the provider is known to the Bifrost gateway configuration

#### Scenario: Reject unsupported provider
- **WHEN** a client configures a session with an unknown provider identifier
- **THEN** the system SHALL reject the request with a validation error and SHALL NOT change the session model configuration

#### Scenario: Model listing served from shared Valkey cache
- **WHEN** two replicas of the agent-orchestrator both call `list_models` for the same provider within the TTL window
- **THEN** the second call SHALL receive the cached value from Valkey and SHALL NOT issue a new HTTP request to Bifrost
