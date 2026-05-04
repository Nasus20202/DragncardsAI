## Why

The game-service can observe and mutate live DragnCards sessions, but it cannot capture a reusable setup snapshot or restore one into a session. That makes scenario setup, repeatable test fixtures, and scripted game preparation harder than they need to be, especially as the service starts supporting more than one game.

## What Changes

- Add an HTTP endpoint to export a session's current game state as a reusable setup snapshot.
- Add an HTTP endpoint to load a previously exported setup snapshot into a session so callers can automate scenario and board setup.
- Keep state import/export HTTP-only and explicitly exclude those operations from MCP tool exposure.
- Consolidate API routing around game-session operations so `room_control` and `room_events` no longer need to exist as separate routers.
- Refactor the current `session/` package so session orchestration, DragnCards transport concerns, and catalog/search code no longer live in one directory; move toward clearer `logic/` and `dragncards` transport boundaries.
- Refactor card-search loading so the service can evolve from a Marvel Champions specific data source toward plugin-aware card catalog support.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `game-service`: add HTTP-only game state export/import workflows for setup automation, and define that privileged setup endpoints are not exposed as MCP tools.

## Impact

- `services/game-service/src/game_service/api/routers/games.py` and related API models for the new import/export endpoints and router consolidation.
- `services/game-service/src/game_service/mcp/server.py` and/or FastMCP route mapping so setup endpoints stay out of MCP.
- `services/game-service/src/game_service/session/` and its successors for moving session lifecycle logic away from unrelated transport and catalog helpers.
- `services/game-service/src/game_service/dragncards/` and/or `services/game-service/src/game_service/logic/` style packages for clearer inbound/outbound transport and orchestration boundaries.
- Card-search plumbing moved out of `session/card_db.py` into a plugin-aware catalog module.
- Tests covering snapshot export/import behavior, MCP exclusion, and card catalog refactoring boundaries.

## Non-goals

- Defining a generic cross-service persistence format for every possible DragnCards payload beyond what game-service needs for setup snapshots.
- Adding MCP tools for privileged setup operations.
- Solving full multi-game plugin discovery and card ingestion for every game in this change.
- Renaming every top-level package in game-service to a brand new directional taxonomy in one pass.
