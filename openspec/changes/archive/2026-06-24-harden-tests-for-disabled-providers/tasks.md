## 1. Make provider listing tests provider-agnostic

- [x] 1.1 Update `test_list_providers` in `test_app_meta_and_catalog.py` to derive the expected provider id set from `app.state.settings.enabled_provider_ids`
- [x] 1.2 Update `test_catalog_endpoints_expose_available_providers_and_skills` in `test_api_catalog_meta.py` to assert against the configured enabled providers instead of `openai`

## 2. Make session model-config tests provider-agnostic

- [x] 2.1 Replace hardcoded `"openai"` provider ids in `test_app_sessions.py` with a provider chosen from `app.state.settings.enabled_provider_ids`
- [x] 2.2 Update `test_rejects_disabled_provider` to pick a supported-but-not-enabled provider (skip if none)

## 3. Honor environment-configured providers in the unit fixture

- [x] 3.1 Update unit `conftest.py` `app` fixture to honor `ENABLED_PROVIDER_IDS` from the environment

## 4. Add testing spec requirement

- [x] 4.1 Add an ADDED requirement to the testing capability covering provider-agnostic orchestrator tests

## 5. Verify

- [x] 5.1 Run the affected unit tests with the default provider set
- [x] 5.2 Run the affected unit tests with a provider disabled via `ENABLED_PROVIDER_IDS`
- [x] 5.3 Run lint
