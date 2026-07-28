# Export and import a game's history and current state as a human-readable file

## Why

DRA-13 asks, verbatim:

> Please add option to export and import game histories and current states using
> a human readable format.

Today a recorded game exists only inside the history-service's PostgreSQL. There
is no way to hand a game to someone else, keep it after the database is reset,
diff two runs of the same scenario, or move a game between a laptop and a shared
stack. The service's whole router surface is
`GET|DELETE /games`, `GET|POST /games/{id}/events`, `GET /games/{id}/snapshots`,
`POST /games/{id}/restore`, `GET /health`, `GET /ready` — nothing writes a game
out, and the only write-in path (`POST /games/{id}/events`) takes one envelope at
a time and re-mints `seq`, so it cannot reproduce a game faithfully.

Reconstruction machinery already exists and works: `RestoreService` loads a
full-state base (the nearest snapshot, or the nearest `game-service` event whose
payload embeds the whole post-action state) into a game-service session and
replays the mutating actions after it. What is missing is a way to get a game's
events and snapshots *out of* and *back into* the store, after which restore
already turns them into a playable board. This change adds exactly that and
nothing else.

## What Changes

### A human-readable, streamable bundle format

- **history-service** gains `GET /games/{game_id}/export`, which streams the
  game's complete recorded history as **NDJSON** (newline-delimited JSON, one
  self-contained JSON object per line, keys sorted) served as
  `application/x-ndjson` with a `Content-Disposition: attachment` filename.
- The bundle is `header` line → one `event` line per stored event in ascending
  `seq` → one `snapshot` line per stored snapshot in ascending `snapshot_at_seq`
  → `footer` line. The header carries the format id, format version, source
  `game_id`, `plugin_name`, export timestamp, and the event/snapshot counts; the
  footer repeats the counts.
- **history-service** gains `POST /import`, which reads such a bundle and
  persists it under a target `game_id`.
- **dashboard** gains an "Export" button (per selected game) and an "Import"
  button (game-independent) in the history header, plus an inline result notice
  in the existing notice style.

**Why NDJSON and not pretty-printed JSON, YAML, or a binary format.** A losslessly
exported game is large: `game-service` events embed the complete post-action
DragnCards state, so a real game is tens of megabytes. That rules out anything
that must be resident in one piece.

- NDJSON is plain text a person can open, `grep`, `jq`, and — crucially — **diff
  per event**, because one event is exactly one line. Two runs of the same
  scenario diff to the events that actually differ.
- It streams in both directions: export never materializes the bundle (it pages
  the database and yields lines), and import parses and validates line by line
  instead of buffering the file.
- Every line validates independently against a pydantic model, so a malformed
  file is reported with the **line number** that broke.
- Rejected: a single pretty-printed JSON document — more readable in the small,
  but it forces the whole bundle into memory on both sides and diffs badly (a
  reordered key deep in one state re-indents everything around it). Rejected:
  YAML — no streaming record boundary, a much larger and more surprising parser
  surface for untrusted input, and the payloads are already JSON. Rejected:
  anything compressed or binary — the issue's explicit constraint is human
  readability.

### "Current state" is the bundle's last full-state record, not a separate field

The bundle carries no separate `current_state` field. It does not need one: the
last `game-service` event's payload already embeds the complete post-action
state, and the stored snapshots are verbatim game-service `GameStateSnapshot`
documents. Once a bundle is imported, the **existing** `POST /games/{id}/restore`
reconstructs the current state (target the last `seq`) or any earlier moment,
using the same snapshot-or-state-event base selection it already uses for
natively recorded games. Adding a parallel "load this state" path was rejected:
it would duplicate `RestoreService` and immediately drift from it.

### An import creates a new game; it never overwrites one

Import is **non-destructive**. The target id is the `?game_id=` query parameter
when given, otherwise the source `game_id` from the bundle header. If the target
already has recorded history the request fails with **409** and a message naming
the conflict and telling the caller to pass a different `game_id`. Nothing is
written.

Rationale: the event log is append-only with a gap-free per-game `seq`, and
silently merging or clobbering an existing log would break that contract and
destroy data. Putting an imported game *onto a live board* is a different
operation that already exists — `POST /games/{id}/restore` with
`mode="in_place"` — so import stops at "the history is in the store", and restore
does the rest. `seq`, `event_id`, `idempotency_key`, `occurred_at`, and
`recorded_at` are preserved verbatim from the bundle so the imported game is
byte-identical to the source on read-back, rather than being re-timestamped.

### Import validates the whole bundle, and fails without importing anything

Every record is validated against a pydantic model **before** it reaches the
database, and the whole import runs in **one transaction**, so a bundle that
fails anywhere imports nothing. Rejections, each carrying the offending line
number and a reason:

- unparseable JSON, a non-object line, or an unknown `kind`;
- a first line that is not a `header`, a `format` that is not this format, or a
  `format_version` this service does not support;
- a missing `footer`, or footer counts that disagree with the records actually
  read (this is what catches a truncated or concatenated file);
- `seq` values that are not strictly ascending and gap-free from 1, a snapshot
  before an event, a `snapshot_at_seq` above the last event, or a field longer
  than the column that stores it;
- an actor outside the envelope's four known actors;
- a bundle with zero events;
- a duplicate `idempotency_key`, caught by the store's own unique constraint
  inside the transaction.

An `event` line's `payload` and a `snapshot` line's `snapshot` are typed as plain
JSON objects and stored verbatim, exactly as the ingest path already stores
producer payloads. Unknown top-level keys on a record are **dropped**
(`extra="ignore"`) rather than carried into storage. Parsing is `json.loads`
only: no `eval`, no `pickle`, no object hooks, and no type is reconstructed from
the file.

### Bounded body size

`POST /import` rejects a body over `HISTORY_IMPORT_MAX_BYTES` (default 64 MiB)
with **413** and `{"detail": "Request body too large"}` — the same status and
body the agent-orchestrator's `MaxBodySizeMiddleware` returns for
`MAX_REQUEST_BODY_BYTES` (default 8 MiB), and the same env-var shape. The limit
is enforced in the streaming reader (declared `Content-Length` checked up front,
running total checked per chunk) rather than by adopting that middleware, because
the middleware buffers the entire body to replay it, which would defeat the
streaming import it is meant to protect. The default differs from the
orchestrator's because a lossless game bundle is inherently far larger than an
API request body.

### No secrets are exported

Audited before serializing anything: no event payload and no snapshot contains a
credential. `BOT_EMAIL`/`BOT_PASSWORD` and the DragnCards auth token stay local
to `game_service.logic.session_manager` and never enter session state, snapshots,
or events; the orchestrator's Bifrost API key and MCP registry `headers_json` —
the one place a bearer token lives — are never part of a history envelope. The
export therefore serializes stored events and snapshots verbatim, and reads
**only** the history store: no service configuration, environment, provider
credentials, or MCP registry rows are joined in.

What the bundle does contain, and is intended to: the agent's system prompt and
full conversation context (including MCP tool results), user prompt text, and the
DragnCards numeric user id and player alias carried in every game state. Those
are the recorded game itself — redacting them would make the export lossy and
un-importable — but they mean a bundle is the user's own game data and should be
shared as deliberately as a database dump.

### Round numbers are not surfaced

The bundle contains no derived round number. DragnCards `roundNumber` counts
*completed* rounds and a `game-service` event embeds the state *after* its action,
so a round label is a derivation that DRA-9 settled for the UI in
`features/history/lib/history-rounds.ts`. Repeating that derivation in the export
format would create a second place for it to be wrong. Events are exported
verbatim; a reader derives rounds the same way the UI does.

## Non-goals

- Changing the events/snapshots list endpoints, their paging, or their limits.
  Export reads through the existing repository paging; the read API is untouched.
- Changing `RestoreService`, the restore endpoint, or its base-selection logic.
  Import produces ordinary stored history that restore already understands.
- Merging into, appending to, or overwriting an existing game's history.
- Exporting or importing agent-orchestrator sessions, jobs, skills, MCP
  registries, or eval-service requests. The bundle is history-store data only.
- Redacting, pseudonymizing, or filtering event content. The export is lossless.
- Compression, chunked/resumable transfer, or a background export job.
- Deriving round numbers, phases, or any other display metadata in the format.
- Restyling any existing dashboard component.

## Impact

- Affected specs: `history-event-store` (a human-readable export of a game's
  history; a validated, atomic, non-destructive import; a bounded import body).
  `game-history-ui` (export and import controls in the history header).
- Affected code:
  - `services/history-service/src/history_service/schemas/transfer.py` (new)
  - `services/history-service/src/history_service/runtime/transfer.py` (new)
  - `services/history-service/src/history_service/api/routers/transfer.py` (new)
  - `services/history-service/src/history_service/storage/repository.py`
    (paged snapshot read, snapshot count, transactional import)
  - `services/history-service/src/history_service/config.py`,
    `runtime/app.py`, `README.md`, `.env.example`
  - `services/dashboard/features/history/components/history-transfer.tsx` (new),
    `features/history/components/history-workspace.tsx`,
    `features/history/lib/history-api.ts`,
    `features/shared/lib/types.ts`
- New configuration: `HISTORY_IMPORT_MAX_BYTES` (default 67108864).
- No database migration: import writes the existing `events` and `snapshots`
  tables with the existing columns.
