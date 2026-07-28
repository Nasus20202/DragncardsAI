# Agent Orchestrator Service Agent Guide

Read this file before making changes in `services/agent-orchestrator/`.

## Scope

These instructions apply to the agent-orchestrator service and override the repository-level `AGENTS.md`.

## Tech Stack

- **Language**: Python 3.x with `uv` package manager
- **Framework**: FastAPI for HTTP API
- **Database**: PostgreSQL for session/job persistence
- **Streaming**: Valkey (Redis) for transient SSE events
- **Workers**: Background job processing via Redis/BullMQ
- **MCP**: Model Context Protocol client for LLM tool integration
- **Testing**: pytest with async support

## Project Structure

```
agent-orchestrator/
  src/agent_orchestrator/   # Main source code
  tests/                    # Unit and integration tests
```

## Core Concepts

### Sessions

Sessions are persistent agent configurations:
- Provider/model assignment via `/sessions/{id}/model-config`
- Skill assignments via `/sessions/{id}/skills`
- MCP assignments via `/sessions/{id}/mcps`
- Each session tracks jobs and tool catalog

### Jobs

Jobs are prompt executions:
- Created via `POST /sessions/{id}/prompts`
- Stream events via `GET /jobs/{id}/events/stream`
- Events include: `progress`, `reasoning`, `model_output`, `tool_call`, `tool_result`, `skill_loaded`, `compaction`, `subagent_started`, `subagent_completed`, `subagent_failed`, `user_question`, `user_question_answered`, `user_question_closed`, `completion`, `failure`, `cancellation`
- Only `completion`, `failure`, and `cancellation` are terminal and close the SSE stream
- A new event type needs no migration (`job_events.event_type` is a free string), but it **must** be
  added to the dashboard's `STREAM_EVENT_TYPES`, because the browser registers one named `EventSource`
  listener per type and silently drops anything absent from that list

### Personas

Personas are deployment-global, user-authored agent configurations stored in `agent_personas`
(PostgreSQL), keyed by name:

- A persona bundles a detailed system prompt, a skill selection, and a tool allowlist.
- `spawn_subagent` takes an optional `persona`; a session's `default_subagent_persona` applies when
  none is named.
- **A persona is resolved and captured at spawn time**, materialised onto the child session's
  model-config row, skill rows, and metadata snapshot. Nothing at child run time re-reads the persona
  table, so editing or deleting a persona never changes a subagent already started from it.
- **A persona may narrow tool access and must never widen it.** The allowlist is applied by filtering
  the child's already-resolved MCP tool definitions, so it is a subset operation; MCP servers are
  always inherited and are not nameable by a persona. Do not add a code path that lets a persona
  attach a server, a provider, or a tool.
- A persona prompt is user-authored text: concatenate it into the message body and never use it as a
  format string or interpolate it anywhere text becomes code. Never store credentials on a persona.

### Provider Integration

- Providers configured in `services/bifrost/config.json`
- Enable specific providers via `ENABLED_PROVIDER_IDS` env var
- Reasoning support via `gateway_options.reasoning` in model config
- Model list caching via `PROVIDER_MODELS_CACHE_TTL_SECONDS`

## Working Rules

- Use `uv run` to execute commands in the service directory
- Follow async/await patterns throughout
- Use Pydantic models for request/response validation
- Keep job event streaming consistent across replicas
- Cache provider models to reduce Bifrost load
- **Never store state in instance variables.** Use PostgreSQL for persistent data and Valkey for ephemeral shared state. Example: `BifrostClient` model-listing cache lives in Valkey under `agent-orchestrator:model-cache:*`, not in `self._models_cache`.

## Provider Configuration

```text
ENABLED_PROVIDER_IDS=mistral,nvidia,openrouter
PROVIDER_MODELS_CACHE_TTL_SECONDS=600
BIFROST_LIST_MODELS_TIMEOUT_SECONDS=8
BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS=600
VALKEY_URL=redis://localhost:6381/0
```

`BIFROST_LIST_MODELS_TIMEOUT_SECONDS` bounds the per-provider model-listing call
so a provider missing an API key fails fast (returns `available=false`) instead
of stalling the `/providers` response for the full ~60s gateway timeout.

`BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` (must be positive) controls how long an
unavailable provider is negatively cached in Valkey under
`agent-orchestrator:model-cache:unavailable:{id}`. While the marker is live,
`/providers` reports that provider `available=false` immediately, without
re-incurring the list-models timeout. A successful listing clears the marker.
After adding an API key, force an immediate re-probe with
`POST /providers/refresh` (clears positive + negative cache entries and the
shared `:all` listing for every enabled provider) or a one-off
`GET /providers?refresh=true`.

## Testing

```bash
uv run pytest tests/unit/ -v              # Unit tests
uv run pytest tests/integration/ -v       # Integration tests
uv run pytest tests/ -v                  # All tests
```

## Commands

```bash
uv run agent-orchestrator         # Start service
uv run pytest                     # Run tests
```

## Agent Guidance

1. Sessions are the primary unit of organization - treat them as persistent agent configurations
2. Jobs are immutable once created; status updates come through SSE events
3. MCP tools merge into the session's effective tool catalog on assignment
4. Reasoning streams are transient and not persisted
5. Use Valkey for cross-replica event fan-out