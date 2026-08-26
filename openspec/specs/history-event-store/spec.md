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

A `mode="new"` restore SHALL accept an optional existing game-service session to restore into, and SHALL honour it ONLY when the restore is `ephemeral` AND a full-state base at or before the target exists. Building a room is several sequential round trips to DragnCards plus a channel join and a plugin load, measured at ~590 ms of a ~728 ms restore, whereas loading a full-state base into an already-open room was measured at ~55 ms; a caller viewing a second moment of the same game already holds a room that can be re-pointed instead of replaced.

The base requirement is the safety gate, not an optimisation detail. Loading a full-state base issues the DragnCards `set_game` action, which replaces the room's game document outright rather than merging into it, so the loaded document is the entire resulting state and nothing from the previous contents survives. A restore with no base has no such guarantee: it replays forward from `seq` 1 onto whatever the session already holds, which in a reused session is the previous view. The service SHALL therefore create a fresh session whenever no base exists, even when a session to reuse was supplied.

The `ephemeral` condition is what keeps the field aimed at the flow it exists for. Reuse overwrites a session the caller names rather than one the restore created, and an ephemeral reconstruction is by definition a throwaway the caller built in order to look at it. A kept branch restore's whole product is the room it creates, so it SHALL always create one; without this condition the field would be a way to replace an unrelated live session's board with a different game's.

A supplied session SHALL NOT be deleted by the restore's rollback when a restore fails, because the restore did not create it and the caller still owns it. A session whose plugin does not match the game being restored SHALL cause the restore to fail with a client error rather than be loaded into.

#### Scenario: Restore from the nearest full-state base then replay forward
- **WHEN** a client requests a restore of a `game_id` to a target `seq`
- **THEN** the history-service SHALL select the densest full-state base at or before the target `seq` — a periodic snapshot or a `game_state` event, whichever is more recent — load it into a game-service session, and replay the game-mutating events between that base and the target `seq` in ascending `seq` order

#### Scenario: Restore reconstructs the agent conversation context
- **WHEN** the history-service restores a `game_id` to a target `seq`
- **THEN** the history-service SHALL reconstruct the agent's conversation context as captured at the latest `agent` event at or before the target `seq` and SHALL provide it to the orchestrator to seed a session bound to the restored game

#### Scenario: Restore into a new branchable session
- **WHEN** a client requests a restore with the target mode "new session"
- **THEN** the history-service SHALL create a new game-service session and orchestrator session for the restored moment, SHALL leave the original game's events and any live session unmodified, and SHALL report the new session's `room_slug` so the caller can open the game that was created

#### Scenario: Restore into a supplied existing session
- **WHEN** a client requests an `ephemeral` `mode="new"` restore naming an existing game-service session to restore into, and a full-state base at or before the target exists
- **THEN** the history-service SHALL load that base into the named session and replay forward into it, SHALL NOT create a game-service session or a DragnCards room, and SHALL report the restore against the named session

#### Scenario: A reused session ends in exactly the target state
- **WHEN** a session that already holds one moment of a game is restored to a different moment of that game
- **THEN** the resulting game state SHALL be identical to the state produced by restoring that same moment into a freshly created session, carrying nothing over from the moment it previously held

#### Scenario: A supplied session is ignored when no full-state base exists
- **WHEN** a client requests an `ephemeral` `mode="new"` restore naming an existing session, but no snapshot and no usable `game_state` event exists at or before the target `seq`
- **THEN** the history-service SHALL create a fresh session and replay into that instead, and SHALL leave the named session untouched

#### Scenario: A supplied session is ignored for a kept branch restore
- **WHEN** a client requests a non-`ephemeral` `mode="new"` restore naming an existing session
- **THEN** the history-service SHALL create a fresh session and restore into that, and SHALL leave the named session untouched

#### Scenario: A supplied session is not deleted when the restore fails
- **WHEN** an `ephemeral` `mode="new"` restore into a supplied existing session fails part-way through
- **THEN** the history-service SHALL report the failure and SHALL NOT delete the supplied session, because the caller owns it

#### Scenario: A supplied session for the wrong plugin is rejected
- **WHEN** a client requests a restore into an existing session whose plugin differs from the plugin recorded for the game
- **THEN** the history-service SHALL fail the restore with a client error and SHALL NOT leave the named session holding a partially loaded state

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

### Requirement: Reclaim failures do not discard an ingest batch
The stream ingester SHALL treat the pending-entry reclaim pass as best-effort. A
failure while reclaiming SHALL NOT prevent the same batch from reading and committing
new entries.

Reclaiming is recoverable by construction: an entry that is not claimed on one cycle
remains in the consumer group's Pending Entries List and stays eligible for a later
cycle once it exceeds `HISTORY_INGEST_CLAIM_MIN_IDLE_MS`. Aborting the batch therefore
costs new events without saving stale ones.

A reclaim failure SHALL be reported as a single warning line naming the exception type
and message, without a stack trace, and SHALL set a `history.reclaim_failed` flag on
the batch span.

A transport failure raised while reclaiming SHALL NOT be interpreted as the
"unknown command" reply that selects the `XPENDING` + `XCLAIM` fallback, because that
signal is a server response and a transport failure is not.

#### Scenario: New entries are still ingested when reclaiming fails
- **WHEN** `XAUTOCLAIM` fails with a connection error and the stream holds an uncommitted entry
- **THEN** `process_batch` SHALL log one warning, read the entry, commit it, acknowledge it, and report it as processed

#### Scenario: Reclaim failure is not mistaken for a missing command
- **WHEN** `XAUTOCLAIM` fails with a transport error rather than an `ERR unknown command` reply
- **THEN** the ingester SHALL NOT switch to the `XPENDING` + `XCLAIM` fallback path

#### Scenario: Unclaimed entries remain available
- **WHEN** a reclaim pass fails and stale entries are left unclaimed
- **THEN** those entries SHALL remain pending and SHALL be claimable on a later cycle

### Requirement: Bounded retry pacing and de-duplicated failure logging
When a whole ingest batch fails, the poll loop SHALL retry with exponential backoff
starting at `INGEST_RETRY_MIN_SECONDS` and doubling to a ceiling of
`INGEST_RETRY_MAX_SECONDS`, rather than retrying on a fixed short delay.

The loop SHALL log a full traceback only for the first failure of a consecutive streak.
Each subsequent failure in the same streak SHALL log a single warning carrying the
count of consecutive failures and the next retry delay.

A batch that succeeds after one or more failures SHALL log a recovery line reporting
how many consecutive failures preceded it, and SHALL reset both the streak count and
the backoff.

Failures that can lose an event SHALL continue to surface: a failing stream read, a
failing commit, a failing acknowledgement and a malformed envelope are unaffected by
this requirement, and no entry is acknowledged without a successful commit.

#### Scenario: A sustained outage backs off instead of spinning
- **WHEN** `process_batch` fails continuously
- **THEN** the delay between attempts SHALL increase monotonically and SHALL NOT exceed `INGEST_RETRY_MAX_SECONDS`

#### Scenario: One traceback per outage
- **WHEN** `process_batch` fails many times consecutively
- **THEN** exactly one log record SHALL carry exception info, and the remainder SHALL be warnings naming the consecutive-failure count

#### Scenario: Recovery resets the pacing
- **WHEN** a batch succeeds after a streak of failures
- **THEN** the ingester SHALL log a recovery line and SHALL return to `INGEST_RETRY_MIN_SECONDS` for any future failure

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

### Requirement: A recorded event states the orchestration mode it came from
An event recorded from an agent session SHALL carry the mode that session runs in, so a stored timeline states whether it was produced by a single chat agent or by an orchestrated table of per-seat agents. A consumer reading a game's history SHALL be able to tell the two apart without inferring it from the presence of seat identifiers.

An event from an orchestrated session SHALL carry the seat identifier of the agent that produced it, and an event produced by the orchestrating agent itself SHALL carry no seat identifier, so the orchestrator's own bookkeeping is distinguishable from a player's play.

An event recorded before the mode existed, and an event from a session in chat mode, SHALL read as chat mode, so the addition changes no stored meaning.

#### Scenario: An orchestrated seat's move states its mode and seat
- **WHEN** a player agent of an orchestrated session records a move
- **THEN** the stored event SHALL state the orchestrated mode and that seat's identifier

#### Scenario: The orchestrator's own event carries no seat
- **WHEN** the orchestrating agent records an event
- **THEN** the stored event SHALL state the orchestrated mode and SHALL carry no seat identifier

#### Scenario: A chat session's event reads as chat
- **WHEN** a chat session records a move
- **THEN** the stored event SHALL state the chat mode

### Requirement: Capability endpoint

The history-service SHALL expose `GET /capabilities`, returning a JSON document
with the service name, the service's version string, and the list of features
the server supports, so a client can detect version skew before it sends
anything.

The feature list SHALL be derived from the service's own OpenAPI document — one
`verb:path` entry per documented route, for example `get:/games` or
`get:/games/{game_id}/events` — rather than from a hand-maintained list, so a
route added later is advertised without anyone remembering to add it and a route
removed stops being advertised. The derivation SHALL be asserted structurally by
a test that reads the app's own OpenAPI document and fails if the advertised
feature list does not cover every documented route exactly once.

The endpoint SHALL be excluded from the service's MCP surface, because it
describes the server's own state like the liveness and readiness probes, and
SHALL remain fully functional over HTTP.

A server built before this requirement SHALL answer `GET /capabilities` with
`404`, and a client SHALL treat that response as the signal that the server
predates the negotiation.

#### Scenario: A client learns what the server supports

- **WHEN** a client sends `GET /capabilities` to the history-service
- **THEN** the service SHALL respond `200` with the service name, the version
  string, and a feature list containing one `verb:path` entry per documented
  route

#### Scenario: A new route is advertised without a list edit

- **WHEN** a route is added to the history-service and the service's OpenAPI
  document is read
- **THEN** the added route SHALL appear in the `/capabilities` feature list,
  because the list is derived from the document rather than maintained by hand

#### Scenario: The advertised features match the route table

- **WHEN** the service's `/capabilities` response is compared against its own
  OpenAPI document
- **THEN** every documented route SHALL appear exactly once in the feature list

#### Scenario: Capabilities is not an MCP tool

- **WHEN** a client lists the history-service's MCP tools
- **THEN** the `capabilities` tool SHALL be absent, while `GET /capabilities`
  over HTTP SHALL keep working

#### Scenario: A server that predates the endpoint is detectable

- **WHEN** a client sends `GET /capabilities` to a server built before this
  requirement
- **THEN** the server SHALL answer `404`, and the client SHALL treat that
  response as the signal that the server predates the negotiation

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

### Requirement: Marvel hand names are excluded from durable state events

When game-service publishes a Marvel LCG state, prompt, move, or terminal event for
history, its normalized state SHALL use the spectator projection. Player hands SHALL be
represented only by hidden counts, while unambiguous public state may remain visible.
The history payload SHALL not contain private hand card names, identifiers, or metadata.

#### Scenario: A player-specific live read does not affect history

- **WHEN** a player-specific state read occurs before a Marvel history event is emitted
- **THEN** history normalization SHALL independently use the spectator projection
- **AND** the event SHALL not contain the previously selected hand's card names
