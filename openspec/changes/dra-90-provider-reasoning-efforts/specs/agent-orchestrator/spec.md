## MODIFIED Requirements

### Requirement: Model and provider configuration

The system SHALL allow each agent session to configure the model provider, model name, gateway options, and provider-specific non-secret settings used for prompt execution.

Provider model listings SHALL be cached in Valkey (not in process memory) so that all replicas share a consistent cache. The cache TTL SHALL be controlled by `PROVIDER_MODELS_CACHE_TTL_SECONDS`. When Valkey is unavailable, the system SHALL fall through to a live Bifrost fetch and SHALL NOT raise an error to the caller.

`BifrostClient` SHALL NOT hold any mutable in-process state after construction. In particular, `self._models_cache` and `self._all_models_cache` SHALL NOT exist.

The provider catalog SHALL preserve optional per-model reasoning metadata from Bifrost's rich `/v1/models` response. A model whose reasoning metadata is absent SHALL remain distinguishable from a model whose reasoning object has an explicitly empty `supported_efforts` list. The catalog SHALL retain existing model identifiers and SHALL expose the metadata additively so clients that only read the model identifier list remain compatible.

When a configured reasoning effort is submitted for a model whose advertised `supported_efforts` is non-empty, the service SHALL accept only one of those advertised values. When the model's reasoning metadata is absent or does not advertise `supported_efforts`, the service SHALL accept the legacy `low`, `medium`, and `high` values. When the model advertises an explicitly empty `supported_efforts` list, the service SHALL reject a configured effort and SHALL allow a reasoning request only when no effort is sent.

#### Scenario: Configure supported provider
- **WHEN** a client configures a session with one of OpenRouter, Mistral, Claude, OpenAI, LM Studio, or Gemini
- **THEN** the system SHALL persist the provider configuration and validate that the provider is known to the Bifrost gateway configuration

#### Scenario: Reject unsupported provider
- **WHEN** a client configures a session with an unknown provider identifier
- **THEN** the system SHALL reject the request with a validation error and SHALL NOT change the session model configuration

#### Scenario: Model listing served from shared Valkey cache
- **WHEN** two replicas of the agent-orchestrator both call `list_models` for the same provider within the TTL window
- **THEN** the second call SHALL receive the cached value from Valkey and SHALL NOT issue a new HTTP request to Bifrost

#### Scenario: Catalog preserves advertised reasoning efforts
- **WHEN** Bifrost's rich `/v1/models` response includes a model with `reasoning.supported_efforts` equal to `['minimal', 'high']`
- **THEN** the provider catalog SHALL return that model identifier and its exact advertised efforts to clients

#### Scenario: Catalog preserves explicit lack of efforts
- **WHEN** Bifrost's rich `/v1/models` response includes a model with `reasoning.supported_efforts` equal to `[]`
- **THEN** the provider catalog SHALL return that model identifier with an explicit empty effort list rather than replacing it with the legacy values

#### Scenario: Missing reasoning metadata keeps legacy validation
- **WHEN** a client configures a model whose Bifrost reasoning metadata is absent and submits reasoning effort `medium`
- **THEN** the service SHALL accept the configuration

#### Scenario: Advertised efforts constrain configuration
- **WHEN** a client configures a model advertising `['minimal', 'high']` and submits reasoning effort `medium`
- **THEN** the service SHALL reject the configuration and SHALL identify the model's supported efforts

#### Scenario: Explicitly unsupported reasoning omits effort
- **WHEN** a client configures a model advertising an explicit empty `supported_efforts` list and submits reasoning without an effort
- **THEN** the service SHALL accept the configuration without a `reasoning_effort` value in the request sent to Bifrost

### Requirement: Valkey-backed model listing cache

The model cache SHALL store provider model listings in Valkey using native key TTL so that all replicas share a single consistent cache.

Each cached entry SHALL be stored as a JSON-serialised list of model objects under a namespaced key and SHALL expire automatically after `PROVIDER_MODELS_CACHE_TTL_SECONDS` seconds.

The cache SHALL use the following key schema:
- Per-provider listing: `agent-orchestrator:model-cache:provider:<provider_id>`
- All-models listing: `agent-orchestrator:model-cache:all`

Cached model objects SHALL retain the optional reasoning metadata and the distinction between an omitted `supported_efforts` field and an explicitly empty list.

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

#### Scenario: Cached reasoning metadata survives a round trip
- **WHEN** a provider model listing containing advertised reasoning efforts is written to Valkey and read by another client
- **THEN** the returned model SHALL contain the same effort values

#### Scenario: Cached explicit empty efforts remain unsupported
- **WHEN** a provider model listing containing `supported_efforts: []` is written to Valkey and read by another client
- **THEN** the returned model SHALL retain an empty list rather than a legacy fallback
