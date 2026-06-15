## Why

The `/tools` endpoint in the game-service is a debug-only HTML view that duplicates the MCP tool discovery mechanism. It has `include_in_schema=False` and serves no functional purpose beyond debugging. The endpoint exposes MCP tools in an HTML format that conflicts with the architectural principle that MCP clients should discover tools via the MCP protocol itself, not through HTTP endpoints. Removing this endpoint simplifies the API surface and eliminates redundant code.

## What Changes

- **Remove** the `/tools` GET endpoint from `services/game-service/src/game_service/api/routers/meta.py`
- Remove the endpoint requires no spec-level changes since it was already excluded from the OpenAPI schema and not referenced in any capability requirements

## Capabilities

### New Capabilities
<!-- None - this is a removal operation -->

### Modified Capabilities
<!-- None - no spec-level requirement changes -->
- The `/tools` endpoint was never documented as a required capability in `openspec/specs/game-service/spec.md`

## Impact

- **Affected code**: `services/game-service/src/game_service/api/routers/meta.py` (lines 590-615)
- **Tests**: No test coverage for this endpoint currently exists
- **Documentation**: The endpoint was marked `include_in_schema=False` and is not in API docs
- **Dependencies**: None - the endpoint imports from `fastmcp.Client` but this is only used for this endpoint