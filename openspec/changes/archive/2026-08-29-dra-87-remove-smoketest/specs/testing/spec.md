## REMOVED Requirements

### Requirement: Browser smoke coverage for chat-driven game creation
The test suite SHALL include a browser-driven smoke test implemented from the dedicated `services/smoketest` service that opens the dashboard Play workspace, submits a chat prompt asking the agent to create a Marvel Champions game, and verifies that the game is created in live DragnCards state.

The smoke test SHALL run against the documented local `llama.cpp` smoke-model configuration rather than requiring a hosted model provider.

#### Scenario: Chat prompt creates a game through the browser flow
- **WHEN** the smoke test opens the dashboard, submits the documented create-game prompt, and the job reaches a successful terminal state
- **THEN** the test SHALL verify that a corresponding game session or room was created and is observable through the supported local stack

#### Scenario: Verification tolerates asynchronous game creation
- **WHEN** the create-game request succeeds but DragnCards state is not visible immediately
- **THEN** the smoke test SHALL retry verification for a bounded interval before failing

#### Scenario: Smoke test fails clearly when local model runtime is unavailable
- **WHEN** the browser smoke test is run without a reachable `llama.cpp` smoke-model endpoint
- **THEN** the failure SHALL identify the missing local model dependency rather than reporting only a generic UI assertion failure
