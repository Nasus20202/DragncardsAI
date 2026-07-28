# Tasks

## 1. Reproduce

- [x] 1.1 Establish the real default provider set: no `.env` exists in the repo,
      so `Settings` defaults to all seven `REQUIRED_PROVIDER_IDS`, while
      `docker-compose.yaml` and `services/agent-orchestrator/.env.example`
      supply their own lists.
- [x] 1.2 Confirm `uv run` does not read `.env` implicitly, so the leak path is
      `scripts/test.sh integration|all` (which passes `--env-file`) plus any
      shell that exports the variables.
- [x] 1.3 With `services/agent-orchestrator/.env` copied from `.env.example` and
      OpenAI removed, record 9 integration failures, all
      `missing_model_config` / 400 from a hardcoded `provider_id: "openai"`.
- [x] 1.4 With a single provider (`ENABLED_PROVIDER_IDS=openrouter`) plus the
      service configuration exported, record 2 agent-orchestrator unit failures
      on bare `Settings()` default assertions.
- [x] 1.5 With `EVAL_JUDGE_MODEL` / `EVAL_JUDGE_PROVIDER` set, record 2
      eval-service failures (`test_defaults_are_secret_free`,
      `test_defaults_used_when_judge_omitted`).
- [x] 1.6 With the dashboard's service URLs exported, record 6 dashboard failures
      in the proxy and merged-OpenAPI suites.
- [x] 1.7 Confirm Vitest does not load `.env` into `process.env`, so the
      dashboard is only reachable through an exporting shell.

## 2. Hermetic Python harnesses

- [x] 2.1 Add `tests/settings_env.py` to agent-orchestrator, eval-service and
      history-service: derive the readable env var names from the `Settings`
      model and scrub them for one test, minus a `keep` allowlist.
- [x] 2.2 Apply it as an autouse fixture — agent-orchestrator per suite (unit
      scrubs everything, integration keeps `DATABASE_URL`), eval-service and
      history-service at the suite root (keeping their PostgreSQL/Valkey URLs).
- [x] 2.3 Pin `eval_judge_provider=""` in the eval-service judge-config test
      base so the "provider derived from the model id" path is exercised
      deliberately rather than by accident.

## 3. Provider-agnostic agent-orchestrator tests

- [x] 3.1 Stop the unit `app` fixture inheriting `ENABLED_PROVIDER_IDS`; pin
      `UNIT_ENABLED_PROVIDER_IDS` and use it from every unit harness that builds
      `Settings`.
- [x] 3.2 Add `test_unit_app_pins_provider_set_regardless_of_environment` as the
      regression guard.
- [x] 3.3 Replace the `pytest.skip` in `test_rejects_disabled_provider` with an
      assertion that the harness pins only a subset of the supported providers.
- [x] 3.4 Pin `INTEGRATION_ENABLED_PROVIDER_IDS` on both integration app
      builders and on the two suites that build their own app, and replace the
      hardcoded provider/model literals with `INTEGRATION_MODEL_CONFIG`.
- [x] 3.5 Assert in `test_api_catalog_meta.py` that `/providers` reports exactly
      the pinned set, so the harness's independence is itself covered.

## 4. Dashboard

- [x] 4.1 Add `vitest.setup.ts` clearing the variables
      `features/config/lib/dashboard-config.ts` reads, and register it as a
      `setupFiles` entry.
- [x] 4.2 Pin deliberately non-default base URLs in the proxy and merged-OpenAPI
      tests, and key the OpenAPI fake fetch off the pinned orchestrator URL
      instead of a `"4002"` substring.
- [x] 4.3 Add a drift guard asserting every `process.env.*` read by
      `dashboard-config.ts` is cleared by the setup file; verified it fails when
      an entry is removed.

## 5. Spec

- [x] 5.1 Replace the `testing` requirement "Provider tests are robust to the
      configured enabled providers" with "Test suites are independent of the
      environment's provider configuration".

## 6. Verify

- [x] 6.1 `./scripts/test.sh unit` at the repo default — all green.
- [x] 6.2 `./scripts/test.sh unit` with a single provider plus the service
      configuration exported — all green.
- [x] 6.3 `./scripts/test.sh unit` and `./scripts/test.sh all` with
      `services/{agent-orchestrator,eval-service}/.env` present and OpenAI
      absent — all green.
- [x] 6.4 `./scripts/test.sh integration` for agent-orchestrator, eval-service
      and history-service under the narrowed `.env`.
- [x] 6.5 `./scripts/lint.sh --fix` then `./scripts/lint.sh`.
- [x] 6.6 `openspec validate --all` (only the pre-existing
      `spec/typed-game-actions` failure remains).
