## Why

The game-service currently keeps session and connection coordination in process, which ties runtime state to a single container and makes restarts disruptive. Moving that coordination into Valkey will let the service run statelessly while preserving active game connections across process restarts.

## What Changes

- Move game-service session and connection coordination data out of process and into Valkey.
- Add Valkey to a separate infra Docker stack in `docker-compose.infra.yaml`.
- Start the infra stack from the repository infra scripts before the main stack.
- Configure game-service to read and write session coordination state through Valkey instead of process-local storage.
- Keep DragnCards integration behavior unchanged from the client perspective.
- **BREAKING**: game-service will no longer rely on in-memory session state as the source of truth.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `game-service`: session lifecycle and WebSocket connection management will use an external coordination store rather than process-local state.
- `infrastructure`: local Docker Compose will split Valkey into an infra stack and wire game-service to it.

## Impact

- `services/game-service/`: session manager, connection pool, and configuration handling.
- `docker-compose.infra.yaml` and infra scripts: add a Valkey service and startup wiring.
- Runtime dependency footprint: introduces Valkey as a required local service for development.
- Operational behavior: game-service becomes restart-tolerant with respect to session coordination state.
