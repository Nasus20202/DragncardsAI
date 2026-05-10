## Why

DragnCardsAI needs a service that can run LLM agents as durable game-playing harnesses rather than one-off client calls. This enables repeatable agent sessions that can be configured with models, skills, MCP tools, and prompts while persisting orchestration state and work in background jobs.

## What Changes

- Add an agent-orchestrator service that manages agent sessions for LLMs playing DragnCards games through MCP tools, starting with the existing game-service MCP.
- Add APIs to create sessions, configure model/provider settings, assign skills from `@skills/`, attach MCP servers/tools, submit prompts, inspect job/session state, cancel work, and subscribe to streaming updates for future frontend use.
- Route model calls through Bifrost as the AI gateway and configure provider support for GitHub Copilot, OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini.
- Persist sessions, model configuration, skill/MCP assignments, prompt runs, jobs, events, and streamable outputs in a dedicated agent-orchestrator PostgreSQL instance that is not shared with other services.
- Execute all orchestration work as background jobs so HTTP endpoints enqueue or query work instead of running long LLM interactions inline.
- Define the service boundary without changing the upstream DragnCards backend or Marvel Champions plugin.

## Non-goals

- Do not implement a frontend in this change.
- Do not build game-specific decision quality, strategy tuning, or Marvel Champions play policies beyond providing the orchestration harness.
- Do not modify the upstream DragnCards backend or plugin submodules.
- Do not replace the existing game-service MCP; the orchestrator consumes it as a tool surface.
- Do not require real provider credentials in tests or repository files.

## Capabilities

### New Capabilities

- `agent-orchestrator`: API, persistence, job execution, streaming, provider gateway configuration, skill assignment, MCP assignment, and prompt orchestration for LLM agent sessions.

### Modified Capabilities

- `infrastructure`: Add service composition requirements for the agent-orchestrator, dedicated orchestration PostgreSQL and Bifrost services in `docker-compose.infra.yaml`, and non-shared orchestration storage/jobs.

## Impact

- New service code under a service directory such as `services/agent-orchestrator/`.
- New HTTP API surface for orchestration sessions, configuration, jobs, prompts, events, and streaming.
- New database schema/migrations for persistent orchestration data and job state.
- Docker Compose and environment configuration changes for the orchestrator, dedicated orchestrator PostgreSQL, and Bifrost gateway.
- Tests for API behavior, background job behavior, persistence, provider configuration, MCP assignment, skill assignment, and streaming event contracts.
