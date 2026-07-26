## Context

Two producers hold the data we want to capture, and neither persists it durably for cross-service correlation:

- **agent-orchestrator** runs LLM jobs. Each tool round produces `tool_call` / `tool_result` `job_events` (persisted to its own PostgreSQL `job_events`) and live `reasoning` / `model_output` chunks published to a per-job Valkey stream `agent-orchestrator:live-events:{job_id}` (max 512 entries, TTL 300s). It connects to game-service as an MCP server (`GAME_SERVICE_MCP_URL`); game session IDs flow only as MCP tool arguments/results. There is no session-level `game_id` field — `agent_sessions.metadata_json` and `jobs.metadata_json` are free-form.
- **game-service** holds game state in-process per `GameSession` (keyed by a UUID `session_id`, mapped to a DragnCards `room_slug`). State is pull-only via `GET /games/{id}/state`; status lives in `game["mode"]` (`unknown`/`in progress`/`win`/`loss`). It already supports a versioned snapshot document — `GameStateSnapshot { schema_version: 1, plugin_name, game }` — via `GET /games/{id}/snapshot` (export) and `PUT /games/{id}/snapshot` (import). Session metadata is stored in Valkey (`game-service:session:{id}`); state is not.

The history-service must correlate both producers under one game identity, store an ordered append-only log, snapshot periodically, and restore by snapshot-load + forward replay. The restore primitive already exists in game-service (`PUT /games/{id}/snapshot`); the missing pieces are durable storage, correlation, and replay orchestration.

## Goals / Non-Goals

**Goals:** durable per-game ordered event log; a stable, rating-ready event envelope; dual-source ingestion that is idempotent under at-least-once delivery; periodic full-state snapshots; restore to an arbitrary past moment; a dashboard timeline + restore control.

**Non-Goals:** the rating engine itself; modifying upstream DragnCards; replacing orchestrator/game-service runtime APIs; analytics beyond a single game's timeline.

## Decisions

### 1. A separate `services/history-service/` FastAPI service with a dedicated PostgreSQL

Rationale: The event log + snapshots are persistent data (repo convention: PostgreSQL for persistence, Valkey for ephemeral). History has a different failure domain, retention profile, and write pattern (append-only, high volume) than orchestration or game control. A dedicated database keeps schemas, migrations, and load isolated, matching how agent-orchestrator was given its own Postgres. Services keep no in-memory state.

Alternatives considered: (a) Extend agent-orchestrator — rejected: it couples history retention to orchestration storage and would still miss game-service-side events that never pass through the orchestrator. (b) Reuse an existing database — rejected: violates the isolation precedent and mixes failure domains. (c) Object storage / append-only file log — rejected: loses queryability for the timeline UI and ordered range reads needed for replay; reintroduce later only if volume demands it.

### 2. Event envelope: per-game correlation id + monotonic per-game sequence number

The envelope is `{ event_id (uuid), game_id, seq (int64), event_type, actor (agent|game-service), payload (jsonb), occurred_at, recorded_at, idempotency_key, producer_offset }`. `game_id` is the correlation id shared by both producers. `seq` is a gap-free monotonic integer **assigned by the history-service at commit time** (not by producers), under a per-game advisory lock, so ordering is authoritative even when producers deliver concurrently or out of order. Producers supply `occurred_at` and an `idempotency_key`; history-service supplies `seq` and `recorded_at`.

Rationale: Authoritative server-side sequencing removes any dependency on producer clocks or delivery order and gives replay a deterministic forward order. The payload is rich enough for rating: agent events carry intended action + reasoning/context + tool args; game-service events carry resulting state digest + status + outcome.

Alternatives considered: (a) Producer-assigned sequence numbers — rejected: two independent producers cannot maintain a single gap-free sequence without coordination. (b) Order by timestamp only — rejected: clock skew across services breaks tie-breaking and exact-moment replay. (c) Lamport/vector clocks — rejected: more machinery than a single-writer per-game sequence needs.

### 3. Correlation id propagation: game-service `session_id` is the `game_id`

We adopt the game-service session UUID as the canonical `game_id`. game-service already owns it and stamps it on its own events. The orchestrator obtains it from the `create_game` MCP tool result and MUST stamp it on every emitted agent move/decision event (stored on the job/session so subsequent moves reuse it). The history-service treats `game_id` as opaque.

Alternatives considered: (a) Mint a new history-side correlation id — rejected: requires a registration handshake before the first event and a mapping table on both producers. (b) Use orchestrator `session_id` — rejected: game-service events would then need to learn the orchestrator id, which it never sees; the dependency direction is wrong.

### 4. Transport: ingest over the existing Valkey event bus, with an HTTP backfill endpoint

Primary path: producers publish envelopes to a shared Valkey stream `history:ingest` (consumer-group `history-service`, using `XADD` / `XREADGROUP` / `XACK`), reusing the Valkey infrastructure both services already depend on. The history-service is the single consumer group, so it can scale horizontally with one stream and multiple consumers. A secondary authenticated HTTP endpoint `POST /games/{game_id}/events` accepts the same envelope for replay/backfill and for environments where a producer cannot reach Valkey.

Rationale: The bus decouples producers from history-service availability (events buffer in the stream if history is briefly down) and matches the existing event-driven style. HTTP backfill covers gaps and tooling.

Coupling/risk: This makes both producers depend on a shared Valkey stream contract (key name, envelope schema). We mitigate by versioning the envelope (`envelope_version`) and treating unknown fields as forward-compatible. A dedicated stream (not reusing the per-job live-event streams) avoids coupling to the orchestrator's 512-entry/300s-TTL transient stream, whose trimming would otherwise drop history events.

Alternatives considered: (a) Direct synchronous HTTP-only ingestion — rejected as the primary path: it couples each producer's request latency to history availability and risks losing events on history downtime. (b) Valkey pub/sub instead of streams — rejected: pub/sub drops messages with no subscriber and offers no consumer-group replay/ack. (c) Kafka/NATS — rejected: adds a new infrastructure dependency before throughput justifies it.

### 5. Idempotency under at-least-once delivery

Valkey streams + consumer groups give at-least-once, so duplicates are expected. Each envelope carries `idempotency_key = hash(game_id, actor, producer_offset)`; the events table has a unique constraint on `(game_id, idempotency_key)`. Inserts use `ON CONFLICT DO NOTHING`; a conflict means already-stored and the message is `XACK`ed. Sequence assignment happens only on a genuine insert, inside the per-game lock, so duplicates never consume a `seq`.

Alternatives considered: (a) Dedupe by `(game_id, seq)` — rejected: `seq` is server-assigned, so it cannot dedupe inbound duplicates. (b) Best-effort dedupe in a cache — rejected: violates "no in-memory state" and is unreliable across replicas.

### 6. Snapshotting cadence: count- and time-based, full game-service export

After committing an event, the history-service evaluates a cadence policy (`SNAPSHOT_EVERY_N_EVENTS`, default 25; `SNAPSHOT_MAX_INTERVAL_SECONDS`, default 300). When due, it pulls a full snapshot via game-service `GET /games/{game_id}/snapshot` and stores the `GameStateSnapshot` document plus the `seq` it corresponds to (`snapshot_at_seq`). Snapshots are full, self-contained restore points (leveraging the existing export format).

Alternatives considered: (a) Reconstruct state purely by replaying every event from the start — rejected: O(n) restore cost and requires every event to be a perfect, replayable game-state mutation, which agent-decision events are not. (b) Snapshot every event — rejected: storage and game-service load too high. (c) Delta snapshots — rejected: more complex than full snapshots given the existing export already produces a complete document.

### 7. Restore is dual-layer: game state **and** agent conversation context

A restored moment must place the LLM in an *identical decision situation* — not just the same board state, but the same conversation context it had at that `seq` — so that, given the same messages, the agent could play forward and arrive at the same conclusion (this is also what makes later rating meaningful). Restore therefore reconstructs two layers:

- **Game-state layer (game-service):** find the latest snapshot with `snapshot_at_seq <= target_seq`, `PUT` it into a game-service session (existing import; validates `schema_version` and matching `plugin_name`), then replay the subsequent game-mutating events (`seq` in `(snapshot_at_seq, target_seq]`, actor `game-service`) forward via game-service action execution. If no snapshot precedes `target_seq`, restore starts from a fresh/initial session and replays from `seq` 1.
- **Agent-context layer (agent-orchestrator):** reconstruct the agent's conversation context as of `target_seq` from the recorded `agent` events (which carry the full message history / tool calls / tool results up to that decision — see Decision 9) and load it into an orchestrator session bound to the restored game, so the agent resumes from an identical context.

Agent-decision events are therefore **not replayed as game-state mutations** (that would double-apply effects), but they **are** the source of truth for rebuilding the conversation context. Both event types are used in restore; they feed different layers.

**Restore target mode (user choice per restore):** restore supports both (a) a **new branchable session** — spin up a fresh game-service+orchestrator session at the target moment, leaving the original timeline untouched (enables what-if/comparison), and (b) **in-place overwrite** — rewind the existing live session to the target moment, discarding events after it. The caller selects the mode per restore; new-session is the safe default the UI pre-selects.

Rationale: matches the user-chosen event-replay + periodic-snapshot model and reuses the snapshot import primitive game-service already supports, while satisfying the "replay the same situation" requirement that distinguishes a useful restore from a state-only rewind.

Risk (DragnCards, not under our control): The DragnCards Elixir backend owns automation/phase logic over a Phoenix Channels WebSocket. Snapshot import is implemented as a `set_game` action and is the only restore primitive we have; if upstream changes its snapshot/`set_game` semantics or WebSocket protocol, restore fidelity changes with it. Forward replay of individual actions can also diverge if upstream automation is non-deterministic. Mitigation: prefer restoring from the nearest snapshot with minimal forward replay; record the source `seq` and verify post-restore game `mode`/digest against the stored event; surface mismatches rather than silently accepting them.

### 8. Cloud-native: stateless, horizontally scalable, migrated schema

The service holds no state in memory: all durable data is in its PostgreSQL, all transient ingestion buffering is in the Valkey stream. Multiple replicas share one consumer group, so ingestion scales horizontally; per-game ordering is preserved by the per-game advisory lock + unique constraint, independent of which replica processes a message. Schema changes ship as versioned migrations (matching the orchestrator's migration approach). Health/readiness endpoints report DB and Valkey readiness without exposing secrets; provider/DB secrets are externalized via environment.

Alternatives considered: (a) Single-writer ingestion process — rejected: a scaling bottleneck and single point of failure; the per-game lock already gives correctness without serializing all games.

### 9. Agent events capture full conversation context; orchestrator supports resume-at-a-point

To make the agent-context layer of restore (Decision 7) possible, each `agent` move/decision event payload carries not only the intended action + reasoning but the **full conversation context the agent had when it made that decision** — the ordered message history (system/user/assistant turns, tool calls and tool results) sufficient to rehydrate the session. The history-service stores this opaquely. The agent-orchestrator gains a **resume-at-a-point capability**: create/run a session seeded with a supplied conversation context (and bound to a restored `game_id`) so the next turn faces the identical situation.

Because the agent context at `seq N` is a superset of the context at earlier decisions, we capture it per agent event rather than reconstructing it by diffing — the latest `agent` event at or before `target_seq` already contains the full context to load, so context restore is an O(1) lookup, not a replay.

Rationale: storing the full context per decision keeps restore simple and exact and gives the future rating engine the complete input the agent actually saw. Trade-off: larger `agent` payloads (mitigated by `jsonb` storage and the fact that snapshots already dominate storage); the context is also what a rater needs, so it is not waste.

Alternatives considered: (a) Store only deltas (the new messages since the last agent event) and rebuild by concatenation during restore — rejected: more replay logic and failure modes for a marginal storage saving; revisit only if payload size becomes a problem. (b) Re-derive context from orchestrator `job_events` at restore time — rejected: couples restore to orchestrator-internal storage and breaks the "history-service is the durable record" boundary.

### 10. Ingestion stream bounded by `MAXLEN` with consumer-lag alerting

The shared `history:ingest` Valkey stream is transport only — the durable copy is in PostgreSQL. The stream is capped with an approximate `MAXLEN` so it cannot grow unbounded, and the history-service emits a consumer-group lag/backpressure signal (via the `observability` capability) when it falls behind, so operators are alerted before the cap risks dropping un-consumed entries. Gaps that do occur are recoverable via the HTTP backfill endpoint replaying from PostgreSQL on the producer side.

Rationale: bounds memory growth without risking the durable record; alerting turns a silent backlog into an actionable signal.

Alternatives considered: (a) Unbounded stream — rejected: unbounded Valkey memory growth during a history outage. (b) Aggressive TTL trim relying solely on HTTP backfill — rejected: more reconciliation logic and a higher chance of needing backfill in normal operation; kept only as the recovery path.

## Risks / Trade-offs

- **Shared envelope/stream contract across three services** -> versioned `envelope_version`, forward-compatible unknown-field handling, contract tests in producers.
- **At-least-once duplicates / out-of-order delivery** -> server-assigned `seq` under per-game lock + unique idempotency constraint.
- **DragnCards snapshot/`set_game` and WebSocket behavior is upstream and uncontrolled** -> restore prefers nearest snapshot, verifies status post-restore, reports divergence; never modifies upstream.
- **Non-deterministic upstream automation during forward replay** -> minimize replay span via snapshot cadence; treat replay divergence as a surfaced error.
- **Game-service state is pull-only and in-process** -> history-service snapshots via the export endpoint at commit time, accepting that a snapshot reflects state at pull time; the corresponding `seq` is recorded so any skew is observable.
- **Valkey stream growth if history-service is down** -> bounded by stream `MAXLEN`/retention configuration with alerting; HTTP backfill recovers gaps.

## Migration Plan

1. Scaffold `services/history-service/` (FastAPI app, settings, health/readiness, Dockerfile, dedicated PostgreSQL).
2. Add schema/migrations for `events` and `snapshots` with the per-game unique idempotency constraint and per-game sequence assignment.
3. Add the Valkey-stream consumer-group ingester and the HTTP backfill endpoint; implement idempotent commit + sequence assignment.
4. Add the snapshot cadence worker pulling game-service exports.
5. Add the restore endpoint (snapshot import + forward replay into a target session).
6. Add the orchestrator agent-event emitter and game-service state/status emitter.
7. Add the dashboard timeline + restore UI.
8. Wire Docker Compose and run integration tests.

Rollback is removal of the new service, its database, migrations, compose entries, and the additive emitter calls in the two producers. Existing services keep working unchanged because emission is additive and ingestion is decoupled via the bus.

## Resolved Decisions

These were confirmed with the product owner and are reflected above:

- **Restore target:** support **both** modes — a new branchable session and in-place overwrite — with the mode chosen per restore (new session is the default the UI pre-selects). See Decision 7.
- **Snapshot cadence:** every **25 events / 300s**, configurable via `SNAPSHOT_EVERY_N_EVENTS` / `SNAPSHOT_MAX_INTERVAL_SECONDS`. See Decision 6.
- **Ingestion stream retention:** bounded `MAXLEN` plus consumer-lag alerting; PostgreSQL is the durable record and HTTP backfill is the recovery path. See Decision 10.
- **Restore fidelity:** restore reconstructs the **game state and the full agent conversation context** so the LLM faces an identical, replayable situation. Agent-decision events are never replayed as game-state mutations but are the source for rebuilding context. See Decisions 7 and 9.
