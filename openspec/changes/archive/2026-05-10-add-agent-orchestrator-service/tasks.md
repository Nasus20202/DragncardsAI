## 1. Service Scaffold and Configuration

- [x] 1.1 Create `services/agent-orchestrator/` with FastAPI app structure, package metadata, Dockerfile, and local test configuration.
- [x] 1.2 Add orchestrator settings for dedicated PostgreSQL, Bifrost URL, provider identifiers, environment-configured skill roots, MCP server definitions, in-process worker polling, and non-secret runtime configuration.
- [x] 1.3 Add health and readiness endpoints that report API, database, worker, and Bifrost readiness without exposing secrets.
- [x] 1.4 Add unit tests for settings validation and health/readiness responses.

## 2. Persistence and Job Model

- [x] 2.1 Define database models and migrations for agent sessions, model configurations, skill assignments, MCP assignments, prompt runs, jobs, job attempts, events, outputs, and cancellation state in the dedicated orchestrator PostgreSQL database.
- [x] 2.2 Implement repository functions for creating sessions, updating configuration, storing assignments, enqueuing jobs, claiming jobs, appending events, completing jobs, failing jobs, and cancelling jobs.
- [x] 2.3 Add dedicated-PostgreSQL-backed tests for session persistence, job lifecycle transitions, event ordering, and cancellation state.

## 3. Agent Session API

- [x] 3.1 Implement endpoints to create, list, retrieve, update, and terminate agent sessions.
- [x] 3.2 Implement endpoints to configure session model/provider settings and reject unsupported providers.
- [x] 3.3 Implement endpoints to assign, list, and remove skills resolved from environment-configured roots using the shape `skills/<skill_name>`.
- [x] 3.4 Implement endpoints to assign, list, and remove MCP server/tool configurations including game-service MCP.
- [x] 3.5 Add API tests covering session lifecycle, provider validation, skill assignment validation, MCP assignment inspection, and terminated-session behavior.

## 4. Prompt Jobs and Worker Execution

- [x] 4.1 Implement prompt submission endpoint that creates a prompt run, enqueues a job, and returns immediately with job metadata.
- [x] 4.2 Implement job retrieval and cancellation endpoints for queued, running, completed, failed, and cancelled jobs.
- [x] 4.3 Implement an in-process dedicated-PostgreSQL-backed worker loop that claims queued jobs, records attempts, observes cancellation, and persists final job state.
- [x] 4.4 Implement orchestration execution that loads session skills, attaches assigned MCP clients, and records model/tool events for each prompt job.
- [x] 4.5 Add worker tests with fake model and fake MCP clients for successful completion, failure, retryable gateway errors, and cancellation before further model or MCP calls.

## 5. Bifrost Provider Gateway

- [x] 5.1 Add Bifrost client abstraction used by workers for all LLM calls.
- [x] 5.2 Add Bifrost `maximhq/bifrost:v1.5.0` provider configuration entries for GitHub Copilot, OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini using environment-provided credentials or local runtime config.
- [x] 5.3 Ensure provider errors are persisted as non-secret job failure details.
- [x] 5.4 Add tests verifying jobs call the Bifrost client instead of provider SDKs and validate all required provider identifiers are configured.

## 6. Streaming Events

- [x] 6.1 Implement a job event stream endpoint using persisted events and cursor-based resume semantics.
- [x] 6.2 Persist event types for prompt progress, model output chunks, tool calls, tool results, completion, failure, and cancellation.
- [x] 6.3 Add streaming tests for initial replay, live event delivery, and resume from a last-seen cursor.

## 7. Docker Compose and Infrastructure

- [x] 7.1 Add `agent-orchestrator` service to root `docker-compose.yaml` with dependencies on the dedicated orchestrator PostgreSQL and Bifrost services.
- [x] 7.2 Add Bifrost and dedicated orchestrator PostgreSQL service configuration to `docker-compose.infra.yaml` with environment placeholders and no committed provider secrets.
- [x] 7.3 Ensure `docker compose build agent-orchestrator` uses repo root context and `services/agent-orchestrator/docker/Dockerfile`.
- [x] 7.4 Copy configured `skills/<skill_name>` roots into the agent-orchestrator image and expose skill root paths through environment variables.
- [x] 7.5 Add compose/config tests or validation checks for agent-orchestrator, Bifrost, dedicated orchestrator PostgreSQL, required environment variables, copied skill roots, and secret-free defaults.

## 8. End-to-End Verification

- [x] 8.1 Add an integration test that creates an agent session, configures a fake provider, assigns a test skill, assigns game-service MCP metadata, submits a prompt, and observes a completed background job.
- [x] 8.2 Add an integration test that streams prompt/job events from persisted events and reconnects with a cursor.
- [ ] 8.3 Run the relevant orchestrator, game-service, and infrastructure test suites and document any required external services for skipped tests.
