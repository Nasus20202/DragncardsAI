## Context

The game-service currently owns session coordination in memory. That makes the service stateful at the process level and couples availability to the lifetime of a single container. This change introduces Valkey as a shared coordination store so the service can be restarted without losing its session registry or connection mapping.

## Goals / Non-Goals

**Goals:**
- Move session coordination state out of the game-service process.
- Keep the public HTTP and MCP behavior unchanged.
- Run Valkey in a separate infra Docker Compose stack that starts before the main application stack.
- Make restarts of game-service recoverable without manual session reconstruction.

**Non-Goals:**
- Replacing DragnCards as the source of game state.
- Changing Phoenix protocol behavior or DragnCards room semantics.
- Adding distributed worker orchestration beyond the coordination store.
- Persisting full game state in Valkey.

## Decisions

- Use Valkey as the coordination backend.
  - Rationale: it is lightweight, Docker-friendly, and fits ephemeral session metadata better than PostgreSQL.
  - Alternatives considered: PostgreSQL was rejected because it is better suited to durable relational data than fast ephemeral coordination; filesystem state was rejected because it does not survive container replacement cleanly.

- Keep DragnCards as the source of truth for live game state.
  - Rationale: the game-service should coordinate connections, not duplicate game engine behavior.
  - Alternatives considered: mirroring full session state into Valkey was rejected because it would create another state replication problem and increase divergence risk.

- Model Valkey data as coordination records keyed by session ID.
  - Rationale: the service needs fast lookup of active sessions, connection metadata, and recovery hints.
  - Alternatives considered: a single shared blob was rejected because it would make partial updates and recovery harder to reason about.

- Wire Valkey into `docker-compose.infra.yaml` as a first-class service.
  - Rationale: infra dependencies should be started independently from the app stack while still being scriptable.
  - Alternatives considered: keeping Valkey inline in `docker-compose.yaml` was rejected because it couples infra bootstrapping to the main service stack; manual local setup was rejected because it is not repeatable.

- Start infra services through `scripts/docker-infrastructure.sh`.
  - Rationale: the existing infra script is the natural place to bring up shared support services before the app stack.
  - Alternatives considered: adding a new one-off startup path was rejected because it would split the operator workflow.

## Risks / Trade-offs

- [Session metadata drift] -> Keep Valkey writes atomic and treat DragnCards as the authority for live game state.
- [Restart recovery edge cases] -> Rebuild ephemeral in-process caches from Valkey at startup and verify session ownership before reuse.
- [Upstream protocol behavior changes] -> Limit the change to coordination storage so Phoenix message handling stays isolated and easier to debug.
- [Operational dependency on Valkey] -> Provide compose defaults, health checks, and infra-script ordering so local startup failures are obvious.

## Migration Plan

1. Add Valkey to `docker-compose.infra.yaml` and inject connection settings into game-service.
2. Move session registry and connection metadata reads/writes to Valkey.
3. Keep in-process caches only as derived runtime accelerators.
4. Update infra scripts so Valkey starts before the main stack.
5. Verify the service can restart and rehydrate session coordination data from Valkey.
6. Roll back by switching the service back to the previous in-process implementation if Valkey recovery fails.

## Open Questions

- What exact session fields should be stored in Valkey versus reconstructed from DragnCards?
- Should the Valkey service use authentication in local development, or remain open on the Docker network only?
