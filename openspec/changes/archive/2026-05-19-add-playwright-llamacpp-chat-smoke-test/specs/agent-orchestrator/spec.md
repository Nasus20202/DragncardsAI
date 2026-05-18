## ADDED Requirements

### Requirement: Smoke-model provider configuration
The agent-orchestrator SHALL support a local smoke-test model configuration that can target a repo-local `llama.cpp` server through the same session model configuration flow used for other providers.

The smoke-model configuration SHALL be expressible through non-secret environment-backed provider metadata and session model configuration fields rather than hard-coded test logic in the worker.

#### Scenario: Configure a session for the local smoke model
- **WHEN** a client configures an agent session for the documented smoke-test provider and model
- **THEN** the agent-orchestrator SHALL persist that model configuration and use it for prompt execution without requiring hosted-provider credentials

#### Scenario: Smoke-model configuration survives normal session retrieval
- **WHEN** a client retrieves a session configured for the local smoke model
- **THEN** the returned session detail SHALL include the persisted provider, model, and non-secret options needed to understand the smoke configuration

#### Scenario: Smoke session can use default game-service MCP
- **WHEN** a session is configured for the local smoke model
- **THEN** the session SHALL still expose the default `game-service` MCP tools needed for prompt-driven game creation
