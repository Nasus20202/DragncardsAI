## Context

DragnCardsAI currently exposes game control through `game-service`, which provides HTTP and MCP interfaces backed by DragnCards Phoenix Channels sessions. LLM clients can call those tools directly, but there is no durable service for configuring agents, assigning skills and MCP tools, routing model calls through a gateway, preserving run history, or executing long-running prompt work outside request lifetimes.

The agent-orchestrator service will sit above `game-service` as an LLM harness. It will own agent session configuration, prompt runs, background jobs, provider routing, skill loading metadata, MCP server assignment, event persistence, and streaming read APIs. It will not replace the DragnCards integration or directly implement game actions that already belong to `game-service`.

## Goals / Non-Goals

**Goals:**

- Provide a durable HTTP API for creating and configuring agent sessions.
- Persist agent sessions, model settings, skills, MCP assignments, prompt runs, jobs, events, and outputs in PostgreSQL.
- Run all prompt and orchestration work in background jobs.
- Use Bifrost as the gateway for model/provider access.
- Configure provider entries for GitHub Copilot, OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini without committing provider secrets.
- Expose streaming-compatible event APIs for future frontend consumption.
- Integrate with game-service through MCP assignment rather than duplicating game control logic.

**Non-Goals:**

- No frontend implementation.
- No provider-specific credential provisioning beyond environment/configuration shape.
- No custom Marvel Champions strategy engine.
- No upstream DragnCards backend or plugin changes.
- No synchronous endpoint that blocks until an LLM game-playing run finishes.

## Decisions

1. Add a separate `services/agent-orchestrator/` FastAPI service.

   Rationale: The orchestrator has different persistence, job, provider, and streaming concerns than `game-service`. Keeping it separate preserves the existing game-service contract and avoids mixing DragnCards WebSocket lifecycle code with LLM run orchestration.

   Alternatives considered: Extend `game-service` with orchestrator endpoints. Rejected because it would couple game connection pooling to long-running LLM jobs and provider configuration. Add only scripts around MCP clients. Rejected because the requested API, persistence, and future streaming frontend require a service boundary.

2. Use a dedicated PostgreSQL service as both orchestration persistence and durable job state.

   Rationale: PostgreSQL satisfies the requirement for persistent data and jobs, but the orchestrator must not share a database with DragnCards or other services. A dedicated orchestrator Postgres instance keeps schemas, migrations, operational load, and failure domains isolated while still avoiding an additional queue dependency.

   Alternatives considered: Reuse `dragncards-postgres`. Rejected because the user requested that orchestration data not share a database with other services. In-memory queues. Rejected because jobs and events would be lost on restart. Redis/Celery. Rejected for now because it adds another service before queue throughput or retry complexity requires it.

3. Model all orchestration work as jobs with append-only events.

   Rationale: Prompt execution, MCP interaction, model streaming, cancellation, retries, and failure inspection all need durable state that can be queried independently from request lifetimes. Append-only events also provide a natural source for streaming endpoints. For the first development implementation, the worker will run in the same API process using the same codebase and PostgreSQL job state.

   Alternatives considered: Store only final prompt responses. Rejected because it would not support frontend streaming, progress inspection, or debugging agent/tool behavior. Stream directly from worker memory only. Rejected because clients can disconnect and reconnect.

4. Route all model calls through Bifrost provider identifiers.

   Rationale: Bifrost centralizes provider configuration and gives the orchestrator one gateway contract while still supporting GitHub Copilot, OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini. Local Docker Compose infrastructure will use `maximhq/bifrost:v1.5.0` from `docker-compose.infra.yaml`.

   Alternatives considered: Integrate each provider SDK directly. Rejected because it spreads provider-specific behavior and credential handling through orchestrator code. Use OpenAI-compatible endpoints only. Rejected because not all requested providers have identical capabilities or authentication models.

5. Represent skills and MCP servers as assigned resources on an agent session.

   Rationale: Sessions need explicit, inspectable configuration for which `@skills/` entries and MCP tool surfaces are available during prompt runs. Skills are discovered from one or more environment-configured skill roots using the shape `skills/<skill_name>`, and those roots are copied into the orchestrator Docker image. The initial implementation can validate configured skill identifiers and MCP server definitions before jobs execute.

   Alternatives considered: Infer skills and MCPs from raw prompt text. Rejected because it is not auditable or safe. Make assignments global only. Rejected because different agents need different harness capabilities.

6. Expose Server-Sent Events for streaming job/session events.

   Rationale: SSE is simple for frontend consumption, works over HTTP, and maps directly to persisted event records. It is sufficient for one-way progress/token/tool event streams.

   Alternatives considered: WebSockets. Rejected for the first iteration because bidirectional messaging is not yet required. Polling only. Rejected because the user explicitly requested streaming support for a future frontend.

## Risks / Trade-offs

- DragnCards or game-service MCP behavior changes upstream -> Mitigation: keep game interaction behind MCP assignment and rely on game-service tests/contracts rather than reimplementing Phoenix protocol details in the orchestrator.
- Provider capability differences through Bifrost -> Mitigation: persist provider/model metadata and return clear job failures when a requested provider lacks required capabilities.
- Long-running jobs can leave sessions in partial states -> Mitigation: persist job lifecycle states, cancellation requests, attempts, timestamps, errors, and append-only events.
- PostgreSQL-backed jobs are simpler but less scalable than a dedicated queue -> Mitigation: define the worker abstraction so a later queue backend can replace the polling implementation without changing the API contract.
- Streaming from persisted events can lag behind provider token emission -> Mitigation: write events incrementally during job execution and expose last-event cursors for reconnection.

## Migration Plan

1. Add the service skeleton, configuration, database models, and migrations.
2. Add API endpoints for session configuration, assignments, prompt submission, job inspection, cancellation, and event streaming.
3. Add worker execution for queued prompt jobs using Bifrost and assigned MCP resources.
4. Add Docker Compose wiring for `agent-orchestrator` in `docker-compose.yaml` and `bifrost` plus a dedicated orchestrator PostgreSQL service in `docker-compose.infra.yaml`, all using environment-based secrets.
5. Add tests with fake Bifrost and fake MCP clients for unit/integration coverage.

Rollback is removal of the new services, migrations, and compose entries before any production deployment depends on them. Existing `game-service` and DragnCards services remain unchanged.

## Open Questions

- Which concrete Bifrost provider configuration file format is required by `maximhq/bifrost:v1.5.0` for all requested providers?
