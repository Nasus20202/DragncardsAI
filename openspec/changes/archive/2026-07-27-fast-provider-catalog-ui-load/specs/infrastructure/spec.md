## MODIFIED Requirements

### Requirement: Bifrost gateway configuration
The infrastructure compose configuration in `docker-compose.infra.yaml` SHALL define a Bifrost AI gateway service using image `maximhq/bifrost` and configured through non-committed runtime secrets and provider environment variables.

Bifrost's cross-provider model listing answers only once every configured provider has answered, so a provider that is configured but unreachable delays the listing for every caller. Any provider whose endpoint is local — reached over the Docker network rather than the public internet — SHALL use a fast-failing retry policy so that its absence cannot hold the model listing for seconds. Specifically, the `lmstudio` provider's `network_config` SHALL use `max_retries: 1` with `retry_backoff_initial: 200` and `retry_backoff_max: 1000`.

#### Scenario: Bifrost starts with supported providers
- **WHEN** `docker compose up` is run with the required provider environment available
- **THEN** the `bifrost` service SHALL start with provider entries for OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini

#### Scenario: Provider secrets remain external
- **WHEN** repository files are inspected
- **THEN** provider API keys and access tokens SHALL NOT be committed in compose files, default env files, tests, or source code

#### Scenario: LM Studio traffic routes through lmstudio-proxy
- **WHEN** Bifrost sends a request to the `lmstudio` provider
- **THEN** the request SHALL be forwarded to `lmstudio-proxy` inside the Docker network rather than using `host.docker.internal` directly

#### Scenario: Absent LM Studio does not stall the model listing
- **WHEN** LM Studio is not running on the host and a client requests Bifrost's model listing
- **THEN** the `lmstudio` provider SHALL exhaust its retries in well under a second so the listing is not delayed by retry backoff
