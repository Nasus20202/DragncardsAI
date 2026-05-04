## 1. Snapshot Models And Session Methods

- [x] 1.1 Add API and session-layer models for a versioned game-state snapshot envelope with plugin identity and inner `game` payload
- [x] 1.2 Move session orchestration code into a clearer logic-oriented module boundary while keeping imports stable during the refactor
- [x] 1.3 Add `GameSession`-equivalent export logic to fetch current state and normalize it into the snapshot envelope
- [x] 1.4 Add snapshot load logic to validate plugin/version compatibility and send DragnCards `game_action` with action type `set_game`
- [x] 1.5 Move DragnCards bootstrap/transport helpers out of the mixed-purpose `session/` package into a backend-specific module boundary
- [x] 1.6 Add unit tests for snapshot export normalization and load-state request construction
- [x] 1.7 Add unit tests for load-state rejection on unsupported snapshot version and plugin mismatch

## 2. HTTP API And MCP Exclusion

- [x] 2.1 Add HTTP endpoints under `/games/{session_id}/...` for exporting and loading game-state snapshots
- [x] 2.2 Add request and response validation/error handling for invalid snapshot documents and incompatible target sessions
- [x] 2.3 Update FastMCP route mapping so snapshot export/load endpoints are excluded from MCP tool generation
- [x] 2.4 Add unit tests covering the new HTTP endpoints with mocked sessions
- [x] 2.5 Add unit tests asserting MCP tool discovery does not expose snapshot export/load operations

## 3. Router Consolidation

- [x] 3.1 Move room-control and room-event endpoint definitions into the main game-session router module
- [x] 3.2 Remove `room_control` and `room_events` router wiring from `api/app.py` and `api/routers/__init__.py`
- [x] 3.3 Verify existing endpoint paths and operation IDs remain unchanged for non-snapshot routes
- [x] 3.4 Update affected API router tests to match the consolidated module layout

## 4. Package Boundary Refactor

- [x] 4.1 Introduce clearer internal module boundaries for service logic, DragnCards adapters, and catalog providers without changing public API paths
- [x] 4.2 Keep compatibility imports or facades as needed so the refactor can land incrementally without breaking unrelated code
- [x] 4.3 Update internal imports and tests to use the new package layout for touched modules

## 5. Card Catalog Refactor

- [x] 5.1 Replace `session/card_db.py` with a plugin-aware card catalog module boundary that preserves current Marvel Champions search results
- [x] 5.2 Keep `/cards` endpoint behavior stable while routing lookups through the new catalog abstraction
- [x] 5.3 Add unit tests for the Marvel Champions catalog provider and plugin dispatch behavior
- [x] 5.4 Add regression tests for `/cards` search responses after the refactor

## 6. Integration Coverage

- [x] 6.1 Add integration coverage for exporting state from a live session and loading it into a compatible live session
- [x] 6.2 Add integration coverage for rejected snapshot import when plugin identity or snapshot version is incompatible
- [x] 6.3 Add integration coverage that existing MCP tools still work while snapshot import/export remain absent from the generated MCP surface
