## Why

LLM clients can find prebuilt decks and set catalogs, but they still cannot trigger the actual deck-load action against a live game session. Adding a session-scoped deck-loading tool closes that gap and makes setup automation behave like the DragnCards frontend.

## What Changes

- Add an MCP tool that loads a specific prebuilt deck into an existing game session by deck id.
- Require a target `session_id` so the tool operates on a specific live room.
- Reuse the same underlying deck-loading behavior as the DragnCards frontend's "Load prebuilt deck" option.
- Return a success acknowledgment tied to the target session after the load completes.
- Keep the feature focused on Marvel Champions prebuilt decks and do not change deck discovery/catalog behavior.

## Capabilities

### New Capabilities
- `load-prebuilt-deck`: load a chosen Marvel Champions prebuilt deck into a specific game session via MCP.

### Modified Capabilities
- `game-service`: extend MCP tool discovery and session action handling so prebuilt deck loading is available as a first-class session operation.

## Impact

- `services/game-service/` MCP tool registration and session action handling.
- Marvel Champions plugin deck-loading data paths and load action wiring.
- OpenSpec requirements for the game-service MCP surface.
