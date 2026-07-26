## ADDED Requirements

### Requirement: History service boundary and persistence
The system SHALL provide a dedicated `history-service` (Python/FastAPI) that persists a per-game append-only event log and periodic game-state snapshots in a dedicated PostgreSQL database, and SHALL NOT retain game history in process memory.

#### Scenario: History service uses dedicated persistent storage
- **WHEN** the history-service stores an ingested event or a game-state snapshot
- **THEN** the history-service SHALL persist it in its dedicated PostgreSQL database and SHALL NOT keep the event log or snapshots only in process memory

#### Scenario: Health and readiness without secrets
- **WHEN** a client requests the history-service health or readiness endpoint
- **THEN** the history-service SHALL report API, PostgreSQL, and Valkey ingestion readiness and SHALL NOT expose any secret values

### Requirement: Versioned event envelope
The history-service SHALL define a versioned event envelope containing an envelope version, a game correlation identifier (`game_id`), an actor of `agent` or `game-service`, an event type, a JSON payload, a producer-supplied occurrence timestamp, an idempotency key, and a history-assigned monotonic per-game sequence number and recorded timestamp.

#### Scenario: Accept a well-formed envelope
- **WHEN** a producer submits an event envelope containing `envelope_version`, `game_id`, `actor`, `event_type`, `payload`, `occurred_at`, and `idempotency_key`
- **THEN** the history-service SHALL accept the envelope and SHALL assign a monotonic per-game `seq` and a `recorded_at` timestamp before persisting it

#### Scenario: Reject an envelope missing required fields
- **WHEN** a producer submits an envelope missing `game_id`, `actor`, or `event_type`
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Reject an unknown actor
- **WHEN** a producer submits an envelope whose `actor` is neither `agent` nor `game-service`
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Tolerate unknown forward-compatible fields
- **WHEN** a producer submits an envelope with a recognized `envelope_version` and additional unknown fields
- **THEN** the history-service SHALL persist the envelope without failing on the unknown fields

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
The history-service SHALL ingest events from both producers over a shared Valkey stream consumer group as the primary path and SHALL accept the same envelope through an authenticated HTTP backfill endpoint, and SHALL guarantee that at-least-once duplicate deliveries are stored at most once per `game_id`.

#### Scenario: Ingest from the Valkey stream
- **WHEN** a producer publishes an event envelope to the shared history ingestion Valkey stream
- **THEN** the history-service SHALL consume it through its consumer group, persist it, and acknowledge the stream entry

#### Scenario: Ingest from the HTTP backfill endpoint
- **WHEN** a client submits an event envelope to the history-service HTTP ingestion endpoint for a `game_id`
- **THEN** the history-service SHALL persist the event using the same envelope contract and ordering rules as the Valkey path

#### Scenario: Duplicate delivery is stored once
- **WHEN** the same envelope (identical `game_id` and `idempotency_key`) is delivered more than once
- **THEN** the history-service SHALL persist it exactly once, SHALL NOT consume an additional `seq` for the duplicate, and SHALL acknowledge the duplicate delivery

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
The history-service SHALL restore a game to an arbitrary past moment identified by a target `seq` by reconstructing both the game state (loading the nearest prior snapshot into a game-service session and replaying the subsequent game-mutating events forward up to and including the target `seq`) and the agent's conversation context as of the target `seq` (loaded into an orchestrator session bound to the restored game), so the agent faces an identical, replayable situation.

#### Scenario: Restore from nearest prior snapshot then replay forward
- **WHEN** a client requests a restore of a `game_id` to a target `seq`
- **THEN** the history-service SHALL select the latest snapshot whose `seq` is less than or equal to the target `seq`, load it into a game-service session, and replay the game-mutating events between that snapshot and the target `seq` in ascending `seq` order

#### Scenario: Restore reconstructs the agent conversation context
- **WHEN** the history-service restores a `game_id` to a target `seq`
- **THEN** the history-service SHALL reconstruct the agent's conversation context as captured at the latest `agent` event at or before the target `seq` and SHALL provide it to the orchestrator to seed a session bound to the restored game

#### Scenario: Restore into a new branchable session
- **WHEN** a client requests a restore with the target mode "new session"
- **THEN** the history-service SHALL create a new game-service session and orchestrator session for the restored moment and SHALL leave the original game's events and any live session unmodified

#### Scenario: Restore in place over the live session
- **WHEN** a client requests a restore with the target mode "in place"
- **THEN** the history-service SHALL restore the existing live session to the target moment, discarding game state after the target `seq`

#### Scenario: Restore when no prior snapshot exists
- **WHEN** a client requests a restore to a target `seq` for which no snapshot at or before that `seq` exists
- **THEN** the history-service SHALL begin from an initial game-service session and replay the game-mutating events from `seq` 1 up to the target `seq`

#### Scenario: Reject restore to an out-of-range moment
- **WHEN** a client requests a restore to a target `seq` that does not exist for the `game_id`
- **THEN** the history-service SHALL reject the request with a descriptive client error and SHALL NOT mutate any game-service or orchestrator session

#### Scenario: Agent decision events are not replayed as mutations
- **WHEN** the history-service replays events forward during a restore
- **THEN** it SHALL apply only `game-service` game-mutating events as actions and SHALL NOT apply `agent` decision events as game mutations

### Requirement: Stateless horizontal scaling of ingestion
The history-service SHALL allow multiple replicas to ingest concurrently from a single shared consumer group while preserving gap-free per-game ordering and idempotency.

#### Scenario: Concurrent replicas preserve ordering
- **WHEN** two history-service replicas consume events for the same `game_id` concurrently
- **THEN** the committed events SHALL still form a single gap-free ascending `seq` series for that `game_id`

#### Scenario: Concurrent replicas preserve idempotency
- **WHEN** two replicas process the same duplicated envelope concurrently
- **THEN** the history-service SHALL persist that event exactly once
