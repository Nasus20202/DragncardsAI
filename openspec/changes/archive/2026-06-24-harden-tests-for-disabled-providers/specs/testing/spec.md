## ADDED Requirements

### Requirement: Provider tests are robust to the configured enabled providers
The agent-orchestrator test suite SHALL validate provider listing, session model-config assignment, and provider rejection without assuming any specific provider is enabled. Tests SHALL derive their expectations from the application's configured set of enabled providers rather than from hardcoded provider identifiers.

#### Scenario: Provider listing matches configured providers
- **WHEN** the provider-listing endpoint is exercised in tests
- **THEN** the asserted set of provider identifiers SHALL be derived from the application's configured enabled providers and SHALL match regardless of which providers are enabled

#### Scenario: Session model-config uses an enabled provider
- **WHEN** a test assigns a model configuration to a session
- **THEN** the test SHALL select a provider from the application's configured enabled providers and the assignment SHALL succeed

#### Scenario: Disabled provider is rejected
- **WHEN** a test assigns a model configuration using a provider that is supported but not currently enabled
- **THEN** the request SHALL be rejected with a client error, and if every supported provider is enabled the test SHALL skip rather than fail

#### Scenario: Suite honors environment-configured providers
- **WHEN** the unit test suite is run with `ENABLED_PROVIDER_IDS` set to disable one or more providers
- **THEN** the affected provider tests SHALL pass against the reduced provider set
