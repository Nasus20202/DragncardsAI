# Smoke Test Service

`smoketest` is the repo's dedicated browser smoke-test package.

It owns the Playwright harness that drives the dashboard Play workspace, submits a prompt through `agent-orchestrator`, and verifies that `game-service` created a real Marvel Champions game.

It is not part of the dashboard runtime.
The dashboard exposes the UI and automation contract; `smoketest` is the test runner that exercises it.

## Run

From the repo root:

```bash
services/smoketest/smoke.sh test
```

Using the smoke helper directly:

```bash
services/smoketest/smoke.sh test
```

Inside the service directory:

```bash
pnpm test
```

## What This Service Is For

Use `smoketest` when you need to:

- verify the dashboard Play flow end to end in a real browser
- prove that the local `llama.cpp` smoke model can drive orchestration
- catch breakage across dashboard, agent-orchestrator, game-service, and DragnCards state creation
- run the repo's supported Playwright smoke path without coupling it to the dashboard package

## Dependencies

The smoke test expects these local services to be reachable:

- dashboard at `DASHBOARD_SMOKE_BASE_URL` defaulting to `http://127.0.0.1:3001`
- agent-orchestrator at `AGENT_ORCHESTRATOR_SMOKE_URL` defaulting to `http://127.0.0.1:4002`
- game-service at `GAME_SERVICE_SMOKE_URL` defaulting to `http://127.0.0.1:4001`
- llama.cpp OpenAI-compatible endpoint at `LLAMA_CPP_SMOKE_URL` defaulting to `http://127.0.0.1:1234/v1`

The expected smoke model defaults are:

- `SMOKE_MODEL_PROVIDER_ID=lmstudio`
- `SMOKE_MODEL_NAME=qwen3.5-0.8b`

To start the compose-managed smoke stack from the repo root:

```bash
make smoke-up
```

To start only the smoke model:

```bash
make smoke-model
```

To validate that dependencies are reachable before running the browser test:

```bash
services/smoketest/smoke.sh check
```

## Package Layout

- `tests/chat-smoke.spec.ts` - the browser smoke scenario
- `src/config.ts` - smoke-specific environment defaults and prompt constants
- `src/types.ts` - API response shapes used by the harness
- `src/utils.ts` - shared request helpers and polling logic
- `playwright.config.ts` - Playwright configuration for the smoke runner

## Verification

Inside `services/smoketest`:

```bash
pnpm typecheck
pnpm exec playwright test --list
```
