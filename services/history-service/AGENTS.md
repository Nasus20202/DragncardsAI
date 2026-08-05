# History Service Agent Guide

Read this file before making changes in `services/history-service/`.

## Scope

These instructions apply to the history-service and override the repository-level `AGENTS.md`.

## Tech Stack

- **Language**: Python 3.x with `uv`
- **Framework**: FastAPI
- **Database**: dedicated PostgreSQL for the append-only event log + snapshots
- **Transport**: Valkey stream `history:ingest` (consumer group `history-service`)
- **Testing**: pytest with async support (sqlite for unit, real Postgres/Valkey for integration)

## Core Concepts

### Event envelope (shared contract)

Producers (agent-orchestrator, game-service) publish a versioned envelope; the
history-service validates and stores it. Producers supply `occurred_at` and a
stable `idempotency_key`; the history-service assigns the gap-free per-game
`seq` and `recorded_at` at commit time.

```
{ "envelope_version": 1, "event_id": <uuid>, "game_id": <str>,
  "actor": "agent" | "game-service", "event_type": <str>, "payload": <object>,
  "occurred_at": <iso8601>, "idempotency_key": <str>, "producer_offset": <int|str> }
```

`idempotency_key = hash(game_id, actor, producer_offset)`; uniqueness is enforced
on `(game_id, idempotency_key)`. Unknown envelope fields are tolerated for forward
compatibility.

**`actor` is a fixed `Literal`**, so a producer's new concern arrives as a new
`event_type` under an existing actor rather than as a new actor. That is why the
agent-orchestrator's `illegal_action` findings ride on `actor: "agent"` alongside its
`agent_move` events — and why a consumer must never read `actor == "agent"` as "this
is a move".

**`session_mode` is projected on read, not stored as a column.** A payload carries
the key only when the mode is `orchestrated`; a chat-mode event and every event
predating the mode omit it, so their stored bytes are identical and one rule covers
both. `schemas.envelope.session_mode_of` is the only place that resolves the `chat`
default and `EventResponse` the only place that surfaces it, so do not scatter
`payload.get("session_mode", "chat")` at call sites — and do not infer the mode from
whether a `player` key is present, since an orchestrated event with no seat is the
coordinating agent's own bookkeeping. Only unbounded fields belong in
`TIMELINE_OMITTED_PAYLOAD_KEYS`: pruning `session_mode` would cost the timeline read
the one field that lets it classify a whole game at once.

### Ordering and idempotency

`seq` is assigned authoritatively under a per-game advisory lock with
`ON CONFLICT DO NOTHING`. Duplicates never consume a `seq`. Multiple replicas
share one consumer group; per-game ordering holds regardless of which replica
commits.

### Snapshots and restore

Snapshots are full game-service `GameStateSnapshot` exports stored with the
`seq` they correspond to, on a count/time cadence. Restore is dual-layer:
game-state (nearest snapshot + forward replay of `game-service` mutating events)
and agent-context (latest `agent` event's captured conversation context handed
to the orchestrator). Agent events are never replayed as game mutations.

### MCP surface

The service mounts its own MCP server at `/mcp`, wired in `main.py` and
deliberately NOT in the app factory: the test suites build the app directly and
must not start the MCP session manager. `mcp_server.py` declares only the name and
the exclusion list; the mounting itself is `dragncards_common.mcp`.

Tools are generated from this service's FastAPI OpenAPI schema, so a tool IS its
endpoint — with the endpoint's own request and response models as its schema — and
a tool's name is that endpoint's `operation_id`. There is no hand-written tool
layer that could drift from the API.

**Adding a route adds an MCP tool automatically, so give every route an explicit
`operation_id`.** Without one, FastAPI generates a name from the function and path
(`list_events_games__game_id__events_get`), and that is what the tool ends up
called.

`EXCLUDED_ROUTES` in `mcp_server.py` keeps four things out, each for a specific
reason:

- `delete_game_history` (`DELETE /games/{game_id}`) — irreversible. The event store
  is the only durable record of what an agent did, so losing one game's history
  destroys the evidence a debugging loop exists to read.
- `backfill_game_event` (`POST /games/{game_id}/events`) and `import_game_bundle`
  (`POST /import`) — writes into the ordered store. They are the restore and
  migration paths; a fabricated event corrupts the record while every read still
  looks healthy.
- `export_game_bundle` (`GET /games/{game_id}/export`) — a streaming whole-game
  NDJSON bundle. As a tool call it would buffer an entire recorded game, hundreds
  of raw DragnCards states, into the caller's context. Use the paged
  `list_game_events` instead.
- The `health` and `ready` probes, excluded for every service by the shared
  bootstrap: an LLM client gains nothing from them and they crowd the tool list.

Exclusion applies to MCP only. Every one of those endpoints still works over HTTP,
so nothing here reduces what the dashboard or a human with `curl` can do. The
exclusions are regexes matched against generated OpenAPI paths, so
`tests/unit/test_mcp_server.py` asserts tool names against the real app rather
than reading the list — a pattern that quietly matches nothing looks identical to
one that works.

### Browser CORS

`HISTORY_CORS_ALLOW_ORIGINS` is a comma-separated allowlist of browser origins,
defaulting to the local dashboard. **Never widen it to `*`.** That is what this
service shipped with (DRA-31), and because Compose publishes 4004 on the host it
meant any page a developer visited could drive a cross-origin
`DELETE /games/{game_id}` or backfill forged events — precisely the three
operations `EXCLUDED_ROUTES` above withholds from a model, which makes withholding
them decorative. The policy is pinned at the wire level in `tests/unit/test_cors.py`
and matches eval-service, whose shape it was copied from.

Two things to hold on to when touching this:

- **A request with no `Origin` must keep working.** That is every real caller: the
  dashboard reaches this service through its own server-side Node proxy, and
  eval-service, game-service and the orchestrator are server-to-server. CORS does
  not apply to them at all, and a policy that broke them would break the whole
  application while looking secure.
- **CORS is not authentication.** It only stops a *browser* being used as a
  confused deputy for preflighted methods. Any non-browser client omits `Origin`
  and is unaffected. Requiring a credential is DRA-32, deliberately separate.

The whole loop these tools exist for is
[Driving the System End-to-End](../../AGENTS.md#driving-the-system-end-to-end) in
the root `AGENTS.md`.

### Observability

Telemetry comes from `dragncards_common.telemetry`; `history_service/telemetry.py`
only binds `DEFAULT_SERVICE_NAME = "history-service"` to it. Four edges are wired
and all four must stay wired — this service shipped with its `OTEL_*` variables
set in compose and no instrumentation at all (DRA-23), which exported nothing:

- `main.py` calls `setup_telemetry()` before the app is built.
- `runtime/app.py` calls `instrument_fastapi_app(app)` and `shutdown_telemetry()`.
- `storage/db.py` calls `instrument_sqlalchemy_engine(engine)` in `create_engine`.
- `storage/valkey.py` subclasses the shared `RespConnection` to inject this
  module's tracer. The shared client emits NO span without one, so dropping that
  subclass silently loses every Valkey span.

Manual spans cover the workflows library instrumentation cannot explain:
`history.ingest_batch` (one span per polled batch, never per event — the ingester
polls continuously, so per-event spans would be mostly idle noise),
`history.take_snapshot`, and `history.restore`.

A span attribute must never carry an event payload, a snapshot document, or a
restored game state; the permitted attribute keys are pinned in
`tests/unit/test_telemetry.py`. Identifiers, seqs, counts and mode flags only.

## Working Rules

- Use `uv run` for all commands inside the service directory.
- Never store state in memory: PostgreSQL for durable data, Valkey for transport.
- Health/readiness must never echo secrets.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite, mocked Valkey/HTTP)
uv run pytest tests/integration -v   # Integration (needs Postgres + Valkey)
uv run black src tests               # Format
```
