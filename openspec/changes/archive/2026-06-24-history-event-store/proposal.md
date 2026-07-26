## Why

When an LLM agent plays a DragnCards game today, the play is ephemeral. The orchestrator streams events into a per-job Valkey stream (TTL 300s) and persists `job_events` per session, while game-service holds game state in-process and exposes it only via HTTP/MCP pull. There is no durable, cross-service, ordered record of what an agent decided, why, what action it took, and how the game changed as a result. That makes two things we want impossible:

1. **Rating how well the agent played.** To later score decisions we must capture, per move, the agent's *intended* action, its *reasoning/context*, the *resulting game state*, and the *game status* — correlated to a single game over its whole lifetime, not scattered across two services' transient stores.
2. **Restoring a game to any past moment.** Debugging, branching "what-if" replays, and reproducing failures all require event-sourcing: a durable, ordered log of every event plus the ability to reconstruct game state at an arbitrary point.

We need a dedicated, cloud-native history / event-store service that ingests events from both producers (agent-orchestrator and game-service), correlates them per game, stores them durably in PostgreSQL, periodically checkpoints full game-state snapshots, and exposes restore. The data model must be rich enough to enable rating later, even though the rating engine itself is out of scope.

## What Changes

- Add a new `history-service` (Python/FastAPI, mirroring `agent-orchestrator` structure) with a dedicated PostgreSQL database for a persistent, append-only event log and periodic game-state snapshots. No in-memory state.
- Define a versioned **event envelope** (game correlation id, monotonic per-game sequence number, event type, actor `agent`|`game-service`, payload, timestamp, idempotency key) and ingest events from both producers over the existing Valkey event bus, with a fallback HTTP ingestion endpoint for replay/backfill.
- **agent-orchestrator** SHALL emit an agent move/decision event for each tool-driven game action — capturing the intended action, the reasoning/context, and the **full conversation context** (message/tool history) the agent had at that decision — tagged with a game correlation id, and SHALL support **resuming a session from a supplied conversation context** so a restored game can be replayed from an identical situation.
- **game-service** SHALL emit a game-state/status event after each executed action and SHALL support snapshot-based restore of a session from a supplied snapshot document.
- The history-service SHALL store events in strict per-game order with at-least-once + idempotent ingestion, checkpoint full snapshots at a configurable cadence (default every 25 events / 300s), bound its ingestion stream with `MAXLEN` + consumer-lag alerting, and expose a **restore** operation that reconstructs **both** the game state (nearest snapshot + forward replay of game-mutating events) **and** the agent's conversation context at the requested moment — selectable per restore as a new branchable session or an in-place overwrite.
- Add **dashboard** UI to browse a game's history timeline (events + snapshots) and trigger a restore to a chosen point.
- Add unit and integration tests covering ingestion, ordered storage, snapshotting, and restore-to-a-past-moment.

## Non-goals

- **Automated play-rating / scoring engine is explicitly out of scope** and deferred to a future change. This change only guarantees the stored data is rich enough to support it later.
- No changes to the upstream DragnCards Elixir backend or Marvel Champions plugin.
- No new LLM provider, model, or strategy behavior.
- No replacement of orchestrator SSE streaming or game-service state APIs; history-service consumes them, it does not supersede them.
- No cross-game analytics, aggregation dashboards, or long-term archival/retention tiering beyond the event log and snapshots.

## Capabilities

### New Capabilities

- `history-event-store`: durable per-game event log, event envelope contract, dual-source ingestion (Valkey bus + HTTP backfill) with idempotency and ordering, periodic snapshotting, and restore-to-a-past-moment.
- `game-history-ui`: dashboard timeline view of a game's events and snapshots plus a restore control.

### Modified Capabilities

- `agent-orchestrator`: SHALL emit agent move/decision events capturing intended action + reasoning + full conversation context correlated to a game id, and SHALL support resuming a session from a supplied conversation context (resume-at-a-point) for restore.
- `game-service`: SHALL emit game-state/status events after executed actions and SHALL expose a snapshot-based restore entry point usable by the history-service.
- `infrastructure`: add `history-service` and its dedicated PostgreSQL to Docker Compose with secret-free defaults.

## Impact

- New service code under `services/history-service/` with its own schema/migrations and dedicated PostgreSQL.
- New event-emission paths in `agent-orchestrator` and `game-service` (additive; existing contracts unchanged), plus an orchestrator resume-from-context capability used by restore.
- New dashboard route and components for the history timeline and restore, including the per-restore mode choice (new branchable session vs in-place overwrite).
- New Docker Compose entries and environment configuration for the history-service and its database.
- Tests for ingestion, ordering/idempotency, snapshotting, restore, and the two producer emitters.
