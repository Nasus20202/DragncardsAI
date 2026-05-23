## Why

The MCP surface currently duplicates game-room management endpoints that are no longer needed because room creation already assigns the model to the first available seat. Removing these endpoints reduces complexity, avoids conflicting pathways, and clarifies the intended flow for model-driven sessions.

## What Changes

- **BREAKING**: Remove MCP endpoints related to game-room management (spectator, replay, player-count, seat assignment, and similar controls).
- MCP room creation and attachment behavior are the entry points: POST /games creates the room and assigns the model to the first available seat; POST /games/attach assigns the model to the first available seat in an existing room.
- Update MCP documentation to reflect the reduced endpoint set and new expectations around room assignment.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `game-service`: MCP API requirements remove game-room endpoints and specify auto-seat behavior for room creation and attachment.

## Impact

- MCP client integrations that rely on spectator, replay, player-count, or seat assignment endpoints must remove those calls.
- `services/game-service/` MCP tool registry and documentation will be updated; tests covering MCP endpoint availability will change.

## Non-goals

- No changes to DragnCards backend behavior or Phoenix channel protocol.
- No changes to HTTP REST API endpoints outside the MCP interface.
