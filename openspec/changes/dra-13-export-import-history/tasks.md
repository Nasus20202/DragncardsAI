## 1. Define the bundle format

- [x] 1.1 Add `services/history-service/src/history_service/schemas/transfer.py` with
      the `header` / `event` / `snapshot` / `footer` record models, the format id
      `dragncards-ai.game-history`, format version 1, and the NDJSON media type.
- [x] 1.2 Set `extra="ignore"` on every record model so unknown keys from a
      hand-edited or newer file are dropped rather than carried into storage.
- [x] 1.3 Bound every string field to the width of the column that stores it
      (`event_id` 64, `event_type` 128, `idempotency_key` 128,
      `producer_offset` 128) so an oversized value is a readable validation
      error, not a database error mid-transaction.
- [x] 1.4 Reuse the envelope's `Actor` literal for an `event` record's `actor`, so
      a bundle cannot introduce an actor the store does not know.
- [x] 1.5 Move `GAME_ID_PATTERN` to `schemas/envelope.py` and re-export it from
      `api/validation.py`, so the route boundary and the bundle header share one
      definition instead of duplicating the regex.
- [x] 1.6 Document the whole format in `services/history-service/README.md`:
      every record, every field, the ordering, the sorted keys, why no round
      numbers, and what the bundle discloses.

## 2. Stream the export (history-service)

- [x] 2.1 Add `runtime/transfer.py` with `iter_export_lines`, which yields the
      header, then events paged from the repository, then snapshots paged from
      the repository, then the footer — never materializing the bundle.
- [x] 2.2 Serialize each line with sorted keys so two exports of the same game
      diff to the events that actually differ.
- [x] 2.3 Drop `game_id` from every event and snapshot line; the target is chosen
      at import time.
- [x] 2.4 Resolve the header's `plugin_name` from the nearest snapshot then the
      earliest game-state event, mirroring `RestoreService._resolve_plugin_name`;
      export `null` when a game records neither.
- [x] 2.5 Add `Repository.count_snapshots` and optional `after_seq`/`limit`
      paging to `Repository.list_snapshots`, leaving its existing single-argument
      callers behaving exactly as before.
- [x] 2.6 Add `GET /games/{game_id}/export` in `api/routers/transfer.py` as a
      `StreamingResponse` with the NDJSON media type and an attachment filename.
- [x] 2.7 Unit tests: a seeded game exports header/events/snapshots/footer in
      order with the right counts; keys are sorted on every line; event lines
      carry no `game_id`; payloads survive verbatim; an unknown game exports an
      empty bundle; a malformed `game_id` is refused at the boundary.

## 3. Import a bundle atomically (history-service)

- [x] 3.1 Add `BundleReader` to `runtime/transfer.py`: `read_header()` validates
      the first line (so the caller knows the default target before opening a
      transaction) and `records()` resumes the same line stream, validating each
      record as it arrives.
- [x] 3.2 Enforce the structural invariants while streaming — gap-free ascending
      `seq` from 1, snapshots after events, ascending `snapshot_at_seq` with none
      past the last event, a footer whose counts match what was read, nothing
      after the footer, at least one event — each with a message naming the line.
- [x] 3.3 Add `Repository.import_game_history`: one transaction, an
      emptiness check on the target inside that transaction, verbatim writes of
      `seq` / `event_id` / `idempotency_key` / `occurred_at` / `recorded_at`, and
      chunked inserts so the resident slice stays bounded.
- [x] 3.4 Translate a uniqueness violation into a "bundle contains duplicate
      events" error, since the transaction has already rolled back.
- [x] 3.5 Add `POST /import` mapping bundle errors to 400, an existing target to
      409, and an oversized body to 413.
- [x] 3.6 Add `GameIdQuery` so the optional target `game_id` is constrained by the
      same rule as a path `game_id`.
- [x] 3.7 Unit tests for the round trip: export a seeded game, import it under a
      new id, and assert every event field, every snapshot, and that restoring
      the copy at its last `seq` loads the same document and replays the same
      actions as restoring the original.
- [x] 3.8 Unit tests for rejection: unparseable JSON, a non-object line, no
      header, an empty body, a foreign `format`, an unsupported `format_version`,
      a missing footer, disagreeing footer counts, a `seq` gap, a `seq` not
      starting at 1, an unknown `kind`, an unknown `actor`, an oversized field,
      zero events, a snapshot past the last event, snapshots out of order, an
      event after a snapshot, duplicate events, content after the footer, a
      malformed target id.
- [x] 3.9 Unit test that a bundle failing partway leaves the target with no
      events and no snapshots.

## 4. Bound the import body (history-service)

- [x] 4.1 Add `HISTORY_IMPORT_MAX_BYTES` (default 64 MiB) with a validator, to
      `config.py` and `.env.example`, documented in the README table.
- [x] 4.2 Enforce it in the streaming reader against the running byte total, and
      up front against a declared `Content-Length`, answering 413 with the same
      detail the agent-orchestrator's cap uses.
- [x] 4.3 Unit test: a body over the ceiling answers 413 and imports nothing.

## 5. Dashboard controls

- [x] 5.1 Add `historyExportUrl` and `importHistoryBundle` to
      `features/history/lib/history-api.ts`, and `HistoryImportResult` to
      `features/shared/lib/types.ts`.
- [x] 5.2 Add `features/history/components/history-transfer.tsx` with an Export
      button (only while a game is selected, downloading via an anchor rather
      than a buffered fetch) and an Import button driving a hidden file input
      restricted to bundle files.
- [x] 5.3 Mount the controls in the history header's existing action bar and
      render the outcome in a notice row under the header, matching the existing
      truncation-notice and inline-status styles. Do not restyle anything else.
- [x] 5.4 Select the imported game and refresh the games list on success.
- [x] 5.5 Unit tests for the client: the encoded export URL; the file posted as
      the import body; an explicit target id as a query param; the service's
      `detail` surfaced on rejection.
- [x] 5.6 Unit tests for the component: export clicks an anchor at the export URL
      and leaves nothing behind; export is hidden with no selection while import
      remains; a successful import reports counts and selects the game; a
      rejected import reports the service message and selects nothing; the input
      restricts its accepted types.
- [x] 5.7 Unit tests for the wiring: both controls appear in the header, and the
      notice row renders success as a status and rejection as an alert.

## 6. Keep the surrounding files current

- [x] 6.1 Add both endpoints to the history-service README's HTTP API list, and
      document the whole bundle format there: every record, every field, the
      ordering, the sorted keys, why no round numbers, and what a bundle
      discloses.
- [x] 6.2 Add `HISTORY_IMPORT_MAX_BYTES` to all three places it belongs — the
      history-service README config table,
      `services/history-service/.env.example`, and the history-service
      `environment:` block in `docker-compose.yaml`.
- [x] 6.3 Update the root `README.md` architecture prose so the history-service
      paragraph mentions export/import and links to the format documentation.
- [x] 6.4 Grep for an existing history-service config key and for port 4004 to
      find every list the new setting must join: `scripts/service-helpers.sh`
      carries only the port and the `Makefile` only the image name, so neither
      needs a change, and there is no root `.env.example`.
- [x] 6.5 Confirm no Dockerfile change is needed — the endpoints add no
      dependency, no port, and no entrypoint change.
- [x] 6.6 Record, without fixing, that the dashboard Swagger index merges only
      `orchestrator` and `game` (`features/swagger/lib/openapi.ts` loops over
      those two and `fetchOpenApiDocument` knows only their OpenAPI paths), so
      these endpoints cannot appear there until history-service joins that index.
      That is DRA-20's scope, not this change's.
- [x] 6.7 Record, without fixing, that history-service has no OpenTelemetry
      instrumentation in code despite `docker-compose.yaml` setting `OTEL_*` for
      it. The new routes inherit exactly the same (absent) instrumentation as
      every existing route, so this change makes nothing stale there. Overlaps
      DRA-23 (`stanislaw/dra-23-otel-history-eval`).

## 7. Verification

- [x] 6.1 `./scripts/lint.sh --fix` clean.
- [x] 6.2 `./scripts/test.sh unit` — report counts before and after.
- [x] 6.3 `openspec validate --all` (the pre-existing `spec/typed-game-actions`
      failure is untouched).
- [x] 6.4 Confirm no secret reaches a bundle by auditing what every producer puts
      in an event payload and what a game-service snapshot contains, before
      serializing anything wholesale.
