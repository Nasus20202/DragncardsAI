## Why

The repo has API-level integration coverage for game lifecycle flows, but it does not prove that the real dashboard chat can drive the agent end-to-end through a local model and actually create a DragnCards game. Adding a deterministic local smoke path now will catch breakage across the dashboard, agent-orchestrator, game-service, and DragnCards boundary without depending on a remote model provider.

## What Changes

- Add a browser-driven smoke test implemented in `services/smoketest` that opens the dashboard Play workspace with Playwright, submits a prompt asking the agent to create a Marvel Champions game, and verifies that the game appears in DragnCards with bounded retries.
- Add local test-model support based on a small `llama.cpp` server so the smoke flow can run against a fast, low-cost, repo-local model endpoint instead of a hosted provider.
- Add explicit smoke-test environment and service wiring for the dashboard, agent-orchestrator, and supporting local model process so the workflow can be started consistently in local development and CI-like environments.
- Add deterministic test-facing requirements for the Play workspace and orchestration flow so the browser test can create a session, submit a prompt, and observe completion without relying on brittle implementation details.

## Non-goals

- Do not replace the main provider stack used for normal development or broader agent evaluation.
- Do not add a comprehensive Playwright suite for every dashboard interaction in this change.
- Do not require changes to the upstream DragnCards backend or frontend code.
- Do not guarantee that the small local model can handle arbitrary gameplay; it only needs to support the smoke path reliably.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `agent-orchestrator`: Extend provider and session behavior so a repo-local smoke-test model endpoint can be configured and used for deterministic prompt execution.
- `dashboard`: Extend the Play workspace contract with stable, automation-friendly behavior for session creation, prompt submission, and visible job completion in the browser.
- `infrastructure`: Extend local stack wiring with a documented `llama.cpp`-backed smoke-test model runtime and environment needed to run the browser smoke test.
- `testing`: Extend test-layer requirements with the browser-driven smoke flow that verifies chat-triggered game creation against live DragnCards state.

## Impact

- Adds a new OpenSpec capability for browser-driven chat smoke testing and updates existing testing, dashboard, infrastructure, and agent-orchestrator contracts.
- Will affect the dedicated smoke-test service, dashboard automation contract, agent-orchestrator provider configuration, local run scripts and/or compose wiring, and the end-to-end test harness.
- Introduces Playwright-based browser automation and a local `llama.cpp` runtime as first-class smoke-test dependencies.
