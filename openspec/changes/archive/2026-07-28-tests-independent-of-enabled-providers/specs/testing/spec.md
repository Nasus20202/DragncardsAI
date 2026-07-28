## REMOVED Requirements

### Requirement: Provider tests are robust to the configured enabled providers

**Reason**: Replaced by "Test suites are independent of the environment's provider configuration", which isolates the harnesses from ambient configuration instead of teaching them to mirror it. The removed requirement asked the unit suite to honour `ENABLED_PROVIDER_IDS` from the environment, which left test behaviour a function of the developer's machine and never covered the integration suite — where `scripts/test.sh` actually passes the service `.env` in.

**Migration**: The behaviours it protected are preserved: provider listing, session model-config assignment and disabled-provider rejection are still asserted, now against a provider set the harness pins.

## ADDED Requirements

### Requirement: Test suites are independent of the environment's provider configuration
Every test suite SHALL produce the same result regardless of which LLM providers the developer running it has enabled or holds API keys for. No test SHALL fail, and no test SHALL silently stop asserting, because a provider is disabled, keyless or absent.

Test harnesses SHALL NOT inherit service configuration from the ambient environment. Each suite SHALL neutralise the environment variables its settings model can read and SHALL set the values its assertions depend on explicitly, keeping only a documented allowlist of variables the suite genuinely needs to reach an external dependency such as PostgreSQL or Valkey.

A test that genuinely requires a live, keyed provider SHALL skip with a reason naming that requirement rather than passing vacuously or failing.

#### Scenario: Narrowed provider list keeps the suite green
- **WHEN** the unit and integration suites are run with the service's provider list narrowed to a single provider, or with a provider such as OpenAI removed, whether exported in the shell or supplied through the service `.env` that the test runner passes to the suite
- **THEN** every test SHALL pass or skip with a stated reason, and the result SHALL match the result at the repository default configuration

#### Scenario: Provider identity is not asserted as a vendor literal
- **WHEN** a test assigns a model configuration to a session, or asserts on the set of listed providers
- **THEN** it SHALL use the provider set its own harness pins, or the application's configured providers, rather than a hardcoded vendor identifier that a deployment may have disabled

#### Scenario: Harness independence is itself covered
- **WHEN** a provider list is present in the environment while the suite builds its application under test
- **THEN** the application SHALL be configured with the provider set the harness pins, and a test SHALL assert this so the independence cannot regress unnoticed

#### Scenario: Settings defaults are asserted against a clean environment
- **WHEN** a test asserts on a configuration default
- **THEN** the corresponding environment variable SHALL have been neutralised by the suite, so the assertion describes the declared default rather than the machine the suite runs on

#### Scenario: Disabled-provider rejection stays exercised
- **WHEN** the suite asserts that assigning a supported-but-disabled provider is rejected
- **THEN** the harness SHALL guarantee that at least one supported provider is disabled, and the test SHALL assert that precondition rather than skipping when it does not hold

#### Scenario: Frontend configuration defaults do not leak in
- **WHEN** the dashboard test suite runs in a shell that exports the stack's service URLs or session defaults such as the default provider and model
- **THEN** the suite SHALL clear those variables before each test, and a guard SHALL fail if the configuration module starts reading a variable the suite does not clear
