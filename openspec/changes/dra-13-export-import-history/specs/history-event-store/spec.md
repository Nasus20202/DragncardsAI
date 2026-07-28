## ADDED Requirements

### Requirement: Human-readable export of a game's recorded history

The history-service SHALL expose a read endpoint that returns a game's complete recorded history — every stored event and every stored snapshot — as a single human-readable file.

The bundle format SHALL be NDJSON: one self-contained JSON object per line, with object keys serialized in sorted order so that two exports of the same history differ only where the history differs. The records SHALL appear in exactly this order: one `header` record, then one `event` record per stored event in ascending `seq`, then one `snapshot` record per stored snapshot in ascending `snapshot_at_seq`, then one `footer` record.

The `header` SHALL carry the format identifier, the format version, the source `game_id`, the game's recorded `plugin_name` (null when the game recorded none), the export timestamp, and the event and snapshot counts. The `footer` SHALL repeat the event and snapshot counts. An `event` record SHALL carry `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset`. A `snapshot` record SHALL carry `snapshot_at_seq`, `snapshot`, and `created_at`. No record SHALL carry a `game_id`, because the target game is chosen at import time. Every field the format defines SHALL be written on export and read on import; the format SHALL NOT define reserved or unused fields.

The response SHALL be served with the NDJSON media type and a `Content-Disposition: attachment` filename derived from the `game_id`. The export SHALL be streamed rather than materialized in full, so that a game whose every event embeds a complete board state does not have to fit in memory.

The export SHALL read only the history store. It SHALL NOT include service configuration, environment values, provider credentials, MCP registry headers, or any other data outside the stored events and snapshots.

The bundle SHALL NOT carry a derived round number, phase name, or other display metadata, because DragnCards `roundNumber` counts completed rounds and a `game-service` event embeds the state after its action, making a round label a derivation that belongs to the reader rather than the format.

Exporting a game with no recorded history SHALL return a bundle consisting of a `header` and a `footer` with zero counts, consistent with the read endpoints' treatment of unknown games; it SHALL NOT be an error.

#### Scenario: Export a recorded game

- **WHEN** a client requests the export of a game that has recorded events and snapshots
- **THEN** the service SHALL answer with an NDJSON attachment whose first line is a `header` naming the format, its version, the game, its plugin, and the counts; whose next lines are one `event` per stored event in ascending `seq` followed by one `snapshot` per stored snapshot in ascending `snapshot_at_seq`; and whose last line is a `footer` repeating the counts

#### Scenario: Exported events are verbatim and carry no game id

- **WHEN** a bundle's `event` records are read back
- **THEN** each SHALL carry the stored `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset` unchanged, and SHALL NOT carry a `game_id`

#### Scenario: Bundle lines are key-sorted so exports diff cleanly

- **WHEN** any line of a bundle is parsed
- **THEN** its object keys SHALL be in sorted order

#### Scenario: Exporting a game with no history

- **WHEN** a client requests the export of a `game_id` that has no recorded history
- **THEN** the service SHALL answer with a `header` and a `footer` declaring zero events and zero snapshots, and SHALL NOT return an error

#### Scenario: Export carries no credential

- **WHEN** a bundle is inspected for secrets
- **THEN** it SHALL contain no API key, bearer token, authorization header, database credential, or other value drawn from service configuration or environment

### Requirement: Validated, atomic, non-destructive import of a history bundle

The history-service SHALL expose a write endpoint that reads an NDJSON history bundle and persists it as one game's recorded history.

The import target SHALL be the `game_id` supplied by the caller when one is supplied, and otherwise the `game_id` recorded in the bundle's `header`. A supplied target `game_id` SHALL be constrained at the route boundary by the same rule that constrains a `game_id` in a path. When the target already has recorded history the service SHALL reject the request with `409` and a message naming the conflict, and SHALL NOT write, merge, or overwrite anything. Import SHALL NOT be a way to modify an existing game's history; placing an imported game onto a live session remains the restore endpoint's job.

Every record SHALL be validated against the bundle schemas before it reaches the database. The import SHALL be atomic: a bundle that fails validation at any point SHALL leave no events and no snapshots behind. Validation failures SHALL be reported with `400` and a message that identifies the offending line and the reason. The service SHALL reject:

- a line that is not parseable JSON, or that parses to something other than a JSON object;
- a first record that is not a `header`, a `format` that is not this format, or a `format_version` the service does not support;
- an unknown record `kind`;
- a missing `footer`, footer counts that disagree with the records actually read, or content after the `footer`;
- `seq` values that are not strictly ascending and gap-free from 1;
- a `snapshot` record before the last `event` record, a `snapshot_at_seq` above the last imported `seq`, or `snapshot_at_seq` values that do not ascend;
- an `actor` outside the envelope's known actors, or a field longer than the column that stores it;
- a bundle declaring zero events;
- a duplicate `idempotency_key` or `seq` within the bundle.

Records SHALL be deserialized as plain JSON only. The service SHALL NOT evaluate, unpickle, or otherwise reconstruct arbitrary objects from a bundle, and SHALL discard unknown top-level keys on a record rather than carrying them into storage.

An accepted import SHALL preserve `seq`, `event_id`, `idempotency_key`, `occurred_at`, and `recorded_at` verbatim, so that the imported game reads back identically to the game it was exported from rather than being re-sequenced or re-timestamped. The response SHALL report the target `game_id`, the source `game_id`, the number of events and snapshots written, and the imported `seq` range.

#### Scenario: Round trip reproduces the history and reconstructs the same state

- **WHEN** a recorded game is exported and the bundle is imported under a different `game_id`
- **THEN** the imported game's events SHALL match the original's `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset`, its snapshots SHALL match the original's, and restoring the imported game to its last `seq` SHALL load the same game document and replay the same actions as restoring the original to that `seq`

#### Scenario: Import defaults the target to the bundle's own game id

- **WHEN** a bundle is imported without a target `game_id` and no game with the bundle's `game_id` has recorded history
- **THEN** the history SHALL be written under the `game_id` recorded in the bundle's `header`

#### Scenario: Import refuses to overwrite an existing game

- **WHEN** a bundle is imported into a `game_id` that already has recorded history
- **THEN** the service SHALL answer `409` with a message naming the conflict, and that game's stored events and snapshots SHALL be unchanged

#### Scenario: A malformed bundle imports nothing

- **WHEN** a bundle whose records are valid up to some line becomes invalid at a later line
- **THEN** the service SHALL answer `400` naming that line and the reason, and the target game SHALL have no stored events and no stored snapshots

#### Scenario: A truncated bundle is detected

- **WHEN** a bundle ends without a `footer`, or its `footer` counts disagree with the records read
- **THEN** the service SHALL answer `400` reporting the discrepancy, and SHALL NOT import a partial history

#### Scenario: A gap in the sequence is rejected

- **WHEN** a bundle's `event` records do not run strictly ascending and gap-free from 1
- **THEN** the service SHALL answer `400` naming the expected and the received `seq`

#### Scenario: An unknown actor is rejected

- **WHEN** a bundle carries an `event` record whose `actor` is not one of the envelope's known actors
- **THEN** the service SHALL answer `400` and import nothing

#### Scenario: An empty bundle is rejected

- **WHEN** a bundle declares and contains zero events
- **THEN** the service SHALL answer `400` stating there is nothing to import

### Requirement: Bounded import body size

The history-service SHALL refuse an import body larger than a configured ceiling, expressed in bytes and settable by environment variable, and SHALL answer such a request with `413` and the same response body the agent-orchestrator's request-body cap uses. The ceiling SHALL be enforced both against a declared `Content-Length` before the body is read and against the running total of bytes actually received, so that a missing or understated `Content-Length` does not raise the effective limit. A refused body SHALL import nothing.

#### Scenario: An oversized bundle is refused

- **WHEN** an import body exceeds the configured ceiling
- **THEN** the service SHALL answer `413` with the "Request body too large" detail, and the target game SHALL have no stored events
