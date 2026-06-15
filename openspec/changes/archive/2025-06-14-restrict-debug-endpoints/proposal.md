## Why

Certain endpoints expose raw game state and direct action execution capabilities that are intended for debugging purposes. These endpoints should not be accessible through the MCP interface to prevent LLM agents from bypassing the controlled action abstractions, ensuring they only use the intended typed actions.

## What Changes

- Make `/games/{session_id}/state/raw` endpoint inaccessible via MCP (keep HTTP)
- Make POST `/games/{session_id}/actions` inaccessible via MCP (keep HTTP)
- Make `/games/{session_id}/actions/raw` endpoint inaccessible via MCP (keep HTTP)
- Add "DEBUG ONLY" markers in API documentation for these endpoints
- Update MCP tool registration to exclude these endpoints

## Capabilities

### New Capabilities

This change modifies existing capabilities without introducing new ones.

### Modified Capabilities

- `game-service`: Restrict MCP endpoint exposure and add debug-only documentation markers

## Impact

- `services/game-service/`: MCP tool registration logic, OpenAPI documentation
- No database schema changes required