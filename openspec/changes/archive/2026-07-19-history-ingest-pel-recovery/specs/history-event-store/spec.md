## MODIFIED Requirements

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
