# Agent Orchestrator

`agent-orchestrator` is the LLM harness service.

It manages durable agent sessions, model/provider configuration, skill assignment, MCP assignment, prompt execution, background jobs, and streamable job events.

It does not replace `game-service`.
Instead, it assigns MCP servers such as `game-service` to an agent session and lets the worker call those tools during prompt execution.

## Run

From the repo root:

```bash
scripts/run.sh start agent-orchestrator
```

Inside the service directory:

```bash
uv run agent-orchestrator
```

Default local URL:

```text
http://localhost:4002
```

## What This Service Is For

Use `agent-orchestrator` when you need to:

- create persistent agent sessions
- choose which provider/model an agent should use
- list supported providers
- list available skills for picker-style UI flows
- assign local skills from `../../skills/<skill_name>` or `../../.opencode/skills/<skill_name>` when running from the service directory
- assign MCP servers like `game-service`
- inspect the effective tool catalog exposed to a session
- submit prompts as background jobs
- inspect job progress and results
- stream job events for a frontend or client

## Provider Configuration

Provider support is configured in two layers.

For Docker Compose, the agent-orchestrator runtime env should live in:

```text
services/agent-orchestrator/.env
```

This file is only for agent-orchestrator runtime settings.

For direct local runs from `services/agent-orchestrator`, set skill roots back to the repo-level skill directories:

```text
SKILL_ROOTS=../../skills
```

For Docker Compose, this file is optional. If it does not exist, agent-orchestrator uses its built-in application defaults, which keeps CI and pipeline parsing from failing on missing local-only env files.

### 1. Bifrost knows how to talk to providers

This is configured in:

```text
services/bifrost/config.json
```

Provider credentials for Bifrost should live in:

```text
services/bifrost/.env
```

That keeps API keys and Bifrost-specific network config with the Bifrost service instead of mixing them into agent-orchestrator envs.

For Docker Compose, `services/bifrost/.env` is also optional. CI can parse the compose files without local secrets, while local runs still pick them up automatically when the file exists.

### 2. Agent Orchestrator decides which providers are enabled

Use this env var:

```text
ENABLED_PROVIDER_IDS
```

Example:

```text
ENABLED_PROVIDER_IDS=mistral,nvidia
```

Only providers in that list are:

- returned by `GET /providers`
- accepted by `PUT /sessions/{session_id}/model-config`

## How To List Providers

Use:

```text
GET /providers
```

This returns only enabled provider IDs, the model prefix used when routing through Bifrost, the currently available models reported by Bifrost, and per-provider availability/error state.

Supported provider IDs include `nvidia`, `openrouter`, `mistral`, `claude`, `openai`, `lmstudio`, and `gemini`.

To avoid hitting Bifrost on every provider-picker refresh, agent-orchestrator keeps a Valkey TTL cache for provider model lists. Configure it with:

```text
PROVIDER_MODELS_CACHE_TTL_SECONDS=600
```

Set it to `0` to disable caching.

The exact response depends on `ENABLED_PROVIDER_IDS`.

### Resilient Listing

Each provider's model-listing call to Bifrost is bounded by a short per-provider timeout so a provider missing an API key fails fast (returns `available=false`) instead of stalling the whole `/providers` response for the full ~60s gateway timeout. Configure the timeout with:

```text
BIFROST_LIST_MODELS_TIMEOUT_SECONDS=8
```

Unavailable providers are then negatively cached in Valkey, so repeat `/providers` calls fast-fail without re-incurring the timeout. Control how long the negative marker lives (must be positive) with:

```text
BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS=600
```

A successful listing clears the negative marker. The remaining enabled providers degrade gracefully: one unavailable provider never blocks the others from being listed.

### Refreshing the Cache

After adding or fixing an API key you do not have to wait for the TTLs to expire:

- `POST /providers/refresh`
  Clears the cached provider model listings (positive and negative entries) for every enabled provider and reports a summary.

- `GET /providers?refresh=true`
  Bypasses the cache for a single call, forcing an immediate re-probe of every enabled provider.

If a provider returns `available: false`, check that:

- the provider is present in `ENABLED_PROVIDER_IDS`
- the matching API key or base URL is set in `services/bifrost/.env`
- `bifrost` has been restarted after the env change
- the negative cache has been cleared (`POST /providers/refresh` or `GET /providers?refresh=true`)

## Endpoint Guide

### Meta

Use these first when integrating the service.

- `GET /health`
  Simple liveness check.

- `GET /ready`
  Reports readiness for database, Bifrost, and worker loop.

- `GET /providers`
  Lists enabled provider IDs, currently available models, plus `available` and `error` for each provider.
  Accepts `?refresh=true` to bypass the model cache for one call.

- `POST /providers/refresh`
  Clears the cached provider model listings (positive and negative entries) for every enabled provider so the next `/providers` call re-probes Bifrost.

### Catalog

Use these to populate selection UIs before a session is configured.

- `GET /providers`
- `POST /providers/refresh`
- `GET /skills`

`GET /skills` returns discovered skills with their path and markdown content.

### Sessions

Use these to create, inspect, update, and terminate agent sessions.

- `GET /sessions`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/jobs`
- `PATCH /sessions/{session_id}`
- `POST /sessions/{session_id}/terminate`

`GET /sessions` supports:

- `status`
- `limit`
- `offset`

Both `GET /sessions` and `GET /sessions/{session_id}/jobs` return a `page` object with `limit`, `offset`, and `total` for UI pagination.

### Session Configuration

Use this to attach an enabled provider/model to a session.

- `PUT /sessions/{session_id}/model-config`

Typical payload:

```json
{
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "gateway_options": {},
  "provider_options": {}
}
```

Reasoning-capable models can be configured through `gateway_options.reasoning`.

Example:

```json
{
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "gateway_options": {
    "reasoning": {
      "effort": "high",
      "max_tokens": 4096
    }
  },
  "provider_options": {}
}
```

agent-orchestrator requests streamed chat completions from Bifrost for prompt execution.
Transient chunk events are fanned out across replicas through the dedicated orchestrator Valkey instance and then exposed on the job SSE endpoint.

When reasoning is enabled:

- live `reasoning` chunks are sent over the SSE job stream and are not persisted to PostgreSQL

Always:

- live streamed `model_output` chunks are sent over the SSE job stream and are not persisted to PostgreSQL
- final completion state, tool events, failures, cancellations, and the completed output remain persisted

In the dashboard UI, the session settings drawer now includes first-class controls for:

- enabling reasoning stream
- choosing reasoning effort
- setting reasoning max tokens

Those controls write the `gateway_options.reasoning` block for you. The advanced JSON editor is still available for manual overrides and other provider-specific settings.

### Session Skills

Use these to manage skills discovered from the configured `SKILL_ROOTS` entries.

- `GET /sessions/{session_id}/skills`
- `POST /sessions/{session_id}/skills`
- `PATCH /sessions/{session_id}/skills/{skill_name}`
- `DELETE /sessions/{session_id}/skills/{skill_name}`

Any skill found in the skill roots can be enabled; enabling registers it first if
needed, so a skill never enabled before — or added to disk after startup — still
works. A skill that is not on disk is rejected with `400 Unknown skill`.

Enabling is a soft toggle: disabling flips a flag rather than deleting the row.
Disabling is therefore idempotent — disabling a skill that is already off, or was
never enabled, succeeds and changes nothing, so a client can safely replay the
skill set it wants. Only a session that does not exist is a `404`. Endpoints that
report a session's skills list only the enabled ones, and a disabled skill is
withdrawn from the agent: it leaves the system prompt and can no longer be loaded
with `load_skill`.

### Session Player Agents

Use these to configure a roster of player agents for an orchestrated multi-player game — one seat
per hero, each with its own provider, model, reasoning effort, and skills, so two configurations can
play the same cooperative game and be compared afterwards.

- `GET /sessions/{session_id}/players`
- `PUT /sessions/{session_id}/players/{player_id}`
- `DELETE /sessions/{session_id}/players/{player_id}`

`player_id` is one of `player1`..`player4`, matching DragnCards' seat naming.

Every field is optional and an **unset field inherits from the session**, so a comparison only has to
state the axis that differs:

```json
{
  "display_name": "Spider-Man",
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "reasoning": { "enabled": true, "effort": "high" },
  "skills": ["marvel-champions-learn-to-play"],
  "gateway_options": {},
  "provider_options": {}
}
```

- `provider_id` / `model_name` unset — inherit the session's model config.
- `gateway_options` / `provider_options` — *overlaid* on the session's, not replacing them.
- `reasoning` — folded into the resolved `gateway_options.reasoning`; `{"enabled": false}` removes it.
- `skills` unset — inherit the session's enabled skills; a list (including `[]`) overrides them.
- MCP servers are always inherited from the session.

When a session has a roster, its master prompt jobs gain the `list_player_agents` and
`prompt_player_agent` built-in tools. `prompt_player_agent` spawns a child session configured from
that seat's row, tagged with the seat id and the session's `game_id`, so every move the seat records
is attributed to it without inference. Pair it with the standard `wait_for_subagent`. The
`marvel-champions-orchestrator` skill is the playbook for driving this.

### Session Tools

Use this to inspect the tool list that the worker will expose to the model after MCP assignments are attached.

- `GET /sessions/{session_id}/tools`

### Session MCPs

Use these to assign tool surfaces the worker may call.

- `GET /sessions/{session_id}/mcps`
- `POST /sessions/{session_id}/mcps`
- `DELETE /sessions/{session_id}/mcps/{assignment_name}`

Typical `game-service` MCP assignment:

```json
{
  "name": "game-service",
  "transport": "streamable-http",
  "server_url": "http://localhost:4001/mcp/",
  "headers": {}
}
```

For local host clients talking to Dockerized services:

- use `http://localhost:4002` for requests into `agent-orchestrator`
- use `http://game-service:8000/mcp/` inside MCP assignments that will be used by the `agent-orchestrator` container

`POST /sessions/{session_id}/mcps` normalizes `streamable-http` MCP URLs to include the trailing slash automatically.

### Prompt Submission

Use this when you want the agent to do work.

- `POST /sessions/{session_id}/prompts`

This does not run inline.
It creates a prompt run, enqueues a background job, and returns immediately.

### Jobs

Use these to inspect the outcome of a prompt or stop it.

- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/status`
- `POST /jobs/{job_id}/cancel`
- `GET /sessions/{session_id}/jobs`

`GET /jobs/{job_id}` includes:

- `latest_event_id`
- `latest_event_type`
- `available_tools`
- `events`
- `outputs`

`GET /sessions/{session_id}/jobs` supports:

- `status`
- `limit`
- `offset`

`GET /jobs/{job_id}/status` is a lightweight polling endpoint that returns only the job summary.

This shape is intended to be usable directly by a future UI without additional aggregation.

### Job Events

Use these for polling or frontend streaming.

- `GET /jobs/{job_id}/events`
  Replay persisted events, optionally with `?after=<event_id>`.

  Supports optional `?event_type=<name>` filtering.

- `GET /jobs/{job_id}/events/stream`
  Stream events as Server-Sent Events.

Event types include:

- `progress`
- `reasoning`
- `model_output`
- `tool_call`
- `tool_result`
- `completion`
- `failure`
- `cancellation`

## Typical Workflow

### Configure a new agent

1. `POST /sessions`
2. `GET /providers`
3. `GET /skills`
4. `PUT /sessions/{session_id}/model-config`
5. `POST /sessions/{session_id}/skills`
6. `POST /sessions/{session_id}/mcps`
7. `GET /sessions/{session_id}/tools`

### Run a prompt

1. `POST /sessions/{session_id}/prompts`
2. `GET /jobs/{job_id}` or `GET /jobs/{job_id}/events/stream`
3. `GET /sessions/{session_id}/jobs` when a UI needs recent session history without fetching the full session detail

### Stop a running prompt

1. `POST /jobs/{job_id}/cancel`
2. `GET /jobs/{job_id}`

## Dependencies

The service expects:

- dedicated orchestrator PostgreSQL
- dedicated orchestrator Valkey for transient cross-replica streaming events
- Bifrost
- one or more skill roots, usually `/app/skills` in Docker or `skills` locally
- optional MCP servers such as `game-service`

Set the Valkey connection with:

```text
VALKEY_URL=redis://localhost:6381/0
```

In Docker Compose, agent-orchestrator uses the dedicated `agent-orchestrator-valkey` service.

## Tests

From the repo root:

```bash
scripts/test.sh unit agent-orchestrator
scripts/test.sh integration agent-orchestrator
```

From the service directory:

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
uv run pytest tests/ -v
```
