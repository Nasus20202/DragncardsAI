# History Event Store

## MODIFIED Requirements

### Requirement: Versioned event envelope
The history-service SHALL define a versioned event envelope containing an envelope version, a game correlation identifier (`game_id`), the `platform` that produced the game, an actor of `agent`, `game-service`, or `evaluator`, an event type, a JSON payload, a producer-supplied occurrence timestamp, an idempotency key, and a history-assigned monotonic per-game sequence number and recorded timestamp.

`platform` SHALL be a short slug naming the game platform the event came from (`dragncards`, `marvel-lcg`). It SHALL be OPTIONAL on the wire and SHALL default to `dragncards` when a producer omits it, so an older producer and a newer consumer interoperate through a rolling restart with no coordinated deploy and no envelope-version bump. An envelope carrying an unknown platform slug SHALL be rejected with a validation error rather than stored under a value no consumer can interpret.

`platform` SHALL be stored as a first-class field rather than inside `payload`, and SHALL be returned on every read that returns an envelope, so a consumer can tell which platform produced an event without inspecting the payload's shape.

#### Scenario: Accept a well-formed envelope
- **WHEN** a producer submits an event envelope containing `envelope_version`, `game_id`, `platform`, `actor`, `event_type`, `payload`, `occurred_at`, and `idempotency_key`
- **THEN** the history-service SHALL accept the envelope and SHALL assign a monotonic per-game `seq` and a `recorded_at` timestamp before persisting it

#### Scenario: An envelope without a platform reads as dragncards
- **WHEN** a producer built before this change submits an envelope with no `platform` field
- **THEN** the history-service SHALL accept it and SHALL store and return `platform` as `dragncards`
- **AND** the stored meaning of every event recorded before this change SHALL be unchanged

#### Scenario: An unknown platform slug is refused
- **WHEN** a producer submits an envelope whose `platform` is a slug the service does not know
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Reject an envelope missing required fields
- **WHEN** a producer submits an envelope missing `game_id`, `actor`, or `event_type`
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Accept the evaluator actor
- **WHEN** a producer submits an envelope whose `actor` is `evaluator`
- **THEN** the history-service SHALL accept the envelope and SHALL persist it with the same ordering and idempotency rules as `agent` and `game-service` events

#### Scenario: Reject an unknown actor
- **WHEN** a producer submits an envelope whose `actor` is none of `agent`, `game-service`, or `evaluator`
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Tolerate unknown forward-compatible fields
- **WHEN** a producer submits an envelope with a recognized `envelope_version` and additional unknown fields
- **THEN** the history-service SHALL persist the envelope without failing on the unknown fields

#### Scenario: Evaluator events are not replayed as game mutations
- **WHEN** the history-service replays events forward during a restore
- **THEN** it SHALL NOT apply `evaluator` events as game mutations, treating them as advisory like `agent` events

### Requirement: Ordered per-game event storage
The history-service SHALL store events in a strict, gap-free, monotonically increasing order per `game_id` **and `platform`**, assigning the sequence number authoritatively at commit time rather than trusting producer-supplied ordering.

The sequence series SHALL be scoped to the pair `(game_id, platform)`: the next `seq` SHALL be computed within that pair, and the advisory lock that serialises concurrent commits SHALL be derived from that pair rather than from `game_id` alone, so two recordings that share an identifier on different platforms neither interleave into one series nor block each other on the same lock.

#### Scenario: Sequence numbers are gap-free and increasing per game
- **WHEN** multiple events for the same `game_id` and `platform` are committed
- **THEN** each committed event SHALL receive a `seq` exactly one greater than the previously committed event for that pair, starting at 1

#### Scenario: Out-of-order delivery is ordered authoritatively
- **WHEN** events for the same `game_id` arrive in an order different from their `occurred_at` timestamps
- **THEN** the history-service SHALL assign `seq` in commit order and SHALL return events ordered by `seq` on retrieval

#### Scenario: Independent ordering across games
- **WHEN** events for two different `game_id` values are committed interleaved
- **THEN** each `game_id` SHALL maintain its own independent gap-free `seq` series

#### Scenario: The same identifier on two platforms keeps two independent series
- **WHEN** events are committed for the same `game_id` under `platform` `dragncards` and under `platform` `marvel-lcg`
- **THEN** each pair SHALL maintain its own gap-free `seq` series starting at 1
- **AND** neither series SHALL contain an event of the other platform

#### Scenario: The commit lock is scoped to the platform too
- **WHEN** two commits for the same `game_id` on different platforms run concurrently
- **THEN** they SHALL NOT serialise on one another's lock
- **AND** both SHALL commit with the correct `seq` in their own series

### Requirement: Dual-source idempotent ingestion
The history-service SHALL ingest events from both producers over a shared Valkey stream consumer group as the primary path and SHALL accept the same envelope through an authenticated HTTP backfill endpoint, and SHALL guarantee that at-least-once duplicate deliveries are stored at most once per `game_id` **and `platform`**. On the stream path the history-service SHALL isolate per-entry commit failures so a transient failure on one entry neither aborts the rest of the batch nor loses that entry, and SHALL recover pending stream entries (from a failed commit or a crashed consumer) by reclaiming and re-processing them through the same idempotent commit path.

The idempotency key SHALL be computed over the platform as well as the game, and the uniqueness constraint that enforces it SHALL be scoped to `(game_id, platform, idempotency_key)`, so a duplicate is de-duplicated only against the same platform's recording and two platforms' events can never collide into one stored row.

#### Scenario: Ingest from the Valkey stream
- **WHEN** a producer publishes an event envelope to the shared history ingestion Valkey stream
- **THEN** the history-service SHALL consume it through its consumer group, persist it, and acknowledge the stream entry

#### Scenario: Ingest from the HTTP backfill endpoint
- **WHEN** a client submits an event envelope to the history-service HTTP ingestion endpoint for a `game_id`
- **THEN** the history-service SHALL persist the event using the same envelope contract and ordering rules as the Valkey path

#### Scenario: Duplicate delivery is stored once
- **WHEN** the same envelope (identical `game_id`, `platform` and `idempotency_key`) is delivered more than once
- **THEN** the history-service SHALL persist it exactly once, SHALL NOT consume an additional `seq` for the duplicate, and SHALL acknowledge the duplicate delivery

#### Scenario: The same idempotency key on two platforms is two events
- **WHEN** two envelopes carry the same `game_id` and the same `idempotency_key` but different `platform` values
- **THEN** the history-service SHALL persist both, each in its own platform's `seq` series
- **AND** SHALL NOT treat the second as a duplicate of the first

#### Scenario: A transient commit failure does not lose other entries in the batch
- **WHEN** committing one entry of a stream batch fails transiently (e.g. a database deadlock or connection blip) while other entries in the same batch commit successfully
- **THEN** the history-service SHALL persist and acknowledge the successful entries, SHALL NOT abort processing the remainder of the batch, and SHALL leave the failed entry un-acknowledged (pending) rather than dropping it

#### Scenario: Stale pending entries are reclaimed and committed
- **WHEN** a stream entry has remained pending and un-acknowledged for longer than the configured minimum idle time (because its consumer crashed or a prior commit failed)
- **THEN** the history-service SHALL reclaim it onto a live consumer and re-process it through the idempotent commit path, persisting it exactly once (never consuming an additional `seq` if it was already committed) and acknowledging it

### Requirement: List games with recorded history

The history-service SHALL expose an endpoint listing every game that has recorded history, including the game identifier, the `platform` that produced it, its event count, and its first and last recorded timestamps, ordered by most recent activity, computed without a per-game query fan-out.

The listing SHALL accept an optional platform filter and SHALL return only the games of the named platform when one is supplied, so a client can present one platform's games without reading and discarding the other's. An omitted filter SHALL list every platform's games, so the default view is unchanged for a store that holds only `dragncards` recordings.

#### Scenario: Listing returns recorded games

- **WHEN** a client requests the games list and two games have recorded events
- **THEN** the response contains both games with their platform, event counts and first/last recorded timestamps, ordered by last activity descending

#### Scenario: Listing is filterable by platform

- **WHEN** a client requests the games list naming a platform and the store holds games of both platforms
- **THEN** the response SHALL contain only that platform's games
- **AND** requesting the list with no platform named SHALL return the games of every platform

#### Scenario: Listing is empty when nothing is recorded

- **WHEN** a client requests the games list and no events have been recorded
- **THEN** the response is an empty list

### Requirement: Human-readable export of a game's recorded history

The history-service SHALL expose a read endpoint that returns a game's complete recorded history — every stored event and every stored snapshot — as a single human-readable file.

The bundle format SHALL be NDJSON: one self-contained JSON object per line, with object keys serialized in sorted order so that two exports of the same history differ only where the history differs. The records SHALL appear in exactly this order: one `header` record, then `blob`, `event` and `snapshot` records, then one `footer` record. `event` records SHALL appear in ascending `seq` and `snapshot` records SHALL appear after every `event` in ascending `snapshot_at_seq`. A `blob` record SHALL appear before the first record that references it and SHALL be permitted to appear anywhere between the header and the footer, so that a bundle can be both written and read in one pass without buffering.

The format SHALL be identified as version 2. The `header` SHALL carry the format identifier, the format version, the source `game_id`, the `platform` that produced the game, the game's recorded `plugin_name` (null when the game recorded none), the export timestamp, the export mode, the payload fields that mode omits, and the event, snapshot and blob counts. The `footer` SHALL repeat the event, snapshot and blob counts. An `event` record SHALL carry `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset`. A `snapshot` record SHALL carry `snapshot_at_seq`, `snapshot`, and `created_at`. A `blob` record SHALL carry its identifier, its value, and the path at which that value was first encountered. No record SHALL carry a `game_id`, because the target game is chosen at import time. No record SHALL carry a `platform` of its own, because a bundle is one game's history and a game belongs to one platform. Every field the format defines SHALL be written on export and read on import; the format SHALL NOT define reserved or unused fields.

Adding `platform` to the header SHALL NOT bump the format version. It is written on every export and defaulted to `dragncards` on import when absent, so a bundle written before this change imports unchanged and a bundle written after it is read by an older service as a version 2 bundle with one unknown header key, which that service already discards. A version bump would instead make every new bundle unreadable by an older service for a field that is defaultable in both directions.

The response SHALL be served with the NDJSON media type and a `Content-Disposition: attachment` filename derived from the `game_id` and the mode. The export SHALL be streamed rather than materialized in full, so that a game whose every event embeds a complete board state does not have to fit in memory.

The export SHALL read only the history store. It SHALL NOT include service configuration, environment values, provider credentials, MCP registry headers, or any other data outside the stored events and snapshots.

The bundle SHALL NOT carry a derived round number, phase name, or other display metadata, because a platform's raw round counter does not always count the round of play — DragnCards `roundNumber` counts completed rounds while marvel-lcg's `round_id` is already the round of play — and a `game-service` event embeds the state after its action, making a round label a derivation that belongs to the reader rather than the format.

Exporting a game with no recorded history SHALL return a bundle consisting of a `header` and a `footer` with zero counts, consistent with the read endpoints' treatment of unknown games; it SHALL NOT be an error.

#### Scenario: Export a recorded game

- **WHEN** a client requests the export of a game that has recorded events and snapshots
- **THEN** the service SHALL answer with an NDJSON attachment whose first line is a `header` naming the format, its version, the game, its platform, its plugin, the mode and the counts; whose next lines are the `blob` records together with one `event` per stored event in ascending `seq` followed by one `snapshot` per stored snapshot in ascending `snapshot_at_seq`; and whose last line is a `footer` repeating the counts

#### Scenario: An exported bundle names the platform once, in its header

- **WHEN** a marvel-lcg game's bundle is inspected
- **THEN** the `header` SHALL declare `platform` as `marvel-lcg`
- **AND** no `event`, `snapshot` or `blob` record SHALL carry a `platform` field of its own

#### Scenario: Exported events are verbatim and carry no game id

- **WHEN** a bundle's `event` records are read back and their references resolved
- **THEN** each SHALL carry the stored `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset` unchanged, and SHALL NOT carry a `game_id`

#### Scenario: Bundle lines are key-sorted so exports diff cleanly

- **WHEN** any line of a bundle is parsed
- **THEN** its object keys SHALL be in sorted order

#### Scenario: Two exports of the same history are identical

- **WHEN** the same game is exported twice in the same mode with no history written in between
- **THEN** the two bundles SHALL differ only in the header's export timestamp, because blob identifiers are assigned in first-encounter order rather than from a hash or a counter that depends on timing

#### Scenario: Exporting a game with no history

- **WHEN** a client requests the export of a `game_id` that has no recorded history
- **THEN** the service SHALL answer with a `header` and a `footer` declaring zero events, zero snapshots and zero blobs, and SHALL NOT return an error

#### Scenario: Export carries no credential

- **WHEN** a bundle is inspected for secrets
- **THEN** it SHALL contain no API key, bearer token, authorization header, database credential, or other value drawn from service configuration or environment

### Requirement: Previously exported bundles remain importable

The history-service SHALL accept bundles declaring format version 1 as well as format version 2, so that a bundle a user exported before this capability existed still imports.

Detection SHALL be a field read rather than a heuristic: version 1 already declared `format_version: 1` in its header, so no bundle this service has ever produced is unversioned.

A version 1 bundle SHALL be read with no blob table — a `blob` record inside one SHALL be rejected with `400` naming the line — and SHALL be treated as the `full` mode with no omitted payload fields, which is what it is.

A bundle of either version whose `header` carries no `platform` SHALL be imported as `platform` `dragncards`, because every bundle written before this change came from the only platform that existed. The absence SHALL NOT be a validation failure, and the import SHALL write the same events and snapshots it wrote before this change.

The service SHALL always write the current version on export. A bundle of the current version presented to an older service SHALL be refused by that service's existing unsupported-version check, so neither direction of a version mismatch is silent.

#### Scenario: A version 1 bundle still imports

- **WHEN** a bundle declaring format version 1 is imported
- **THEN** the service SHALL accept it, write its events and snapshots verbatim, and report the mode `full`

#### Scenario: A bundle written before the platform field imports as dragncards

- **WHEN** a bundle whose `header` carries no `platform` is imported
- **THEN** the service SHALL accept it, SHALL write its events and snapshots under `platform` `dragncards`, and SHALL NOT answer a validation error

#### Scenario: A version 1 bundle cannot contain blobs

- **WHEN** a bundle declaring format version 1 contains a `blob` record
- **THEN** the service SHALL answer `400` naming the line, because version 1 did not define that record kind

## ADDED Requirements

### Requirement: Platform is a stored column, defaulted, and part of every game-scoped key

`platform` SHALL be a real column on both `events` and `snapshots`, declared `NOT NULL DEFAULT 'dragncards'`, and SHALL NOT be carried only inside `payload_json`. A payload-only discriminator cannot be indexed, cannot participate in a unique constraint, and is silently discarded by a commit path that enumerates its columns, which is exactly what this discriminator must not be.

The column SHALL be joined into every uniqueness and lookup structure that keys on `game_id` today:

- `uq_events_game_idempotency` SHALL cover `(game_id, platform, idempotency_key)`;
- `uq_events_game_seq` SHALL cover `(game_id, platform, seq)`;
- `uq_snapshots_game_seq` SHALL cover `(game_id, platform, snapshot_at_seq)`;
- the `game_id` index on `events` and the `game_id` index on `snapshots` SHALL each lead with the columns a game-scoped read filters on, so a per-game read remains a single index lookup and does not degrade into a scan.

The `NOT NULL DEFAULT` SHALL make every row written before this change read as `dragncards` with no backfill step and no behaviour change for an existing recording.

#### Scenario: An existing row reads as dragncards without a backfill

- **WHEN** the migration is applied to a database holding events and snapshots written before this change
- **THEN** every existing row SHALL read `platform` as `dragncards`
- **AND** no backfill statement SHALL be required for them to do so

#### Scenario: The constraints admit two platforms for one identifier

- **WHEN** an event with `seq` 1 exists for a `game_id` on `dragncards` and an event with `seq` 1 is committed for the same `game_id` on `marvel-lcg`
- **THEN** both rows SHALL be stored
- **AND** the unique constraints SHALL still refuse a second `seq` 1 within either platform

#### Scenario: A snapshot at the same sequence exists per platform

- **WHEN** a snapshot at `snapshot_at_seq` 10 exists for a `game_id` on one platform and a snapshot at `snapshot_at_seq` 10 is stored for the same `game_id` on the other
- **THEN** both SHALL be stored, and a second snapshot at `snapshot_at_seq` 10 on either platform SHALL still be refused

#### Scenario: A per-game read is still one index lookup

- **WHEN** a game's events or snapshots are read
- **THEN** the read SHALL be served through the platform-scoped `game_id` index
- **AND** SHALL NOT degrade to a table scan because the filter gained a column

### Requirement: A snapshot and a restore never cross platforms

Every snapshot SHALL belong to the platform of the game it was taken from, and a restore SHALL only ever load a base and replay events **within one platform**. The history-service SHALL select a restore's full-state base, its replay range, and its snapshots from the target game's own `platform`, and SHALL NOT consider a row of another platform to be a candidate base or a replayable event, even when it shares the `game_id`.

A restore SHALL refuse, with a clear error and without mutating anything, when the game-service session it is asked to restore into runs a different platform than the recorded history it is restoring — the same way it already refuses a session running the wrong plugin. A marvel-lcg board cannot be pushed into a DragnCards room and a DragnCards state document cannot be pushed into a marvel-lcg engine; a partly-applied cross-platform restore would leave a live session in a state nothing recorded.

Cross-platform migration of a game is not supported: an import SHALL preserve the bundle's platform and SHALL NOT re-label a recording onto a different platform.

#### Scenario: A restore reads only its own platform's rows

- **WHEN** a game identifier holds recorded history on both platforms and a restore is requested for one of them
- **THEN** the base state, the replayed events and the snapshots SHALL all be drawn from that platform's rows only

#### Scenario: A restore into a session of the wrong platform is refused

- **WHEN** a restore is asked to load a `marvel-lcg` recording into a supplied game-service session whose platform is `dragncards`
- **THEN** the service SHALL refuse with an error naming the platform mismatch
- **AND** SHALL NOT apply any state, SHALL NOT replay any event, and SHALL NOT delete the supplied session

#### Scenario: An import does not re-label a recording's platform

- **WHEN** a bundle exported from a `marvel-lcg` game is imported
- **THEN** the imported rows SHALL carry `platform` `marvel-lcg`
- **AND** the import SHALL provide no way to write them under a different platform

### Requirement: The platform migration is dialect-paired and safe for the shared runner

The schema change SHALL be delivered as the next migration version in BOTH dialects the shared runner discovers — `0002_<name>.postgresql.sql` and `0002_<name>.sqlite.sql` — because the runner globs `*.sql`, takes the pre-`.` prefix as the version, and sorts lexicographically, so a zero-padded pair is what makes the ordering and the dialect selection work.

Neither file SHALL contain a semicolon inside a string literal or inside a `DO $$ … $$` block, because the shared runner splits a script on a naive `;` and would execute the fragments as separate statements.

The SQLite variant SHALL use the table-rebuild pattern already used by eval-service's `0002_target_player.sqlite.sql` — create the new table with the widened constraints, copy the rows, drop the old table, rename — because SQLite cannot drop or alter a constraint in place.

Both variants SHALL be idempotent under re-application in the same way the existing migrations are, and applying them to a database holding existing recordings SHALL leave every existing event and snapshot readable, in the same `seq` order, under `platform` `dragncards`.

#### Scenario: Both dialects are present at the same version

- **WHEN** the migration directory is listed
- **THEN** it SHALL contain `0002_<name>.postgresql.sql` and `0002_<name>.sqlite.sql`
- **AND** the runner SHALL select the file matching the connected dialect

#### Scenario: A statement is not split in the middle

- **WHEN** either migration file is read by the shared runner's statement splitter
- **THEN** every produced fragment SHALL be a complete, executable statement
- **AND** no fragment SHALL be produced by a semicolon inside a string literal or a `DO $$ … $$` block

#### Scenario: SQLite rebuilds the table to widen a constraint

- **WHEN** the SQLite migration widens a unique constraint
- **THEN** it SHALL create the replacement table, copy every row, drop the original, and rename the replacement
- **AND** the recorded events and snapshots SHALL read back identically afterwards

#### Scenario: Applying the migration preserves an existing recording

- **WHEN** the migration is applied to a database holding a recorded DragnCards game
- **THEN** that game's events SHALL still read in the same gap-free `seq` order with the same payloads
- **AND** they SHALL read `platform` `dragncards`
