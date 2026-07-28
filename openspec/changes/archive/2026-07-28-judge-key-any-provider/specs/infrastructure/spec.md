## MODIFIED Requirements

### Requirement: Dedicated Bifrost judge identity

The infrastructure Bifrost gateway configuration SHALL define a dedicated judge key entry for evaluation traffic under EVERY configured provider, separate from that provider's game-playing key, each sourced from its own non-committed runtime secret, so the judge has its own attributable credential and budget whichever provider it runs on.

Each judge entry SHALL be named identically across providers (`eval-judge`) and SHALL carry `"weight": 0.0`, which keeps it out of Bifrost's weighted key selection so game-playing traffic can never draw it. Because a `0.0`-weighted key is never auto-selected, the eval-service SHALL address it explicitly by name via the `x-bf-api-key` header, which resolves against the target provider's keys and overrides the weight. The `Authorization` bearer SHALL NOT be relied on to select a provider key: with `enforce_auth_on_inference` disabled, `allow_direct_keys` disabled, and no governance virtual keys defined, that header selects nothing.

Adding a judge identity for a further provider SHALL require only a config entry plus a new environment variable — no code change.

#### Scenario: Dedicated judge key present for every provider

- **WHEN** the Bifrost gateway configuration is inspected
- **THEN** every provider SHALL carry a judge key entry distinct from its game-playing key, at `"weight": 0.0`, sourced from a per-provider environment reference
- **AND** the eval-service SHALL route judge traffic under it by explicit name

#### Scenario: Judge traffic never falls back to a game-playing key

- **WHEN** the eval-service sends a judge request to a provider that has no judge key configured, or whose judge key secret is unset
- **THEN** the gateway SHALL reject the request with an explicit error naming the missing key and provider
- **AND** the request SHALL NOT be served using that provider's game-playing key

#### Scenario: Judging with a non-default provider

- **WHEN** an operator configures the judge model to route through a different provider, such as `openrouter`, and sets that provider's judge secret
- **THEN** judge traffic SHALL use that provider's own judge key rather than its game-playing key, with no code change

#### Scenario: Judge key secret remains external

- **WHEN** repository files are inspected
- **THEN** the judge identity's API key or access token SHALL NOT be committed in compose files, default env files, tests, or source code
- **AND** the per-provider judge variables SHALL be documented, with empty values, alongside the game-playing provider variables
