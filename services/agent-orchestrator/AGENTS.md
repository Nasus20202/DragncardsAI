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
- **MCP**: both directions — an MCP *client* (`integrations/mcp/`) that pulls external tools into a session, and this service's own MCP *server* (`mcp_server.py`) that exposes its HTTP API as tools at `/mcp`. See **Two MCP directions** below
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
- Events include: `progress`, `reasoning`, `model_output`, `tool_call`, `tool_result`, `skill_loaded`, `compaction`, `compaction_failed`, `subagent_started`, `subagent_completed`, `subagent_failed`, `user_question`, `user_question_answered`, `user_question_closed`, `illegal_action_finding`, `completion`, `failure`, `cancellation`
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

**A session may also run as a persona itself** (`agent_sessions.session_persona`), and only two
fields apply: the system prompt and `allowed_tools`. The provider, model, options and skills stay the
session's own, because those have visible controls on that same session and a persona overwriting the
rows those controls write would make them misreport what the agent runs with. A spawned child has no
competing control, which is why a child materialises the whole persona and a session does not. The
snapshot is written when the NAME is set, into the same `agent_persona` metadata key a child uses, so
the capture rule holds at both levels; the router owns that key and refuses to take it from a client,
which is what stops a `PATCH /sessions` metadata write forging or dropping it.

**`session_allowed_subagents` is which personas a session's agent may spawn, and it is enforced, not
displayed.** Three rules:

- **An empty allowlist means NO persona may be spawned.** Never widen it to "all" — that makes the
  emptiest-looking state the most permissive one and leaves no way to express "none". Spawning with
  no persona at all still works and is not governed by the allowlist.
- **The check lives at dispatch**, in `_resolve_spawn_persona`, above the persona lookup, so it
  covers a model naming a persona, the session's `default_subagent_persona` falling through to it,
  and any HTTP or MCP caller driving a prompt. Filtering the system-prompt catalogue is presentation;
  do not move the check there or into the dashboard.
- **Configuration must not contradict it.** A `default_subagent_persona` outside the allowlist is a
  400, and revoking a persona that is still the default is a 400 unless the same request clears the
  default. Both are validated against the state the request produces, before either is written.

Neither `session_persona` nor the allowlist is frozen after the first job, unlike `session_mode`.
Nothing durable is keyed to either, so a change orphans nothing — and a security control that cannot
be revoked mid-game is not a security control. Seat personas are operator-configured in the roster
and are not agent-nameable, so they are deliberately outside this allowlist.

### Session Modes and Player Seats

A session's `session_mode` is `chat` (the default, the original single-agent flow) or
`orchestrated` (one persistent agent per player seat under a coordinating agent). It
is a column, not a metadata key, because it gates behaviour and `metadata_json` is
client-writable through `PATCH /sessions`. It is frozen once the session has run a
job — the seats' persistent sessions are recorded against it, so a mid-flight change
would orphan or mis-scope them.

In orchestrated mode a seat is a seat id + persona + persistent session. The seat's
session is created on its first prompt with `multi_turn_memory=True`, recorded in
`session_player_configs.agent_session_id`, reused for every later prompt, and
excluded from `_maybe_terminate_child_session`. In `chat` mode nothing changes: a
player agent is still a memoryless child terminated with its job.

**Four rules the trust boundary rests on. Do not break them.**

- **Player text never reaches the orchestrator's system prompt.** `build_system_prompt`
  takes the skill registry, the session's assignments, and the persona catalogue.
  Do not add a parameter that could carry player output into it.
- **A seat's output reaches the orchestrator only through `wrap_player_report`.** The
  seat id and job status are server-set fields read from the seat's session metadata,
  and the seat's text is confined to one delimited block whose markers are stripped
  from that text first. Do not concatenate a report into a prompt, and do not parse a
  seat id out of a report's prose.
- **Legality is decided from game state, never from a player's claim.** A seat saying
  a move was legal, or that it already undid one, is data to verify — never an input
  that can stand in for the check.
- **A seat may act only with its own cards, enforced server-side.** Ownership is
  checked against the seat recorded on the child session, which no tool available to a
  player can write. Never rely on the prompt telling a seat to stay in its lane.

The two out-of-band channels a seat has are built on those rules rather than beside
them. `send_player_message` (seat jobs only, addressed to another configured seat of
the same orchestrating session) and the open findings from `report_illegal_action`
(orchestrating job only) are both delivered by `PromptRunService._collect_seat_inbox`
as **one user-role message ahead of the seat's own prompt**, each entry fenced by the
same `_fence_untrusted_text` helper `wrap_player_report` uses. Do not move any of it
into a system prompt, do not add a second copy of the delimiter strip, and do not give
a seat a way to resolve a finding — resolution is a judgement about game state and
belongs to the party that reads game state authoritatively.

**Emitted history events state the mode.** `history_emitter.stamp_session_mode` puts
`session_mode` on an agent move and on a `user_prompt`, and **omits the key entirely
for `chat`** — so a chat payload stays byte-identical to what it was before the mode
existed, and one reader rule ("absent means chat") covers both that and every event
recorded before the mode existed. The mode and the seat are independent: an
orchestrated event with **no** `player` is the orchestrator's own bookkeeping, which
is exactly what keeps it distinguishable from a seat's play, so never derive one from
the other. A finding goes out through `HistoryEventEmitter.emit_illegal_action` as
event type `illegal_action` under `actor: "agent"`, because history-service pins
`actor` to a fixed `Literal` and a new producer concern therefore arrives as a new
event type — never as a new actor. eval-service relies on that distinction to keep a
finding from being graded as a move.

### Two MCP directions

This service is both an MCP client and an MCP server, and confusing the two costs real time
because both live under the name "MCP":

- **Inbound / client — `integrations/mcp/`.** This service connects *out* to MCP servers
  (game-service by default) and merges their tool definitions into a session's effective tool
  catalog, which the worker then exposes to the model. This is the direction the game-playing
  agent uses; session MCP assignments (`/sessions/{id}/mcps`) configure it.
- **Outbound / server — `mcp_server.py`.** This service's *own* MCP server, mounted at `/mcp`
  by `main.py` — deliberately not by the app factory, because the test suites build the app
  directly and must not start the MCP session manager. Its tools are generated from this
  service's FastAPI OpenAPI schema by `dragncards_common.mcp`, so a tool *is* the endpoint it
  came from and a tool's name is that endpoint's `operation_id`. There is no hand-written tool
  layer, and there should not be one — it would be a second implementation of the API, free to
  drift from the first.

Because tools come from the schema, **adding a route to this service adds an MCP tool
automatically**. Give every route an explicit `operation_id`: without one, FastAPI derives a
name from the function, path and method — `submit_prompt_sessions__session_id__prompts_post` —
and that string becomes the tool name a model has to read.

`EXCLUDED_ROUTES` in `mcp_server.py` is what is deliberately kept out:

- `stream_job_events` (`GET /jobs/{id}/events/stream`). An MCP tool call reads its response to
  completion and an SSE stream never completes, so mapping it to a tool hangs the caller until
  it times out. Poll `list_job_events` with `after` instead.
- The **writes** to the deployment-global skill registry, MCP registry, and persona table —
  `register_skill`, `unregister_skill`, `register_mcp`, `unregister_mcp`, `save_persona`,
  `delete_persona`. An entry changed in any of the three changes what *every* session in the
  deployment resolves, including sessions the caller does not own. Reads of all three stay
  exposed (`list_skill_registry`, `list_mcp_registry`, `list_personas`, `get_persona`), and so
  does the whole per-session lifecycle (`terminate_session`, `delete_session`,
  `disable_session_skill`, `remove_session_mcp`) — excluding the global registries must not cost
  an agent the ability to clean up after itself.
- Health and readiness probes, excluded for every service by the shared bootstrap.

Exclusion applies to MCP only. The HTTP endpoint is untouched, so nothing here limits the
dashboard or a developer with `curl`; the operation just is not offered to a model as a tool.
`tests/unit/test_mcp_server.py` asserts the surface against the real app rather than against
`EXCLUDED_ROUTES`, because an exclusion regex that silently matches nothing looks identical to
one that works.

The full loop this surface exists for — create a game, start a player agent, read its actions,
read the live board, request an evaluation, read the verdict — is in the root
[`AGENTS.md`](../../AGENTS.md#driving-the-system-end-to-end), along with the prerequisites that
otherwise block it.

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

## Browser CORS

`CORS_ALLOW_ORIGINS` is a comma-separated allowlist of browser origins, defaulting
to the local dashboard. **Never widen it to `*`.** That is what this service
shipped with, and because Compose publishes 4002 on the host it meant any page a
developer visited could drive a cross-origin `DELETE /sessions/{id}` or
`POST /sessions/{id}/prompts` — destroying sessions and spending the owner's model
budget (DRA-31). The policy is pinned at the wire level in
`tests/unit/test_cors.py`.

Two things to hold on to when touching this:

- **A request with no `Origin` must keep working.** That is every real caller: the
  dashboard reaches this service through its own server-side Node proxy, including
  the SSE job streams — those are `EventSource` calls to relative
  `/api/proxy/orchestrator/...` URLs, never to port 4002 — and history-service is
  a server-to-server caller.
- **CORS is not authentication.** It only stops a *browser* being used as a
  confused deputy for preflighted methods. Any non-browser client omits `Origin`
  and is unaffected. Requiring a credential is DRA-32, deliberately separate.

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