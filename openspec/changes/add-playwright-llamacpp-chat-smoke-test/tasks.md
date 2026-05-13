## 1. Smoke Runtime Wiring

- [x] 1.1 Add the documented local `llama.cpp` smoke-model startup path and required environment variables for the smoke workflow
- [x] 1.2 Wire the smoke-model environment into the local stack entrypoint used for end-to-end testing without making it mandatory for normal development
- [x] 1.3 Document how to obtain or point to the small smoke-test model artifact and how to verify the local model endpoint is healthy

## 2. Agent-Orchestrator Smoke Model Support

- [x] 2.1 Extend provider configuration so a session can target the local `llama.cpp` smoke-model endpoint through normal model configuration APIs
- [x] 2.2 Add unit or integration coverage for creating and reading back a session configured for the smoke model without hosted-provider credentials
- [x] 2.3 Ensure the smoke-model session wiring can still use the required game-service MCP assignment for prompt execution

## 3. Dashboard Smoke-Test Contract

- [x] 3.1 Add or stabilize the Play workspace selectors, labels, or visible status markers needed to create/select a session and submit a prompt from Playwright
- [x] 3.2 Add or stabilize a terminal job-state signal in the Play workspace so the browser test can detect when streaming has finished
- [x] 3.3 Add dashboard test coverage for any new automation-facing selectors or terminal-state rendering

## 4. Browser Smoke Test

- [x] 4.1 Add Playwright test setup in `services/smoketest` for the dashboard smoke path, including smoke-specific environment validation before the browser assertions run
- [x] 4.2 Implement the smoke test that opens the dashboard, configures or selects the smoke-model session, and asks chat to create a Marvel Champions game
- [x] 4.3 Implement bounded retry verification that confirms the game was created through the supported local stack rather than only through transcript text
- [x] 4.4 Make the smoke test report a clear dependency error when the local `llama.cpp` endpoint or required local services are unavailable

## 5. Verification

- [x] 5.1 Run the relevant dashboard and agent-orchestrator unit tests after the smoke-path changes
- [x] 5.2 Run the new Playwright smoke test against the local stack and fix any timing or reliability issues in the retry loop
- [x] 5.3 Update repo docs or scripts so the `services/smoketest` workflow is discoverable from the standard development entrypoints
