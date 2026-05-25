## Why

LLM clients can already discover prebuilt deck catalogs, but they still cannot load a chosen deck into an existing game session the same way the DragnCards frontend can. Adding a session-scoped load tool removes that gap and makes deck setup usable end to end from MCP.

## What Changes

- Add an MCP tool that loads a specific prebuilt deck by deck id into an existing game session.
- Make the tool session-scoped so it targets a concrete `session_id` rather than creating a new game.
- Reuse the same underlying load behavior used by the DragnCards frontend's "Load prebuilt deck" flow.
- Return a simple success/failure response tied to the target session.
- Keep the feature focused on Marvel Champions prebuilt decks and do not change deck catalog discovery.

## Capabilities

### New Capabilities
- `load-prebuilt-deck-tool`: load a specific prebuilt deck into an existing Marvel Champions session via MCP.

### Modified Capabilities
- `game-service`: extend MCP tool discovery and session actions so prebuilt deck loading is exposed as a first-class session operation.

## Impact

- `services/game-service/` MCP tool registration and session action handling.
- Marvel Champions plugin deck-loading data paths.
- OpenSpec requirements for the game-service MCP surface.
