# History Service

Durable, per-game event store for DragnCards agent play. Ingests events from both
producers (agent-orchestrator and game-service) over a shared Valkey stream (plus
an HTTP backfill path), stores them in a dedicated PostgreSQL in strict per-game
order, checkpoints full game-state snapshots on a cadence, and restores a game to
any past moment (game state + agent conversation context).

## Quick start

```bash
cd services/history-service
uv sync
uv run history-service        # serves on :4004 by default
```

## Configuration

All settings have secret-free defaults; secrets live only in
`HISTORY_DATABASE_URL`. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HISTORY_DATABASE_URL` | `postgresql+asyncpg://...:5442/history_service` | Dedicated event-store DB |
| `VALKEY_URL` | `redis://localhost:6381/0` | Ingestion stream transport |
| `HISTORY_INGEST_STREAM` | `history:ingest` | Shared ingest stream key |
| `HISTORY_INGEST_CONSUMER_GROUP` | `history-service` | Consumer group |
| `HISTORY_INGEST_STREAM_MAXLEN` | `100000` | Approximate stream cap |
| `HISTORY_CONSUMER_LAG_ALERT_THRESHOLD` | `1000` | Emit lag signal above this |
| `SNAPSHOT_EVERY_N_EVENTS` | `25` | Count-based snapshot cadence |
| `SNAPSHOT_MAX_INTERVAL_SECONDS` | `300` | Time-based snapshot cadence |
| `GAME_SERVICE_BASE_URL` | `http://localhost:4001` | Snapshot export/import + replay |
| `AGENT_ORCHESTRATOR_BASE_URL` | `http://localhost:4002` | Resume-from-context |

## HTTP API

- `POST /games/{game_id}/events` — HTTP backfill ingestion (same envelope).
- `GET  /games/{game_id}/events?after_seq=&limit=` — events by ascending `seq`, paged.
- `GET  /games/{game_id}/snapshots` — stored snapshots with their `seq`.
- `POST /games/{game_id}/restore` — body `{ "target_seq": int, "mode": "new"|"in_place" }`.
- `GET  /health`, `GET /ready` — liveness/readiness (no secrets).

Unknown games return empty results, not errors.

## Event envelope

```json
{
  "envelope_version": 1,
  "event_id": "uuid",
  "game_id": "string",
  "actor": "agent | game-service",
  "event_type": "string",
  "payload": {},
  "occurred_at": "iso8601",
  "idempotency_key": "string",
  "producer_offset": "int|string"
}
```

The history-service assigns `seq` (gap-free per game, from 1) and `recorded_at`.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite + mocks)
uv run pytest tests/integration -v   # Integration (needs Postgres + Valkey)
```
