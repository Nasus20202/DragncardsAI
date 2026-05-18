## Why

The repo has API-level integration coverage for game lifecycle flows, but it does not prove that the real dashboard chat can drive the agent end-to-end through a local model and actually create a DragnCards game. Adding a deterministic local smoke path catches breakage across the dashboard, agent-orchestrator, game-service, and DragnCards boundary without depending on a hosted provider.

## What Changes

- Add a browser-driven smoke test in `services/smoketest` that opens the dashboard Play workspace with Playwright, submits a prompt asking the agent to create a Marvel Champions game, and verifies that the game appears through supported service state with bounded retries.
- Add local smoke-model support based on a small `llama.cpp` server so the smoke flow can run against a fast repo-local endpoint instead of a hosted provider.
- Add explicit smoke-test wiring through `services/smoketest/smoke.sh`, repo `make` targets, and an optional Docker Compose `smoke` profile.
- Add deterministic automation-facing requirements for the Play workspace so the browser test can create a session, submit a prompt, and observe streaming and completion without relying on incidental DOM details.

## Non-goals

- Do not replace the main provider stack used for normal development or broader agent evaluation.
- Do not add a comprehensive Playwright suite for every dashboard interaction.
- Do not require changes to upstream DragnCards backend or frontend code.
- Do not guarantee that the small local model can handle arbitrary gameplay; it only needs to support the smoke path reliably.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `agent-orchestrator`: Extend provider and session behavior so a repo-local smoke-model endpoint can be configured and used through normal session model configuration.
- `dashboard`: Extend the Play workspace contract with stable automation behavior for session creation, prompt submission, streaming state, and visible terminal job state.
- `infrastructure`: Extend local stack wiring with an optional compose-managed `llama.cpp` smoke runtime and environment needed to run the browser smoke flow.
- `testing`: Extend test-layer requirements with the browser-driven smoke flow that verifies chat-triggered game creation against live service state.

## Impact

- Updates testing, dashboard, infrastructure, and agent-orchestrator contracts for browser-driven smoke coverage.
- Affects the dedicated smoke-test service, dashboard automation contract, agent-orchestrator provider configuration, and local scripts/compose wiring.
- Introduces Playwright automation, `services/smoketest/smoke.sh`, and an optional local `llama.cpp` runtime as first-class smoke-test dependencies.
