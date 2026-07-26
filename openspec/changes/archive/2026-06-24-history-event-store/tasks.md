## 1. Service Scaffold and Configuration

- [x] 1.1 Create `services/history-service/` with FastAPI app structure, package metadata, Dockerfile, and local test configuration, mirroring `services/agent-orchestrator/`.
- [x] 1.2 Add history-service settings for the dedicated PostgreSQL URL, Valkey URL, ingestion stream/consumer-group names, ingestion stream bound (`HISTORY_INGEST_STREAM_MAXLEN`) and consumer-lag alert threshold, snapshot cadence (`SNAPSHOT_EVERY_N_EVENTS`, `SNAPSHOT_MAX_INTERVAL_SECONDS`), game-service base URL, and agent-orchestrator base URL, with secret-free defaults.
- [x] 1.3 Add health and readiness endpoints reporting API, PostgreSQL, and Valkey readiness without exposing secrets.
- [x] 1.4 Add unit tests for settings validation and health/readiness responses.

## 2. Persistence Schema and Migrations

- [x] 2.1 Define database models and migrations for `events` (envelope fields, server-assigned `seq`, unique `(game_id, idempotency_key)`) and `snapshots` (snapshot document plus `snapshot_at_seq`) in the dedicated history PostgreSQL database.
- [x] 2.2 Implement repository functions for idempotent event commit with per-game sequence assignment (per-game advisory lock + `ON CONFLICT DO NOTHING`), event range reads by `seq`, and snapshot read/write.
- [x] 2.3 Add PostgreSQL-backed unit tests proving gap-free per-game `seq` assignment, independent sequencing across games, and duplicate envelopes stored once without consuming a `seq`.

## 3. Event Envelope and Ingestion

- [x] 3.1 Implement the versioned event envelope model (`envelope_version`, `game_id`, `actor`, `event_type`, `payload`, `occurred_at`, `idempotency_key`) with validation for required fields, allowed actors, and forward-compatible unknown fields.
- [x] 3.2 Implement the Valkey-stream consumer-group ingester (`XREADGROUP`/`XACK`) that commits envelopes idempotently and acknowledges duplicates.
- [x] 3.3 Implement the authenticated HTTP backfill ingestion endpoint accepting the same envelope and ordering rules.
- [x] 3.4 Add unit tests for envelope validation (accept well-formed, reject missing fields/unknown actor, tolerate unknown fields).
- [x] 3.5 Add integration tests proving ingestion from the Valkey stream and from HTTP both persist ordered events, and that at-least-once duplicates are stored exactly once.
- [x] 3.6 Add an integration test proving two concurrent ingester instances preserve gap-free per-game ordering and idempotency.
- [x] 3.7 Bound the ingestion stream with approximate `MAXLEN` trimming on publish and emit a consumer-group lag/backpressure signal (via the observability capability) when lag exceeds the configured threshold; add a test for the lag signal.

## 4. Snapshotting

- [x] 4.1 Implement the snapshot cadence worker that, after commits, evaluates count- and time-based thresholds and pulls a full snapshot from game-service `GET /games/{id}/snapshot`.
- [x] 4.2 Store each snapshot with its corresponding `seq` in the documented snapshot format.
- [x] 4.3 Add integration tests proving a snapshot is taken after the configured event count and after the configured interval, stored with the correct `seq`.

## 5. Restore to a Past Moment

- [x] 5.1 Implement the game-state layer of restore: select the latest snapshot with `seq <= target_seq`, load it into a game-service session, then replay `game-service` game-mutating events in `(snapshot_at_seq, target_seq]` forward.
- [x] 5.2 Implement the agent-context layer of restore: look up the latest `agent` event at or before `target_seq`, extract its captured conversation context, and call the orchestrator resume-from-context capability to seed a session bound to the restored `game_id`.
- [x] 5.3 Implement the restore target mode: "new session" (create fresh game-service + orchestrator sessions, leaving the original untouched) and "in place" (rewind the existing live session, discarding state after `target_seq`); default to "new session".
- [x] 5.4 Implement the no-prior-snapshot path (start from an initial session and replay from `seq` 1) and reject out-of-range target `seq` without mutating any game-service or orchestrator session.
- [x] 5.5 Ensure `agent` decision events are excluded from forward replay as mutations, and verify post-restore game status against the stored event, surfacing divergence.
- [x] 5.6 Add an integration test that ingests a recorded game, restores to a chosen past `seq`, and asserts the restored game-service state matches the state captured at that `seq`.
- [x] 5.7 Add an integration test asserting the restored orchestrator session's conversation context matches the context captured at the target `seq`.
- [x] 5.8 Add integration tests for both restore modes (new session leaves the original intact; in-place rewinds the live session), the no-prior-snapshot path, and rejecting an out-of-range target `seq`.

## 6. Event and Snapshot Read APIs

- [x] 6.1 Implement endpoints to list a game's events by ascending `seq` with paging and to list a game's snapshots.
- [x] 6.2 Add tests for ordered event listing, snapshot listing, and empty-result behavior for unknown games.

## 7. Agent-Orchestrator Emitter

- [x] 7.1 Capture the game-service `game_id` when a prompt job creates or attaches a game session via MCP and persist it for reuse across moves.
- [x] 7.2 Emit an `agent` move/decision history envelope (intended action, reasoning/context, arguments, full conversation context, `game_id`) for each game-mutating MCP tool call, without blocking the tool round.
- [x] 7.3 Add orchestrator unit tests with a fake history bus proving an agent event is emitted per game-mutating tool call with the captured `game_id`, decision context, and full conversation context.
- [x] 7.4 Implement the resume-from-context capability: create/resume a session seeded with a supplied conversation context and bound to a supplied restored `game_id`, exposed for the history-service restore flow.
- [x] 7.5 Add orchestrator tests proving a session resumed from a supplied context has a matching conversation context and game binding and can run its next turn.

## 8. Game-Service Emitter and Restore Entry Point

- [x] 8.1 Emit a `game-service` state/status history envelope after each executed action (resulting state + status, session id as `game_id`) without changing the action result returned to the caller.
- [x] 8.2 Confirm the existing snapshot import path accepts a history-supplied snapshot and supports applying replayed actions forward; add any missing restore-entry affordance.
- [x] 8.3 Add game-service unit tests with a fake history bus proving a state/status event is emitted per executed action with the correct `game_id`.
- [x] 8.4 Add a game-service integration test proving a snapshot can be loaded into a target session and replayed actions applied forward.

## 9. Dashboard History UI

- [x] 9.1 Add a dashboard history route/view that lists a game's events by ascending `seq`, distinguishing `agent` and `game-service` events and indicating snapshot restore points.
- [x] 9.2 Add detail rendering for an agent move (intended action + reasoning/context) and a state event (game status), with an empty-state for games without history.
- [x] 9.3 Add a restore control that requests a restore to a selected moment's `seq`, lets the user choose the target mode (new branchable session vs in-place overwrite, defaulting to new session) with a confirmation warning before an in-place overwrite, and shows success or failure outcomes.
- [x] 9.4 Verify the timeline and restore flow end-to-end in the running app with the Playwright MCP.

## 10. Infrastructure and End-to-End Verification

- [x] 10.1 Add `history-service` and its dedicated PostgreSQL to `docker-compose.yaml` / `docker-compose.infra.yaml` with environment placeholders and secret-free defaults, and the shared ingestion Valkey stream configuration.
- [x] 10.2 Add an end-to-end integration test that runs an agent game so both producers emit events, confirms ordered durable storage and at least one snapshot, then restores the game to a past `seq` and asserts the restored state matches.
- [x] 10.3 Run the history-service, agent-orchestrator, game-service, and infrastructure test suites and document any external services required for skipped tests.
