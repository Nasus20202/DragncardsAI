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
