## MODIFIED Requirements

### Requirement: Human-readable export of a game's recorded history

The history-service SHALL expose a read endpoint that returns a game's complete recorded history — every stored event and every stored snapshot — as a single human-readable file.

The bundle format SHALL be NDJSON: one self-contained JSON object per line, with object keys serialized in sorted order so that two exports of the same history differ only where the history differs. The records SHALL appear in exactly this order: one `header` record, then `blob`, `event` and `snapshot` records, then one `footer` record. `event` records SHALL appear in ascending `seq` and `snapshot` records SHALL appear after every `event` in ascending `snapshot_at_seq`. A `blob` record SHALL appear before the first record that references it and MAY appear anywhere between the header and the footer, so that a bundle can be both written and read in one pass without buffering.

The format SHALL be identified as version 2. The `header` SHALL carry the format identifier, the format version, the source `game_id`, the game's recorded `plugin_name` (null when the game recorded none), the export timestamp, the export mode, the payload fields that mode omits, and the event, snapshot and blob counts. The `footer` SHALL repeat the event, snapshot and blob counts. An `event` record SHALL carry `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset`. A `snapshot` record SHALL carry `snapshot_at_seq`, `snapshot`, and `created_at`. A `blob` record SHALL carry its identifier, its value, and the path at which that value was first encountered. No record SHALL carry a `game_id`, because the target game is chosen at import time. Every field the format defines SHALL be written on export and read on import; the format SHALL NOT define reserved or unused fields.

The response SHALL be served with the NDJSON media type and a `Content-Disposition: attachment` filename derived from the `game_id` and the mode. The export SHALL be streamed rather than materialized in full, so that a game whose every event embeds a complete board state does not have to fit in memory.

The export SHALL read only the history store. It SHALL NOT include service configuration, environment values, provider credentials, MCP registry headers, or any other data outside the stored events and snapshots.

The bundle SHALL NOT carry a derived round number, phase name, or other display metadata, because DragnCards `roundNumber` counts completed rounds and a `game-service` event embeds the state after its action, making a round label a derivation that belongs to the reader rather than the format.

Exporting a game with no recorded history SHALL return a bundle consisting of a `header` and a `footer` with zero counts, consistent with the read endpoints' treatment of unknown games; it SHALL NOT be an error.

#### Scenario: Export a recorded game

- **WHEN** a client requests the export of a game that has recorded events and snapshots
- **THEN** the service SHALL answer with an NDJSON attachment whose first line is a `header` naming the format, its version, the game, its plugin, the mode and the counts; whose next lines are the `blob` records together with one `event` per stored event in ascending `seq` followed by one `snapshot` per stored snapshot in ascending `snapshot_at_seq`; and whose last line is a `footer` repeating the counts

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

### Requirement: Repeated values are carried once and referenced

The bundle format SHALL carry any repeated value once, as a `blob` record, and reference it from every place it occurs, because a recorded game is overwhelmingly repetition: on a measured 124-event game, the DragnCards delta log is re-shipped in full by every state event, every agent move re-ships the whole conversation that preceded it, and the plugin's DragnLang functions, automation lists, rules and layout are byte-identical on every state.

While a record's `payload` (for an `event`) or `snapshot` (for a `snapshot`) is serialized, any object or array whose serialization reaches a fixed size threshold SHALL be replaced by a reference of the form `{"$ref": "<blob id>"}`, and the value itself SHALL be emitted as a `blob` record on an earlier line. Extraction SHALL be by size alone and SHALL NOT depend on field names, so that the format needs no knowledge of DragnCards and does not have to be revised when a recorded state gains a field.

A reference SHALL name only a blob defined on an earlier line. Consequently a bundle can be read in one forward pass, and a reference cycle cannot be expressed.

A blob's value MAY itself contain references to earlier blobs, so that a value which is repeated only in part is still carried once.

Because an object in a recorded payload could genuinely have `$ref` as its only key, the format SHALL escape any object whose sole key is `$ref` or `$literal` as `{"$literal": <the object>}`, and reading SHALL unwrap it. This SHALL nest, so that a payload containing an escape marker round-trips unchanged.

The service SHALL reject a bundle whose `blob` records do not resolve: a reference to an unknown identifier, a reference to a blob defined on a later line, a duplicate blob identifier, and a footer `blob_count` that disagrees with the blobs read SHALL each be a `400` naming the offending line.

#### Scenario: A repeated value is carried once

- **WHEN** a game whose events share a large identical value is exported
- **THEN** the bundle SHALL contain that value in exactly one `blob` record, and each event that carried it SHALL carry a reference to that record instead

#### Scenario: A partially repeated value is still shared

- **WHEN** a value is an array that grows by appending, so that each occurrence contains every earlier occurrence's elements
- **THEN** the bundle SHALL carry each distinct element once and each occurrence SHALL reference the elements it shares with the ones before it

#### Scenario: An escape marker in real data round-trips

- **WHEN** a stored payload contains an object whose only key is `$ref`, or one whose only key is `$literal`
- **THEN** exporting and re-importing that game SHALL reproduce the payload exactly, and the reference resolver SHALL NOT treat the payload's own object as a reference

#### Scenario: A dangling reference is rejected

- **WHEN** an imported bundle contains a reference to a blob identifier that no earlier line defines
- **THEN** the service SHALL answer `400` naming the line and the identifier, and SHALL import nothing

### Requirement: Export modes select whether prompt material is included

The export endpoint SHALL accept a mode of `full` or `minimal`, defaulting to `full`, and SHALL record the chosen mode in the bundle header together with the list of payload fields that mode omits.

`full` SHALL be lossless: every stored event and every stored snapshot, every field verbatim. Exporting, importing and re-exporting in `full` mode SHALL reproduce the bundle.

`minimal` SHALL carry the same records as `full` — the same events with the same `seq` values, and the same snapshots — and SHALL omit only the LLM prompt material, which is the `conversation_context` field of an `agent_move` payload. Every other field SHALL be carried, including an agent move's `reasoning`, `intended_action` and `arguments`, every user prompt, every evaluation, and every recorded state.

A mode SHALL NOT be permitted to drop whole events, because event `seq` is required to be gap-free and ascending from 1 and a bundle with holes could not be imported; and because an agent's recorded moves are the substance of a recorded game rather than prompt material.

An omitted field SHALL be omitted by **absence**: the key SHALL NOT be present, and SHALL NOT be written as an empty value. This is what distinguishes a minimally exported game from a fully exported game whose conversations happened to be empty.

The mode SHALL describe the export operation rather than a permanent property of the game. A game imported from a minimal bundle genuinely holds no captured conversation, so exporting it in `full` mode SHALL report `full` and carry no `conversation_context`, which states that the recording has no prompts rather than that its prompts were empty.

Import SHALL reject a bundle whose header declares `full` while also declaring omitted fields, because the two statements contradict one another.

#### Scenario: A minimal export omits exactly the prompt material

- **WHEN** a game with recorded agent moves is exported in `minimal` mode
- **THEN** no `agent_move` record SHALL carry a `conversation_context` key, every other payload field of every record SHALL match the `full` export, and the header SHALL declare the mode `minimal` and name `conversation_context` as omitted

#### Scenario: A full export declares itself lossless

- **WHEN** a game is exported without a mode, or with `full`
- **THEN** the header SHALL declare the mode `full` and an empty list of omitted fields

#### Scenario: A minimal bundle is recognisable after import

- **WHEN** a minimal bundle is imported
- **THEN** the import response SHALL report the mode the bundle declared, and the imported `agent_move` events SHALL have no `conversation_context` key rather than an empty one

#### Scenario: An unknown mode is refused

- **WHEN** an export is requested with a mode that is neither `full` nor `minimal`
- **THEN** the service SHALL reject the request rather than falling back to a default

### Requirement: Validated, atomic, non-destructive import of a history bundle

The history-service SHALL expose a write endpoint that reads an NDJSON history bundle and persists it as one game's recorded history.

The import target SHALL be chosen as follows: the `game_id` supplied by the caller when one is supplied; otherwise a freshly minted identifier when the caller asks for a new one; otherwise the `game_id` recorded in the bundle's `header`. A supplied target `game_id` SHALL be constrained at the route boundary by the same rule that constrains a `game_id` in a path. Supplying both an explicit `game_id` and a request for a new one SHALL be rejected with `400`, because they are two answers to one question. When the target already has recorded history the service SHALL reject the request with `409` and a message naming the conflict and the alternatives, and SHALL NOT write, merge, or overwrite anything. Import SHALL NOT be a way to modify an existing game's history; placing an imported game onto a live session remains the restore endpoint's job.

The service SHALL NOT default an import onto a freshly minted identifier, because doing so would turn the conflict into a silent copy and remove the only way to re-import a bundle onto its original identifier after that game's history was deleted.

Every record SHALL be validated against the bundle schemas before it reaches the database. The import SHALL be atomic: a bundle that fails validation at any point SHALL leave no events and no snapshots behind. Validation failures SHALL be reported with `400` and a message that identifies the offending line and the reason. The service SHALL reject:

- a line that is not parseable JSON, or that parses to something other than a JSON object;
- a first record that is not a `header`, a `format` that is not this format, or a `format_version` the service does not support;
- an unknown record `kind`;
- a missing `footer`, footer counts that disagree with the records actually read, or content after the `footer`;
- `seq` values that are not strictly ascending and gap-free from 1;
- a `snapshot` record before the last `event` record, a `snapshot_at_seq` above the last imported `seq`, or `snapshot_at_seq` values that do not ascend;
- an `actor` outside the envelope's known actors, or a field longer than the column that stores it;
- a bundle declaring zero events;
- a duplicate `idempotency_key` or `seq` within the bundle;
- a `header` declaring the `full` mode together with a non-empty list of omitted payload fields.

Records SHALL be deserialized as plain JSON only. The service SHALL NOT evaluate, unpickle, or otherwise reconstruct arbitrary objects from a bundle, and SHALL discard unknown top-level keys on a record rather than carrying them into storage.

An accepted import SHALL preserve `seq`, `event_id`, `idempotency_key`, `occurred_at`, and `recorded_at` verbatim, so that the imported game reads back identically to the game it was exported from rather than being re-sequenced or re-timestamped. The response SHALL report the target `game_id`, the source `game_id`, the bundle's mode, the number of events and snapshots written, the imported `seq` range, and how many imported events still mention the source `game_id` in their payload.

#### Scenario: Round trip reproduces the history and reconstructs the same state

- **WHEN** a recorded game is exported and the bundle is imported under a different `game_id`
- **THEN** the imported game's events SHALL match the original's `seq`, `event_id`, `envelope_version`, `actor`, `event_type`, `payload`, `occurred_at`, `recorded_at`, `idempotency_key`, and `producer_offset`, its snapshots SHALL match the original's, and restoring the imported game to its last `seq` SHALL load the same game document and replay the same actions as restoring the original to that `seq`

#### Scenario: Import defaults the target to the bundle's own game id

- **WHEN** a bundle is imported without a target `game_id`, without asking for a new one, and no game with the bundle's `game_id` has recorded history
- **THEN** the history SHALL be written under the `game_id` recorded in the bundle's `header`

#### Scenario: Import under a freshly minted id never conflicts

- **WHEN** a bundle exported from a game that still has its history is imported asking for a new identifier
- **THEN** the service SHALL mint an identifier that no game holds, write the history under it, and report both it and the source `game_id`, rather than answering `409`

#### Scenario: Naming a target and asking for a new one is refused

- **WHEN** an import supplies both an explicit target `game_id` and a request for a freshly minted one
- **THEN** the service SHALL answer `400` naming both, and SHALL import nothing

#### Scenario: Import refuses to overwrite an existing game

- **WHEN** a bundle is imported into a `game_id` that already has recorded history
- **THEN** the service SHALL answer `409` with a message naming the conflict and the alternatives, and that game's stored events and snapshots SHALL be unchanged

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

Because the format carries repeated values once and references them, a small bundle can describe an arbitrarily large expansion — a blob that references two earlier blobs, repeated, grows exponentially in the size of the file. The service SHALL therefore also enforce the ceiling against the *expanded* size of what a bundle describes: each blob's expanded size SHALL be accounted for as it is read, as its own size plus the expanded size of every blob it references, and a bundle whose expansion exceeds the ceiling SHALL be refused with `413` before the expansion is materialized.

#### Scenario: An oversized bundle is refused

- **WHEN** an import body exceeds the configured ceiling
- **THEN** the service SHALL answer `413` with the "Request body too large" detail, and the target game SHALL have no stored events

Reading a bundle also means walking structure the file chose, so the service SHALL bound how deeply a record's or a blob's value may nest and SHALL refuse a deeper one with `400` naming the line. The bound SHALL be enforced on the reading side alone: nothing deeper can then enter the store, so the export side, which only walks what the store already holds, needs no bound of its own. The bound SHALL be far above what a recorded DragnCards state nests and far below the interpreter's own recursion limit, so that exceeding it is a stated refusal rather than a crash.

#### Scenario: A reference bomb is refused before it is expanded

- **WHEN** an import body within the ceiling describes, through nested blob references, an expansion that exceeds the ceiling
- **THEN** the service SHALL answer `413`, SHALL NOT allocate the expansion, and the target game SHALL have no stored events

#### Scenario: An excessively nested value is refused

- **WHEN** an imported bundle carries a record or blob whose value nests deeper than the configured bound
- **THEN** the service SHALL answer `400` naming the line and the bound, and the target game SHALL have no stored events

## ADDED Requirements

### Requirement: Previously exported bundles remain importable

The history-service SHALL accept bundles declaring format version 1 as well as format version 2, so that a bundle a user exported before this capability existed still imports.

Detection SHALL be a field read rather than a heuristic: version 1 already declared `format_version: 1` in its header, so no bundle this service has ever produced is unversioned.

A version 1 bundle SHALL be read with no blob table — a `blob` record inside one SHALL be rejected with `400` naming the line — and SHALL be treated as the `full` mode with no omitted payload fields, which is what it is.

The service SHALL always write the current version on export. A bundle of the current version presented to an older service SHALL be refused by that service's existing unsupported-version check, so neither direction of a version mismatch is silent.

#### Scenario: A version 1 bundle still imports

- **WHEN** a bundle declaring format version 1 is imported
- **THEN** the service SHALL accept it, write its events and snapshots verbatim, and report the mode `full`

#### Scenario: A version 1 bundle may not contain blobs

- **WHEN** a bundle declaring format version 1 contains a `blob` record
- **THEN** the service SHALL answer `400` naming the line, because version 1 did not define that record kind

### Requirement: An empty captured conversation is not a restored agent context

When the agent event a restore selects carries no captured conversation, the history-service SHALL report the agent context as **not** restored, together with a human-readable reason, and SHALL NOT ask the orchestrator to seed a session with an empty conversation. The game-state layer of the restore SHALL still complete, exactly as it does when no agent event exists at all.

This is the failure mode a `minimal` bundle would otherwise create. The orchestrator accepts an empty conversation and answers success, so forwarding one would report a rebuilt agent context where nothing was rebuilt — an agent resumed with no memory of the game, described as an agent restored to the moment. Agent event types known to carry no conversation are already excluded when the event is selected; this closes the remaining case, which is an event type that normally carries one in a recording that does not.

#### Scenario: Restoring a minimally imported game reports the missing conversation

- **WHEN** a game imported from a `minimal` bundle is restored to a moment at or after one of its agent moves
- **THEN** the game state SHALL be restored and the same events replayed as for the fully exported game, and the response SHALL report that the agent conversation was not rebuilt, with a reason naming the `minimal` export as a cause

### Requirement: An imported game's remaining references to its source are reported

An imported game's payloads are recorded evidence and SHALL NOT be rewritten when the import target differs from the `game_id` the bundle came from. A captured conversation is the verbatim record of what a model was shown and what it emitted, and is the input the stored evaluation verdicts judged; rewriting an identifier inside it would produce a transcript no model emitted and would invalidate those verdicts. No reader dereferences a `game_id` found inside a payload — the restore path addresses its target by the route identifier — so a stale reference is a provenance question rather than a broken pointer.

Because a stale reference is nonetheless a thing a reader can be misled by, it SHALL NOT be silent. The import response SHALL report how many imported events contain the source `game_id` somewhere in their payload. The count SHALL be zero when the target and the source are the same identifier, because in that case the references are current rather than stale.

#### Scenario: References to the source game are counted

- **WHEN** a bundle whose payloads mention its own `game_id` is imported under a different identifier
- **THEN** the service SHALL write those payloads unchanged and SHALL report the number of events that mention the source identifier

#### Scenario: Importing onto the source identifier reports no stale references

- **WHEN** a bundle is imported under the same `game_id` its header declares
- **THEN** the reported count of events mentioning the source identifier SHALL be zero
