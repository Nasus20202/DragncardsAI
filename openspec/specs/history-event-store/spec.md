# history-event-store Specification

## Purpose
Keep an authoritative, append-only record of what happened in every game, so that a game can be
reconstructed, reviewed, and judged after the fact rather than only observed live. A dedicated
`history-service` ingests events emitted by `game-service` and the orchestrator, stores them with
periodic game-state snapshots in its own PostgreSQL database, and replays them on demand. It is the
single source of truth for game history: nothing about a played game is retained in process memory,
and consumers such as `game-history-ui` and `agent-move-evaluation` read from here rather than
keeping their own copies. Ingest isolates per-entry failures so one bad event cannot cost a game its
log.
## Requirements
### Requirement: History service boundary and persistence
The system SHALL provide a dedicated `history-service` (Python/FastAPI) that persists a per-game append-only event log and periodic game-state snapshots in a dedicated PostgreSQL database, and SHALL NOT retain game history in process memory.

#### Scenario: History service uses dedicated persistent storage
- **WHEN** the history-service stores an ingested event or a game-state snapshot
- **THEN** the history-service SHALL persist it in its dedicated PostgreSQL database and SHALL NOT keep the event log or snapshots only in process memory

#### Scenario: Health and readiness without secrets
- **WHEN** a client requests the history-service health or readiness endpoint
- **THEN** the history-service SHALL report API, PostgreSQL, and Valkey ingestion readiness and SHALL NOT expose any secret values

### Requirement: Versioned event envelope
The history-service SHALL define a versioned event envelope containing an envelope version, a game correlation identifier (`game_id`), an actor of `agent`, `game-service`, or `evaluator`, an event type, a JSON payload, a producer-supplied occurrence timestamp, an idempotency key, and a history-assigned monotonic per-game sequence number and recorded timestamp.

#### Scenario: Accept a well-formed envelope
- **WHEN** a producer submits an event envelope containing `envelope_version`, `game_id`, `actor`, `event_type`, `payload`, `occurred_at`, and `idempotency_key`
- **THEN** the history-service SHALL accept the envelope and SHALL assign a monotonic per-game `seq` and a `recorded_at` timestamp before persisting it

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
The history-service SHALL store events in a strict, gap-free, monotonically increasing order per `game_id`, assigning the sequence number authoritatively at commit time rather than trusting producer-supplied ordering.

#### Scenario: Sequence numbers are gap-free and increasing per game
- **WHEN** multiple events for the same `game_id` are committed
- **THEN** each committed event SHALL receive a `seq` exactly one greater than the previously committed event for that `game_id`, starting at 1

#### Scenario: Out-of-order delivery is ordered authoritatively
- **WHEN** events for the same `game_id` arrive in an order different from their `occurred_at` timestamps
- **THEN** the history-service SHALL assign `seq` in commit order and SHALL return events ordered by `seq` on retrieval

#### Scenario: Independent ordering across games
- **WHEN** events for two different `game_id` values are committed interleaved
- **THEN** each `game_id` SHALL maintain its own independent gap-free `seq` series

### Requirement: Dual-source idempotent ingestion
The history-service SHALL ingest events from both producers over a shared Valkey stream consumer group as the primary path and SHALL accept the same envelope through an authenticated HTTP backfill endpoint, and SHALL guarantee that at-least-once duplicate deliveries are stored at most once per `game_id`. On the stream path the history-service SHALL isolate per-entry commit failures so a transient failure on one entry neither aborts the rest of the batch nor loses that entry, and SHALL recover pending stream entries (from a failed commit or a crashed consumer) by reclaiming and re-processing them through the same idempotent commit path.

#### Scenario: Ingest from the Valkey stream
- **WHEN** a producer publishes an event envelope to the shared history ingestion Valkey stream
- **THEN** the history-service SHALL consume it through its consumer group, persist it, and acknowledge the stream entry

#### Scenario: Ingest from the HTTP backfill endpoint
- **WHEN** a client submits an event envelope to the history-service HTTP ingestion endpoint for a `game_id`
- **THEN** the history-service SHALL persist the event using the same envelope contract and ordering rules as the Valkey path

#### Scenario: Duplicate delivery is stored once
- **WHEN** the same envelope (identical `game_id` and `idempotency_key`) is delivered more than once
- **THEN** the history-service SHALL persist it exactly once, SHALL NOT consume an additional `seq` for the duplicate, and SHALL acknowledge the duplicate delivery

#### Scenario: A transient commit failure does not lose other entries in the batch
- **WHEN** committing one entry of a stream batch fails transiently (e.g. a database deadlock or connection blip) while other entries in the same batch commit successfully
- **THEN** the history-service SHALL persist and acknowledge the successful entries, SHALL NOT abort processing the remainder of the batch, and SHALL leave the failed entry un-acknowledged (pending) rather than dropping it

#### Scenario: Stale pending entries are reclaimed and committed
- **WHEN** a stream entry has remained pending and un-acknowledged for longer than the configured minimum idle time (because its consumer crashed or a prior commit failed)
- **THEN** the history-service SHALL reclaim it onto a live consumer and re-process it through the idempotent commit path, persisting it exactly once (never consuming an additional `seq` if it was already committed) and acknowledging it

### Requirement: Rating-ready captured data
The history-service SHALL preserve, for each agent move, the agent's intended action, its reasoning/context, the full conversation context the agent had at that decision, and the resulting game state and game status from game-service, so that an automated rating capability can later score play and a restore can rebuild the agent's situation without re-instrumenting the producers.

#### Scenario: Agent move event retains decision context
- **WHEN** the history-service stores an `agent` move/decision event
- **THEN** the stored payload SHALL retain the intended action and the agent's reasoning/context as supplied by the orchestrator

#### Scenario: Agent move event retains full conversation context
- **WHEN** the history-service stores an `agent` move/decision event
- **THEN** the stored payload SHALL retain the full conversation context (ordered message, tool-call, and tool-result history) the agent had at that decision, sufficient to rehydrate an orchestrator session at that point

#### Scenario: Game-state event retains status and outcome
- **WHEN** the history-service stores a `game-service` game-state event
- **THEN** the stored payload SHALL retain the resulting game-state representation and the game status (such as `in progress`, `win`, or `loss`)

### Requirement: Periodic game-state snapshots
The history-service SHALL checkpoint full game-state snapshots per `game_id` on a configurable cadence based on event count and elapsed time, storing each snapshot together with the `seq` it corresponds to.

#### Scenario: Snapshot taken after the configured event count
- **WHEN** the number of events committed for a `game_id` since the last snapshot reaches the configured count threshold
- **THEN** the history-service SHALL obtain a full game-state snapshot from game-service and SHALL store it with its corresponding `seq`

#### Scenario: Snapshot taken after the configured interval
- **WHEN** the configured maximum interval elapses since the last snapshot for an active `game_id` with new events
- **THEN** the history-service SHALL obtain and store a full game-state snapshot with its corresponding `seq`

#### Scenario: Snapshot stored in the documented snapshot format
- **WHEN** the history-service stores a snapshot
- **THEN** the stored snapshot SHALL use the game-service versioned snapshot document containing the schema version, plugin identity, and game payload

### Requirement: Event and snapshot retrieval
The history-service SHALL expose read APIs to list a game's events in `seq` order with paging and to list a game's snapshots, for timeline consumption.

#### Scenario: List events for a game in order
- **WHEN** a client requests the events for a `game_id`
- **THEN** the history-service SHALL return the events ordered by ascending `seq` with their envelope fields

#### Scenario: List snapshots for a game
- **WHEN** a client requests the snapshots for a `game_id`
- **THEN** the history-service SHALL return the stored snapshots with their `seq` and timestamps

#### Scenario: Retrieve for an unknown game
- **WHEN** a client requests events or snapshots for a `game_id` with no stored history
- **THEN** the history-service SHALL return an empty result rather than an error

### Requirement: Restore to a past moment

The history-service SHALL restore a game to an arbitrary past moment identified by a target `seq` by reconstructing both the game state (loading the densest full-state base at or before the target into a game-service session and replaying the subsequent game-mutating events forward up to and including the target `seq`) and the agent's conversation context as of the target `seq` (loaded into an orchestrator session bound to the restored game), so the agent faces an identical, replayable situation.

The two layers are NOT equally essential, and the service SHALL NOT let the second fail the first. The game-state layer is the restore; the agent-context layer is an enhancement to it. A restore whose game state was applied SHALL be reported as a restore that happened, together with whether the agent conversation was rebuilt and, when it was not, a human-readable reason. This is not a cosmetic distinction: the agent-context layer runs after the game state has already been written, and an in-place restore has no rollback, so reporting a completed rewind as a failure describes a state that does not exist and invites the user to retry a destructive action that already succeeded.

Specifically, agent-orchestrator answers `404` to a `mode="in place"` context restore when no ACTIVE agent session is bound to the game. That is a correct answer, not a fault: the session that played a game is terminated long before anyone browses its history, so most games worth restoring have none to resume. The history-service SHALL treat that `404` as "there is no agent session to resume" and complete the restore. Any other upstream failure status SHALL still fail the restore, so a genuine fault is never silently swallowed.

The restore result SHALL name the DragnCards room holding the restored state whenever the restore created one. A branch restore's entire product is a new game room, and a room the caller cannot address is indistinguishable from a restore that never happened; the room slug is returned by game-service on the same response that assigns the session id, so naming it costs nothing and removes both an extra round trip and a race against the ephemeral reaper.

#### Scenario: Restore from the nearest full-state base then replay forward
- **WHEN** a client requests a restore of a `game_id` to a target `seq`
- **THEN** the history-service SHALL select the densest full-state base at or before the target `seq` — a periodic snapshot or a `game_state` event, whichever is more recent — load it into a game-service session, and replay the game-mutating events between that base and the target `seq` in ascending `seq` order

#### Scenario: Restore reconstructs the agent conversation context
- **WHEN** the history-service restores a `game_id` to a target `seq`
- **THEN** the history-service SHALL reconstruct the agent's conversation context as captured at the latest `agent` event at or before the target `seq` and SHALL provide it to the orchestrator to seed a session bound to the restored game

#### Scenario: Restore into a new branchable session
- **WHEN** a client requests a restore with the target mode "new session"
- **THEN** the history-service SHALL create a new game-service session and orchestrator session for the restored moment, SHALL leave the original game's events and any live session unmodified, and SHALL report the new session's `room_slug` so the caller can open the game that was created

#### Scenario: Restore in place over the live session
- **WHEN** a client requests a restore with the target mode "in place"
- **THEN** the history-service SHALL restore the existing live session to the target moment, discarding game state after the target `seq`

#### Scenario: In-place restore completes when no agent session is bound to the game
- **WHEN** a client requests an in-place restore of a game for which the orchestrator reports no active agent session bound to that `game_id`
- **THEN** the history-service SHALL complete the game-state restore, SHALL report that the agent conversation was not rebuilt together with the reason, and SHALL NOT report the restore as failed

#### Scenario: In-place restore over a live session that no longer exists
- **WHEN** a client requests an in-place restore of a game whose live game-service session has been deleted or reaped
- **THEN** the history-service SHALL reject the request with a message stating that the live session no longer exists and naming the branchable restore as the alternative, and SHALL NOT mutate anything

#### Scenario: Genuine orchestrator failures still fail the restore
- **WHEN** the orchestrator fails a context restore with any status other than `404`
- **THEN** the history-service SHALL fail the restore rather than reporting a partially completed one as successful

#### Scenario: Restore when no full-state base exists
- **WHEN** a client requests a restore to a target `seq` for which no snapshot and no usable `game_state` event exists at or before that `seq`
- **THEN** a branchable restore SHALL begin from an initial game-service session and replay the game-mutating events from `seq` 1 up to the target `seq`, and an in-place restore SHALL be rejected with a message naming the missing base — because replaying forward onto an un-rewound live session would double-apply every event

#### Scenario: Reject restore to an out-of-range moment
- **WHEN** a client requests a restore to a target `seq` that does not exist for the `game_id`
- **THEN** the history-service SHALL reject the request with a descriptive client error and SHALL NOT mutate any game-service or orchestrator session

#### Scenario: Agent decision events are not replayed as mutations
- **WHEN** the history-service replays events forward during a restore
- **THEN** it SHALL apply only `game-service` game-mutating events as actions and SHALL NOT apply `agent` decision events as game mutations

#### Scenario: The replay range is narrowed to replayable events in the database
- **WHEN** the history-service reads the events to replay between the base and the target
- **THEN** it SHALL restrict that read to `game-service` events in the query itself rather than reading every actor's events and skipping them after they are transferred — because when the base is the nearest `game_state` event that range contains no `game-service` events at all, so the read should return nothing rather than fetching and parsing every intervening agent payload only to skip it (measured: 219,476 bytes on a 124-event game)

### Requirement: Stateless horizontal scaling of ingestion
The history-service SHALL allow multiple replicas to ingest concurrently from a single shared consumer group while preserving gap-free per-game ordering and idempotency.

#### Scenario: Concurrent replicas preserve ordering
- **WHEN** two history-service replicas consume events for the same `game_id` concurrently
- **THEN** the committed events SHALL still form a single gap-free ascending `seq` series for that `game_id`

#### Scenario: Concurrent replicas preserve idempotency
- **WHEN** two replicas process the same duplicated envelope concurrently
- **THEN** the history-service SHALL persist that event exactly once

### Requirement: List games with recorded history

The history-service SHALL expose an endpoint listing every game that has recorded history, including the game identifier, its event count, and its first and last recorded timestamps, ordered by most recent activity, computed without a per-game query fan-out.

#### Scenario: Listing returns recorded games

- WHEN a client requests the games list and two games have recorded events
- THEN the response contains both games with their event counts and first/last recorded timestamps, ordered by last activity descending

#### Scenario: Listing is empty when nothing is recorded

- WHEN a client requests the games list and no events have been recorded
- THEN the response is an empty list

### Requirement: Delete a game's history

The history-service SHALL support deleting all recorded history for a game — its events, snapshots, and per-game bookkeeping — in a single transaction, reporting the counts removed, and SHALL be idempotent when the game has no history.

#### Scenario: Deleting removes events and snapshots

- WHEN a delete request is issued for a game that has recorded events and snapshots
- THEN all of that game's events and snapshots are removed in one transaction and the response reports the counts deleted

#### Scenario: Deleting an absent game is idempotent

- WHEN a delete request is issued for a game with no recorded history
- THEN the request succeeds and reports zero events and zero snapshots deleted

### Requirement: Validated game_id at the route boundary
The history-service SHALL validate the `game_id` path parameter on every game-scoped route (events backfill/listing, snapshots listing, restore, and game deletion) against a strict pattern (`^[A-Za-z0-9_-]{1,64}$`) and SHALL reject a malformed, oversized, or encoded-traversal `game_id` before any database access or outbound service call. Validation SHALL NOT alter the existing idempotent semantics for a well-formed but absent `game_id`.

#### Scenario: Reject a malformed game_id
- **WHEN** a request targets a game-scoped route with a `game_id` that violates the allowed pattern (e.g. contains a dot, space, slash, encoded slash, or exceeds 64 characters)
- **THEN** the history-service SHALL reject the request before any database or outbound call, returning a validation error (422) or, for a path that cannot match the single-segment route, a route miss (404)

#### Scenario: Well-formed unknown game_id keeps idempotent delete
- **WHEN** a delete is requested for a well-formed `game_id` that has no stored history
- **THEN** the history-service SHALL return success with zero deleted events and snapshots

### Requirement: URL-encoded outbound service-call path parameters
The history-service SHALL construct outbound game-service request URLs by percent-encoding each path segment (e.g. via `httpx.URL` / `urllib.parse.quote`) rather than by raw f-string interpolation, so a crafted `game_id` or action suffix cannot inject additional path segments or traversal against the trusted internal API.

#### Scenario: Encode an id containing path-significant characters
- **WHEN** the history-service issues a game-service request for a `game_id` that contains slash or traversal characters
- **THEN** those characters SHALL be percent-encoded within a single path segment and SHALL NOT introduce extra path segments in the request

### Requirement: Allowlisted replay action_path
The history-service SHALL constrain the `action_path` read from a stored event payload to the known replay-endpoint shape (the generic `actions` endpoint, an `actions/<action_name>` suffix, or a single legacy `<action_name>` segment) before forwarding a replay, and SHALL reject any other value with a clear error instead of forwarding an arbitrary path.

#### Scenario: Reject a disallowed action_path
- **WHEN** a stored event payload carries an `action_path` that does not match the allowed replay-endpoint shape (e.g. contains traversal, extra segments, a scheme, or query characters)
- **THEN** the history-service SHALL raise an error and SHALL NOT forward any request to the game-service

#### Scenario: Forward an allowed action_path
- **WHEN** a stored event payload carries `actions` or `actions/<action_name>`
- **THEN** the history-service SHALL forward the replay to the corresponding game-service endpoint with each path segment percent-encoded

### Requirement: Game-state events carry a full, self-sufficient reconstruction base

Every `game_state` event SHALL record the session `plugin_name` slug and the complete game state in its payload, so a reconstruction can be built from history alone. A restore SHALL load the full state embedded in the nearest `game_state` event at or before the target as its base when that event is at least as recent as the nearest periodic snapshot (the densest available, preferring it over a sparser snapshot), rather than relying on action replay — because setup actions (e.g. deck loading) are not all recorded as replayable actions, so replay-from-start yields an incomplete board.

This base selection SHALL apply to **every** restore mode, not only branchable ones. A `game_state` event embeds the same complete board a snapshot does, so it establishes an equally clean base for an in-place rewind; requiring a periodic snapshot there rejected every game shorter than one snapshot cadence, which is most games a user browses. The `plugin_name` SHALL be resolvable without any snapshot (from a `game_state` event), so short games with no snapshot can still be reconstructed.

Reading the `plugin_name` SHALL NOT require loading snapshot documents that are then discarded. Every snapshot row carries a full board (~245 KB measured), so the read SHALL be bounded to the single row it consumes rather than fetching every snapshot of the game to extract one short string (measured: 1,347,305 B across 6 documents to read a 16-character slug).

#### Scenario: Short game with no snapshot reconstructs with full state

- WHEN a branchable restore targets a game that has no periodic snapshot
- THEN the branch session is created from the `plugin_name` recorded on a `game_state` event, and the nearest `game_state` event's full state is loaded as the base, reproducing the board (including cards loaded during setup)

#### Scenario: In-place rewind of a game with no snapshot

- WHEN an in-place restore targets a moment for which no periodic snapshot exists but a `game_state` event does
- THEN that event's full recorded board is loaded into the live session as the clean base and the rewind completes, rather than being rejected for want of a snapshot

#### Scenario: Ephemeral reconstruction does not restore agent context

- WHEN an ephemeral (view-only) reconstruction is created
- THEN only the game-state layer is restored; no orchestrator agent session is created for it

### Requirement: Ephemeral reconstruction sessions are non-emitting and self-reclaiming

Reconstructing a past moment for viewing SHALL create an ephemeral session that emits no history events (so it never appears in the games list and produces nothing to clean up), distinct from a kept "new branchable session". Ephemeral reconstruction sessions SHALL be reclaimed server-side after a configurable TTL — their session state and DragnCards room deleted — even if the client never issues an explicit teardown (e.g. lost network connection, tab crash, or power loss). Explicit client teardown remains the fast path for immediate cleanup.

#### Scenario: Viewing reconstruction does not pollute history

- WHEN a user opens the board reconstructed at a past event (an ephemeral reconstruction)
- THEN that reconstruction emits no history events and does not appear as a new game in the games list

#### Scenario: Reconstruction is reclaimed after a lost connection

- WHEN the client that opened an ephemeral reconstruction never issues a teardown (its connection is lost or the tab is killed)
- THEN the server reclaims the reconstruction session and its room after the TTL elapses, leaving no orphaned session or room

#### Scenario: Explicit teardown reclaims immediately

- WHEN the client closes the reconstruction view and issues a teardown
- THEN the reconstruction session and its room are deleted immediately rather than waiting for the TTL

### Requirement: Player attribution on evaluation events
The history-service SHALL accept, store, and return an optional `player` attribute on evaluation
events, identifying the player a verdict pertains to (e.g. `player1`), so per-player move/round/
game evaluations can be distinguished and queried. The field SHALL be optional for backward
compatibility with existing evaluation events that predate per-player scoring.

#### Scenario: Store and return a player-attributed evaluation
- **WHEN** an evaluation event is appended with a `player` attribute
- **THEN** the history-service SHALL persist it and SHALL include the `player` when the event is
  listed or read back

#### Scenario: Evaluation without a player remains valid
- **WHEN** an evaluation event is appended without a `player` attribute
- **THEN** the history-service SHALL accept and store it unchanged (backward compatible)

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

### Requirement: Timeline read that omits unbounded payload fields

The history-service SHALL expose a read API that lists a game's events **without
the payload fields whose size is unbounded**, so that listing a whole game's
timeline costs a size proportional to the number of events rather than to the size
of the recorded game states.

The omitted fields SHALL be `state` — the raw DragnCards room state, measured on
real recorded games at ~450-470 KB per `game-service` event — and
`conversation_context`, an agent move's whole captured conversation. Every other
payload field SHALL be carried through verbatim.

`state` SHALL NOT simply vanish: the entry's payload SHALL carry a projection of
it under `state.game` holding `roundNumber` and `stepId`, which is what a
consumer needs to label the round and the phase. The projection SHALL preserve
the recorded types — `stepId` is a dotted Marvel Champions step id and SHALL
remain a string, so step `0.1` SHALL NOT be reported as the number `0.1`, and
`roundNumber` 0 SHALL be reported as 0 rather than as absent, because 0 is the
whole first round of play. Where no game state was recorded for an event, no
`state` projection SHALL be present.

Each entry SHALL declare that its payload is reduced, so a consumer can tell a
timeline entry from a complete event and knows to fetch the complete event before
displaying an omitted field. The complete payload SHALL remain reachable per event
through the existing events read.

The timeline read SHALL use the same cursor contract as the events read — an
`after_seq` request parameter, ascending `seq` order, and a `next_after_seq`
response cursor that is absent once the log is exhausted — so a client walks
either one the same way. Its per-request `limit` ceiling MAY be higher than the
events read's, because an entry is orders of magnitude smaller.

The omitted fields SHALL be removed by the database rather than in the service
process, so that they are neither deserialized nor re-serialized on the way out.

The events read, its `limit` ceiling, its response shape, the games listing, the
snapshots read and restore SHALL be unchanged by this requirement.

#### Scenario: A listed entry drops the recorded state's bulk but keeps its round and step

- **WHEN** a client requests a game's timeline and the game has `game-service` events carrying a full DragnCards room state
- **THEN** each entry's payload SHALL omit the state's card definitions, group and stack tables, and delta log, and SHALL carry `state.game.roundNumber` and `state.game.stepId`

#### Scenario: A dotted step id survives as a string

- **WHEN** a listed entry's recorded step id is `0.0` or `0.1`
- **THEN** the timeline read SHALL report it as the string `"0.0"` or `"0.1"` and SHALL NOT report it as a number

#### Scenario: A listed agent entry drops the conversation but keeps the decision

- **WHEN** a client requests a game's timeline and the game has `agent` events carrying a captured conversation
- **THEN** each such entry's payload SHALL omit `conversation_context` and SHALL carry the move's intended action, reasoning, and arguments

#### Scenario: A listed entry is far smaller than the same event read in full

- **WHEN** the same game is read through the timeline read and through the events read
- **THEN** the timeline response SHALL be at least an order of magnitude smaller than the events response

#### Scenario: An entry declares that its payload is reduced

- **WHEN** a client reads an entry from the timeline read
- **THEN** the entry SHALL indicate that its payload is not complete, and an event read from the events read SHALL NOT so indicate

#### Scenario: The timeline pages with the events read's cursor

- **WHEN** a client walks a game's timeline by passing each response's `next_after_seq` as the next request's `after_seq`
- **THEN** the history-service SHALL return the events in ascending `seq` with no gaps and no repeats, and SHALL omit the cursor from the page that exhausts the log

#### Scenario: A complete payload is still reachable for one event

- **WHEN** a client holds a timeline entry and needs the payload fields the listing omitted
- **THEN** the existing events read SHALL serve that single event with its payload intact

#### Scenario: Timeline of an unknown game

- **WHEN** a client requests the timeline for a `game_id` with no stored history
- **THEN** the history-service SHALL return an empty result rather than an error

