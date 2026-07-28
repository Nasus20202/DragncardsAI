# Make the test suites independent of which providers are enabled

## Why

A user reported: "When some providers are disabled via the `.env` file (e.g.
OpenAI), some tests fail." Whether a contributor holds an OpenAI key must not
decide whether the suite is green.

Reproduced. `pydantic-settings` reads *every* `Settings` field from the process
environment, and several test harnesses built their `Settings` without pinning
the values their assertions depended on. `scripts/test.sh` runs integration (and
`all`) suites under `uv run --env-file services/<service>/.env`, so a developer's
`.env` lands directly in those runs; exporting the same variables in a shell
(direnv, `set -a; source .env`) reaches the unit suites too.

With `services/agent-orchestrator/.env` copied from `.env.example` and OpenAI
removed from `ENABLED_PROVIDER_IDS`, **9 agent-orchestrator integration tests
failed**: they hardcoded `{"provider_id": "openai", "model_name": "gpt-4o-mini"}`
while `build_integration_app` inherited the narrowed provider set, so every
`PUT /sessions/{id}/model-config` was correctly rejected with 400 and the tests
read that as a product failure. With a judge configured for a non-OpenAI
provider (`EVAL_JUDGE_MODEL` / `EVAL_JUDGE_PROVIDER`), **2 eval-service unit
tests failed** because they asserted on `Settings()` defaults. Exporting the
service configuration in a shell added **2 more agent-orchestrator unit
failures** (`Settings().valkey_url`, `Settings().bifrost_unavailable_cache_ttl_seconds`)
and **6 dashboard failures** (proxy and merged-OpenAPI tests that assumed the
default localhost service URLs).

The previous attempt at this (`2026-06-24-harden-tests-for-disabled-providers`)
went the other way: it taught the unit `app` fixture to *honour*
`ENABLED_PROVIDER_IDS` from the environment and derive expectations from it. That
made a handful of assertions provider-agnostic but left the suites' behaviour a
function of the developer's machine, and it never covered the integration suite
where the `.env` actually leaks in.

## What Changes

- **Test harnesses become hermetic.** Each Python service's test suite scrubs the
  environment variables its `Settings` model can read (derived from the model, so
  it cannot drift) and keeps only a documented allowlist that a suite genuinely
  needs — the PostgreSQL/Valkey URLs the integration fixtures connect with.
  Anything a test cares about is set explicitly: as a `Settings` keyword
  argument, or with `monkeypatch.setenv` inside the test.
- The agent-orchestrator unit `app` fixture no longer inherits
  `ENABLED_PROVIDER_IDS`; it pins `UNIT_ENABLED_PROVIDER_IDS`, a fixed subset of
  the supported providers backed by the fake Bifrost client. Env-driven parsing of
  `ENABLED_PROVIDER_IDS` stays covered directly in `tests/unit/test_config.py`,
  and a new test asserts the harness ignores an ambient value.
- The agent-orchestrator integration harness pins its provider set and exposes
  `INTEGRATION_MODEL_CONFIG`, replacing the vendor literals sprinkled across the
  suite. Provider ids there are configuration tokens against a fake gateway, so
  naming a vendor was never the point of those tests.
- `test_rejects_disabled_provider` no longer skips when every supported provider
  happens to be enabled. The harness now guarantees a supported-but-disabled
  provider exists, so the test asserts that precondition instead of quietly
  skipping.
- Dashboard tests clear the configuration variables `dashboard-config.ts` reads
  before each test, and the proxy/OpenAPI tests pin deliberately non-default base
  URLs — which proves the values come from configuration rather than accidentally
  matching a default. A drift guard fails if `dashboard-config.ts` starts reading
  a variable the isolation does not clear.

No production code changes. No test lost an assertion, and nothing was converted
to a skip.

## Capabilities

### New Capabilities

<!-- None -->

### Modified Capabilities

- **testing**: replace the requirement that the suite *honour* the environment's
  provider selection with one that the suites are independent of it, covering all
  services rather than only agent-orchestrator provider listing.

## Impact

- **Affected tests**:
  - `services/agent-orchestrator/tests/settings_env.py` (new),
    `tests/unit/conftest.py`, `tests/unit/app_test_support.py`,
    `tests/unit/context_api_test_support.py`, `tests/unit/test_auto_compaction.py`,
    `tests/unit/test_app_meta_and_catalog.py`, `tests/unit/test_app_sessions.py`,
    `tests/integration/conftest.py`, `tests/integration/api_test_support.py`,
    `tests/integration/test_api_{catalog_meta,context,jobs,live_mcp,sessions,skills,subagents}.py`
  - `services/eval-service/tests/settings_env.py` (new), `tests/conftest.py`,
    `tests/unit/test_judge_config.py`
  - `services/history-service/tests/settings_env.py` (new), `tests/conftest.py`
  - `services/dashboard/vitest.setup.ts` (new), `vitest.config.ts`,
    `features/proxy/__tests__/proxy.test.ts`,
    `features/swagger/__tests__/openapi.test.ts`,
    `features/config/__tests__/dashboard-config.test.ts`
- **Production code**: none.
- **Documentation**: none.

## Notes

- `tests/integration/test_api_jobs.py::test_cancel_job_records_cancellation_event`
  flakes under `pytest -n auto` (a cancel/observe race, `'running' == 'cancelled'`).
  Verified pre-existing on the unmodified branch and left alone; it is unrelated
  to provider configuration.
- game-service needed no change: it has no provider configuration and no test
  asserting on bare `Settings()` defaults.
