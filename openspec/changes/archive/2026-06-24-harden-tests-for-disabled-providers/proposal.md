## Why

Several agent-orchestrator tests assume that specific providers (`openai`, `gemini`) are always enabled. The set of enabled providers is environment-driven via `ENABLED_PROVIDER_IDS`, so when a deployment disables one of those providers (for example to remove OpenAI), the affected tests fail with hardcoded-expectation mismatches even though the service behaves correctly. The test suite must validate provider listing, session model-config assignment, and provider rejection regardless of which providers an environment enables.

## What Changes

- Make agent-orchestrator provider-related tests derive their expectations from the app's configured `enabled_provider_ids` (exposed via `app.state.settings`) instead of hardcoding `openai`/`gemini`.
- Have tests that need *a* valid provider pick one from the configured enabled set; have the rejection test pick a provider that is supported but **not** enabled.
- Allow the shared unit `app` fixture to honor `ENABLED_PROVIDER_IDS` from the environment so the suite exercises whichever providers a deployment enables.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities

- **testing**: Add a requirement that agent-orchestrator provider tests are robust to the configured set of enabled providers.

## Impact

- **Affected tests**:
  - `services/agent-orchestrator/tests/unit/test_app_meta_and_catalog.py`
  - `services/agent-orchestrator/tests/unit/test_app_sessions.py`
  - `services/agent-orchestrator/tests/integration/test_api_catalog_meta.py`
  - `services/agent-orchestrator/tests/unit/conftest.py`
- **Production code**: None. Only test expectations and a test fixture change.
- **Documentation**: None.
