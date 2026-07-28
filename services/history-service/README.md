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
| `HISTORY_IMPORT_MAX_BYTES` | `67108864` | Largest accepted `POST /import` body |
| `GAME_SERVICE_BASE_URL` | `http://localhost:4001` | Snapshot export/import + replay |
| `AGENT_ORCHESTRATOR_BASE_URL` | `http://localhost:4002` | Resume-from-context |

## HTTP API

- `POST /games/{game_id}/events` — HTTP backfill ingestion (same envelope).
- `GET  /games/{game_id}/events?after_seq=&limit=` — events by ascending `seq`, paged.
- `GET  /games/{game_id}/snapshots` — stored snapshots with their `seq`.
- `POST /games/{game_id}/restore` — body `{ "target_seq": int, "mode": "new"|"in_place" }`.
- `GET  /games/{game_id}/export` — the game's whole history as an NDJSON bundle.
- `POST /import?game_id=` — import an NDJSON bundle as a new game's history.
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

## History bundles (export / import)

A bundle is **NDJSON**: one self-contained JSON object per line, keys sorted, in
this order and no other.

| Line | `kind` | Content |
| --- | --- | --- |
| first | `header` | `format`, `format_version`, source `game_id`, `plugin_name` (null when the game recorded none), `exported_at`, `event_count`, `snapshot_count` |
| next `event_count` lines | `event` | one stored event, ascending `seq`: `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, `producer_offset` |
| next `snapshot_count` lines | `snapshot` | one stored snapshot, ascending `snapshot_at_seq`: `snapshot_at_seq`, `snapshot`, `created_at` |
| last | `footer` | `event_count`, `snapshot_count`, repeated |

```
{"event_count":122,"exported_at":"2026-07-28T21:40:00+00:00","format":"dragncards-ai.game-history","format_version":1,"game_id":"3512...","kind":"header","plugin_name":"Marvel Champions","snapshot_count":4}
{"actor":"game-service","envelope_version":1,"event_id":"...","event_type":"game_state","idempotency_key":"...","kind":"event","occurred_at":"...","payload":{...},"producer_offset":"0","recorded_at":"...","seq":1}
{"created_at":"...","kind":"snapshot","snapshot":{"game":{...},"plugin_name":"Marvel Champions","schema_version":1},"snapshot_at_seq":25}
{"event_count":122,"kind":"footer","snapshot_count":4}
```

Every field above is written on export and read on import; there are no reserved
or unused fields. No line carries a `game_id` — the target game is chosen at
import time. Unknown keys on a record are ignored, so a bundle from a future
version still reads as long as its `format_version` is one this service knows.
Keys are sorted so two exports of the same scenario diff to the events that
actually differ. Round and phase labels are **not** in the format: DragnCards
`roundNumber` counts *completed* rounds and an event embeds the state *after* its
action, so the round shown for an event is a derivation, done in the dashboard
(`features/history/lib/history-rounds.ts`) rather than duplicated here.

**Export** streams; it never materializes the bundle. It reads only the history
store, so no configuration or credential can reach the file. It does serialize
the recorded game in full, which includes the agent's system prompt and
conversation context, user prompt text, and the DragnCards user id and player
alias in every game state — a bundle is game data and should be shared as
deliberately as a database dump. An unknown game exports a header/footer pair
with zero counts.

**Import** is non-destructive and atomic. The target is `?game_id=` when given,
else the header's `game_id`; a target that already has history is refused with
**409** and nothing is written. Records are validated against the bundle schemas
as they stream and written in one transaction, so a malformed, truncated, or
oversized file imports nothing and the **400** names the line at fault. The
invariants checked are the store's own: gap-free ascending `seq` from 1,
snapshots after the events with ascending `snapshot_at_seq` and none past the
last event, footer counts matching the records read, nothing after the footer,
and at least one event. A body
over `HISTORY_IMPORT_MAX_BYTES` is refused with **413**. `seq`, `event_id`,
`idempotency_key`, `occurred_at`, and `recorded_at` are preserved verbatim, so an
imported game reads back identical to the game it came from.

Import stops at "the history is in the store". Putting an imported game onto a
playable board is `POST /games/{game_id}/restore` — target the last `seq` for the
current state, or any earlier `seq` for an earlier moment.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite + mocks)
uv run pytest tests/integration -v   # Integration (needs Postgres + Valkey)
```
