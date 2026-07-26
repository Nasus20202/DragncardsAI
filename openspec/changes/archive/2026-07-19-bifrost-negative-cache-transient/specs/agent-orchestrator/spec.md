## MODIFIED Requirements

### Requirement: Cached unavailable providers
The system SHALL cache the unavailable result of a provider model listing so that repeated `/providers` calls do not re-incur the per-provider list-models timeout for a provider that is missing an API key or otherwise unreachable.

When a provider's model listing fails or times out, the system SHALL record a negative/unavailable marker in Valkey for that provider, distinguishable from a positive cache entry. The marker's time-to-live SHALL depend on whether the failure is retryable: a definitive (non-retryable) failure — such as a missing API key — SHALL use the long time-to-live controlled by `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` (default 600 seconds, which MUST be positive), while a transient (retryable) failure — a timeout, network error, 5xx, or 429 — SHALL use a much shorter time-to-live controlled by `BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS` (default 30 seconds, which MUST be positive) so that a provider which recovers from a brief blip is re-probed quickly rather than suppressed for the full definitive time-to-live.

While a provider's negative marker is live, the system SHALL report that provider as `available=false` with a clear error message and SHALL NOT make the slow underlying model-listing HTTP call. A negative marker SHALL expire after its time-to-live so the negative cache can never permanently hide a provider, and a subsequent successful listing for a provider SHALL clear that provider's negative marker.

#### Scenario: Unavailable provider is not re-probed within the TTL
- **WHEN** a provider's model listing fails and a client requests `/providers` again before the negative-cache time-to-live elapses
- **THEN** the system SHALL report that provider as `available=false` with a clear error message without making another model-listing HTTP call to that provider

#### Scenario: Transient failure uses the short retryable TTL
- **WHEN** a provider's model listing fails with a retryable error (timeout, network error, 5xx, or 429)
- **THEN** the system SHALL record the negative marker with the short `BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS` time-to-live rather than the long `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` time-to-live, so a recovered provider is re-probed within the short window

#### Scenario: Definitive failure uses the long TTL
- **WHEN** a provider's model listing fails with a non-retryable error (for example a missing API key returning a 4xx auth error)
- **THEN** the system SHALL record the negative marker with the long `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` time-to-live so the slow model-listing HTTP call is not re-incurred on every subsequent request

#### Scenario: Negative marker cleared on recovery
- **WHEN** a provider that was previously negatively cached returns a successful model listing
- **THEN** the system SHALL clear that provider's negative marker so it is reported as `available=true` with its models
