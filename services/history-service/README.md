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
| `HISTORY_CORS_ALLOW_ORIGINS` | `http://localhost:3001,http://127.0.0.1:3001` | Comma-separated browser CORS allowlist (see [Browser CORS](#browser-cors)) |

Standard OpenTelemetry variables (`OTEL_SERVICE_NAME`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SDK_DISABLED`)
are read too; see Observability below.

## Observability

Traces, metrics and logs are exported over OTLP/HTTP to `otel-lgtm` (Grafana on
http://localhost:3004). The bootstrap is `dragncards_common.telemetry`, bound to
this service's name in `history_service/telemetry.py`; the instrumented edges are
the HTTP server, outbound HTTP, PostgreSQL via SQLAlchemy, and Valkey via the
shared RESP client. Manual spans cover `history.ingest_batch` (one per polled
batch), `history.take_snapshot` and `history.restore`.

Set `OTEL_SDK_DISABLED=true` to run with telemetry off; the service is otherwise
unaffected. Spans carry identifiers, seqs and counts only — never an event
payload, a snapshot document, or a restored game state.

## HTTP API

- `POST /games/{game_id}/events` — HTTP backfill ingestion (same envelope).
- `GET  /games/{game_id}/events?after_seq=&limit=` — events by ascending `seq`,
  paged, payloads intact (`limit` max 1000).
- `GET  /games/{game_id}/timeline?after_seq=&limit=` — the same events by
  ascending `seq`, with the two unbounded payload fields removed (`limit` max
  5000). See below.
- `GET  /games/{game_id}/snapshots` — stored snapshots with their `seq`.
- `POST /games/{game_id}/restore` — body
  `{ "target_seq": int, "mode": "new"|"in_place", "ephemeral": bool }`. See
  [Restoring a game](#restoring-a-game).
- `GET  /games/{game_id}/export` — the game's whole history as an NDJSON bundle.
- `POST /import?game_id=` — import an NDJSON bundle as a new game's history.
- `GET  /health`, `GET /ready` — liveness/readiness (no secrets).

Unknown games return empty results, not errors.

### Restoring a game

A restore rebuilds two layers, and they are not equally essential. The **game state**
is the restore: the densest full-state base at or before the target — a periodic
snapshot or a `game_state` event, whichever is more recent — is loaded into a
game-service session, then the `game-service` events after it are replayed forward.
The **agent conversation** is an enhancement to it, handed to agent-orchestrator so a
resumed agent faces the same decision.

`mode` chooses what receives the restored state:

- `"new"` creates a fresh DragnCards game with its own history and leaves the original
  untouched. The response's `room_slug` names the room that was created, so a caller
  never has to list every live session to find it. Add `"ephemeral": true` for a
  view-only reconstruction: a non-emitting session, reaped server-side by TTL, which
  records no history and gets no agent session.
- `"in_place"` rewinds the existing live session, discarding state after the target.

Beyond `status`, `game_session_id`/`session_id` and `room_slug`, the response reports
the agent layer separately from the game-state layer:

- `agent_context_restored` — whether the agent conversation was rebuilt.
- `agent_context_note` — a human-readable reason when it was not.

**A missing agent session does not fail a restore, by design.** agent-orchestrator
answers `404` to an `in_place` context restore when no *active* agent session is bound
to the `game_id`, and that is a correct answer: the session that played a game is
terminated long before anyone browses its history. history-service treats that `404` as
"there is no agent session to resume", completes the game-state restore, and explains
itself on `agent_context_note`. Any other upstream status still fails the restore, so a
genuine fault is never swallowed. Do not "fix" this by making the `404` fatal again: the
agent layer runs *after* the game state has been written, and an `in_place` restore has
no rollback, so failing there reported a rewind that had already happened as a failure
(DRA-26).

An `in_place` restore is rejected — before anything is mutated — when the live
game-service session no longer exists, or when no full-state base of either kind exists
at or before the target (replaying forward onto an un-rewound live session would
double-apply every event). Both cases name the branchable restore as the alternative.

### Which read to use

`GET /games/{game_id}/events` serves complete payloads and is what the restore
replay and the eval-service judge need. It is expensive to walk: a
`game-service` event embeds the raw DragnCards room state, which is ~450-470 KB
per event, so a whole game is tens of megabytes.

`GET /games/{game_id}/timeline` is for listing a game — a transcript, a
navigation tree, a round breakdown. It returns the same entry shape with
`state` and `conversation_context` removed from each payload, plus
`payload_complete: false` to say so, and keeps a projection of the state under
`payload.state.game` holding `roundNumber` and `stepId` so round and phase
labels still work. Pruning happens in SQL (`jsonb - 'key'` on Postgres,
`json_remove` on sqlite), so the omitted values are never deserialized or
re-serialized. Both reads share one cursor contract: pass `after_seq`, follow
`next_after_seq` until it is absent.

To get one event's complete payload after listing, use the events read's
exclusive cursor: `GET /games/{game_id}/events?after_seq={seq-1}&limit=1`.

Measured over loopback HTTP against game-shaped fixtures with realistic
466 KiB state payloads (sqlite-backed; Postgres `jsonb` should be at least as
fast, unverified):

| read | 122 events | 400 events |
| --- | --- | --- |
| `GET /events?limit=1000` | 0.50 s, 26.2 MiB | 2.32 s, 86.0 MiB |
| `GET /timeline?limit=5000` | 0.14 s, 82 KiB | 0.57 s, 262 KiB |
| `GET /timeline` with nothing new after the last cursor | 1.3 ms, 58 B | 1.4 ms, 58 B |
| one event's full payload | 7 ms, 428 KiB | 7 ms, 428 KiB |
| `GET /games` | 8 ms | 8 ms |

## MCP surface

The same HTTP API is exposed as MCP tools over streamable-HTTP at
http://localhost:4004/mcp/ (clients address it with the trailing slash). It exists
so an assistant working in this repository can read a recorded game as tool calls —
list recorded games, walk a game's events and timeline, inspect snapshots, restore
a session to a past moment — instead of hand-written `curl` against endpoints whose
shape it has to guess. The transport is mounted in `main.py`, not in the app
factory, so the test suites never start the MCP session manager.

Tools are **generated from this service's OpenAPI schema** by
`dragncards_common.mcp`, so a tool is exactly the endpoint it came from and a
tool's name is that endpoint's `operation_id`: `list_recorded_games`,
`list_game_events`, `list_game_timeline`, `list_game_snapshots`, `restore_game`.

`history_service/mcp_server.py` lists what is kept out:

| Not a tool | Why |
| --- | --- |
| `delete_game_history` | Irreversible — the event store is the only record of what an agent did |
| `backfill_game_event` | Writes into the ordered store; a fabricated event corrupts the record while every read still looks healthy |
| `import_game_bundle` | Same write path, for a whole bundle |
| `export_game_bundle` | Streams a whole recorded game; as a tool it would buffer tens of megabytes into the caller's context — use the paged `list_game_events` |
| `health`, `ready` | Probes are noise in an LLM's tool list |

Exclusion applies to MCP only; every one of those endpoints still works over HTTP.

The end-to-end debugging loop these tools exist for is documented in
[`AGENTS.md`](../../AGENTS.md#driving-the-system-end-to-end).

## Browser CORS

`HISTORY_CORS_ALLOW_ORIGINS` is a comma-separated allowlist of browser origins,
defaulting to the local dashboard (`http://localhost:3001,http://127.0.0.1:3001`).
It must never be set to `*`.

Docker Compose publishes 4004 on the host, so under a wildcard allowlist *any* web
page a developer happens to visit while the stack is running could issue a
cross-origin `DELETE http://localhost:4004/games/{game_id}` — or backfill forged
events — and the browser would carry it out. That reaches exactly the three
operations the table above withholds from MCP, which makes withholding them
decorative: `delete_game_history`, `backfill_game_event` and `import_game_bundle`
are kept away from a model and then handed to any page in a browser.

A strict allowlist does not affect normal use, because nothing reaches this service
from a browser directly:

- The dashboard calls it **through its own server-side proxy**
  (`/api/proxy/history/...`), so the request to 4004 originates in the dashboard's
  Node process and carries no `Origin` header at all. That proxy also strips
  `cookie` and `authorization` and rewrites `host`, and rejects cross-site browser
  requests via `isCrossSiteRequest`.
- eval-service, game-service and the agent-orchestrator are server-to-server
  callers, likewise with no `Origin`.
- MCP clients are not browsers.

Requests with no `Origin` are outside CORS entirely and are unaffected by this
setting — that is the path the whole application actually depends on.

**CORS is not authentication.** It stops a browser being used as a confused deputy
for methods that require a preflight (`DELETE`, `PUT`, and `POST` with a JSON
content type), which is the attack above. It does not stop a non-browser client —
`curl`, a script, anything that can reach the port — from calling this service
directly, because such a client simply omits `Origin`. Requiring a credential is
tracked separately as DRA-32.

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

### Session mode on a recorded event

`payload` is stored and returned verbatim. An event from an agent session may carry
an optional `session_mode` key naming the orchestration mode that session ran in
(`orchestrated`). It is **absent** on a chat-mode event and on every event recorded
before the mode existed, so those two are the same shape and there is exactly one
rule for reading them: absent means `chat`.

Both event read paths — `GET /games/{game_id}/events` and `GET /games/{game_id}/timeline` —
therefore project the resolved mode as a top-level `session_mode` field, defaulting
to `chat`, so a consumer can tell an orchestrated timeline from a chat one without
digging into the payload. In particular it must not be inferred from the presence of
a seat identifier: an orchestrated event with no `player` is the coordinating
agent's own bookkeeping, not a chat event. An orchestrated seat's move carries both
the mode and its `player`; the coordinator's own events carry the mode and no seat.

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
