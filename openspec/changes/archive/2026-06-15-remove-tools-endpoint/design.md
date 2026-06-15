## Context

The `/tools` endpoint exists in `services/game-service/src/game_service/api/routers/meta.py` as an HTML view of MCP tools. It was marked with `include_in_schema=False`, indicating it was never intended as a public API. The endpoint uses `fastmcp.Client` to connect to the MCP server and list tools, then renders them as HTML. This duplicates the MCP tool discovery mechanism which clients already have access to through the standard MCP protocol.

## Goals / Non-Goals

**Goals:**
- Remove the redundant `/tools` endpoint from the game-service API
- Clean up unused imports and simplify the meta router

**Non-Goals:**
- Adding any replacement functionality
- Modifying MCP tool discovery (already works via MCP protocol)

## Decisions

**Decision**: Delete the endpoint rather than deprecate it
- **Rationale**: The endpoint has `include_in_schema=False` and is not referenced in any documentation or tests
- **Alternatives considered**:
  - Keep and deprecate: rejected because there's no external usage to maintain compatibility with

**Decision**: Remove the unused `fastmcp.Client` import
- **Rationale**: After removing the endpoint, the import is no longer needed
- **Alternatives considered**: None - unused imports should always be removed

## Risks / Trade-offs

- **Risk**: Someone might be using this endpoint for debugging
- **Mitigation**: The endpoint was already hidden from the OpenAPI schema, so usage would be intentional and known. Developers can use MCP client tools directly for debugging instead.