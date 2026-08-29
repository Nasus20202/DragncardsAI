# DRA-87: Remove Smoketest Package and CI llama.cpp Smoke Runner

## Why
`services/smoketest` runs a browser-driven Playwright smoke test (`chat-smoke.spec.ts`) against a local `llama.cpp` container running Qwen 0.8B. In CI, running local LLM inference on 2-vCPU GitHub Actions runners takes minutes per model call, frequently times out, and triggers Playwright's retry loops (up to 10 retries in CI), ballooning CI runs to 25+ minutes and causing intermittent failures. Furthermore, mocked frontend tests such as `turn-continuation-smoke.spec.ts` in `services/smoketest` duplicate existing unit and component tests in `services/dashboard`. The core application logic and service interactions across all 6 services are already thoroughly tested by over 3,000 unit tests and live API integration tests.

## What Changes
- Delete `services/smoketest/` entirely.
- Remove `services/smoketest` steps, `llama.cpp` model cache, and smoke test execution from `.github/workflows/test.yaml`.
- Remove `llama-cpp-smoke` and `llama-cpp-smoke-model-cache` compose services from `docker-compose.yaml`.
- Remove smoke targets (`smoke-up`, `smoke-check`, `smoke-model`, `smoke-test`) from `Makefile`.
- Remove `services/smoketest` formatting and linting from `scripts/lint.sh`.
- Remove `services/smoketest` and smoke setup instructions from `README.md`.
- Remove `Browser smoke coverage for chat-driven game creation` from `openspec/specs/testing/spec.md`.
- Remove `Local smoke-model runtime wiring` and references to `services/smoketest` from `openspec/specs/infrastructure/spec.md`.

## Capabilities
### Modified Capabilities
- `testing`: Remove browser smoke test requirements.
- `infrastructure`: Remove local smoke model compose profile and smoketest pnpm project requirements.
