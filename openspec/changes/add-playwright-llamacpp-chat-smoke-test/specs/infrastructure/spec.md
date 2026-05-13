## ADDED Requirements

### Requirement: Local smoke-model runtime wiring
The repository SHALL provide a documented local runtime path for a small `llama.cpp` model used by smoke tests, including the environment configuration needed for the dashboard and agent-orchestrator to target that model.

The smoke-model runtime SHALL remain optional for developers who are not running the smoke workflow.

#### Scenario: Smoke runtime can be started locally
- **WHEN** a developer follows the documented smoke-test setup for the local model runtime
- **THEN** the `llama.cpp` server SHALL be startable with the configured model artifact and reachable at the documented local endpoint

#### Scenario: Normal local stack does not require the smoke runtime
- **WHEN** a developer starts the normal local stack without the smoke-test workflow
- **THEN** the dashboard, game-service, and agent-orchestrator SHALL remain runnable without requiring the `llama.cpp` smoke-model process
