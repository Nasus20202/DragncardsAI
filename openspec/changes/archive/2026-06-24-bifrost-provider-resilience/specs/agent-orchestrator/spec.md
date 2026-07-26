## ADDED Requirements

### Requirement: Bounded provider-listing latency
The provider/model listing endpoint SHALL bound the time spent listing models for any single provider so that a provider missing an API key or otherwise unreachable cannot stall the aggregate response.

Each per-provider model-listing HTTP request SHALL use a short, configurable timeout controlled by `BIFROST_LIST_MODELS_TIMEOUT_SECONDS` (default 8 seconds, which MUST be positive), separate from the general client timeout used for chat completions. The general completion timeout SHALL remain unchanged so normal completion behaviour does not regress.

The `/providers` endpoint SHALL additionally enforce a hard per-provider ceiling, no longer than the configured list-models timeout plus a small fixed margin, so that the total endpoint latency is bounded by that ceiling even when every provider is broken.

#### Scenario: Keyless provider fails fast
- **WHEN** a client requests `/providers` and one enabled provider's model listing does not respond within `BIFROST_LIST_MODELS_TIMEOUT_SECONDS`
- **THEN** the system SHALL stop waiting for that provider within the configured timeout (plus the fixed guard margin) and SHALL NOT wait the full general completion timeout

#### Scenario: Endpoint bounded when all providers are broken
- **WHEN** a client requests `/providers` and every enabled provider's model listing hangs
- **THEN** the system SHALL return a response whose total latency is bounded by the configured list-models timeout plus the fixed guard margin

### Requirement: Graceful per-provider listing failure
The provider/model listing endpoint SHALL isolate failures so that one slow or failing provider never prevents the working providers from returning their models.

When listing models for a provider fails or times out, the system SHALL return that provider with `available=false`, an empty model list, and a clear, non-empty error message, while still returning successful results for all other enabled providers in the same response.

#### Scenario: One failing provider does not block others
- **WHEN** a client requests `/providers` and one enabled provider raises an error while others succeed
- **THEN** the system SHALL return the successful providers with `available=true` and their models, and the failing provider with `available=false`, an empty model list, and a descriptive error message

#### Scenario: Timed-out provider reported as unavailable
- **WHEN** a provider's model listing exceeds the configured per-provider timeout
- **THEN** the system SHALL return that provider with `available=false`, an empty model list, and an error indicating the listing timed out

### Requirement: Cached unavailable providers
The system SHALL cache the unavailable result of a provider model listing so that repeated `/providers` calls do not re-incur the per-provider list-models timeout for a provider that is missing an API key or otherwise unreachable.

When a provider's model listing fails or times out, the system SHALL record a negative/unavailable marker in Valkey for that provider, distinguishable from a positive cache entry, with a configurable time-to-live controlled by `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` (default 600 seconds, which MUST be positive). While a provider's negative marker is live, the system SHALL report that provider as `available=false` with a clear error message and SHALL NOT make the slow underlying model-listing HTTP call. A negative marker SHALL expire after its time-to-live so the negative cache can never permanently hide a provider, and a subsequent successful listing for a provider SHALL clear that provider's negative marker.

#### Scenario: Unavailable provider is not re-probed within the TTL
- **WHEN** a provider's model listing fails and a client requests `/providers` again before the negative-cache time-to-live elapses
- **THEN** the system SHALL report that provider as `available=false` with a clear error message without making another model-listing HTTP call to that provider

#### Scenario: Negative marker cleared on recovery
- **WHEN** a provider that was previously negatively cached returns a successful model listing
- **THEN** the system SHALL clear that provider's negative marker so it is reported as `available=true` with its models

### Requirement: Provider model-cache reset
The system SHALL provide an operator-facing capability to clear the cached provider model listings so that a provider which becomes available after configuration changes (such as adding an API key) is immediately re-probed rather than waiting for cache entries to expire.

The reset capability SHALL clear both positive and negative cache entries, including the per-provider listing, the per-provider unavailable marker, and the shared aggregate listing, for every enabled provider, and SHALL be exposed via an HTTP endpoint registered consistently with the other catalog routes. The provider listing endpoint MAY additionally accept a request parameter that bypasses the cache for a single call.

#### Scenario: Reset forces re-probe of a recovered provider
- **WHEN** an operator triggers the provider model-cache reset after a previously unavailable provider becomes available
- **THEN** the system SHALL clear the cached entries and the next `/providers` call SHALL re-probe the provider and report it as `available=true` with its models
