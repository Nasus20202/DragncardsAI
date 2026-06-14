## Context

The Game Service exposes three endpoints that provide low-level access to DragnCards internals:
1. `GET /games/{session_id}/state/raw` - Returns raw, untransformed game state
2. `POST /games/{session_id}/actions` - Generic action execution with arbitrary action payloads
3. `POST /games/{session_id}/actions/raw` - Direct DragnLang action list execution

These endpoints are intended for debugging and development purposes. The MCP interface uses FastMCP's auto-generation from OpenAPI schema, which would expose these endpoints as MCP tools unless explicitly excluded.

## Goals / Non-Goals

**Goals:**
- Block MCP access to the three debug endpoints
- Mark these endpoints as "DEBUG ONLY" in OpenAPI documentation
- Keep the endpoints fully functional via HTTP

**Non-Goals:**
- Removing the endpoints entirely
- Adding authentication/authorization for these endpoints
- Modifying any other endpoints or their MCP exposure

## Decisions

### Decision: Use RouteMap.MCPType.EXCLUDE for MCP blocking
The MCP server uses FastMCP's `RouteMap` pattern to control which OpenAPI routes become MCP tools. Adding RouteMap entries with `MCPType.EXCLUDE` is the cleanest approach since it:
- Controls MCP exposure at the gateway level
- Does not modify the HTTP endpoint behavior
- Follows existing patterns in the codebase (snapshot, reset, seat, etc.)

**Alternative considered:** Modifying the endpoint decorators with `include_in_schema=False` — Rejected because this would hide the endpoints from both MCP and HTTP documentation, but HTTP still needs to access them.

### Decision: Use OpenAPI description field for "DEBUG ONLY" marker
Adding `description="DEBUG ONLY: ..."` to endpoint definitions provides inline documentation without affecting the route behavior. This appears in Swagger UI and the auto-generated OpenAPI schema.

**Alternative considered:** Custom OpenAPI extension field — Rejected as less standard and not visible in typical API docs.

## Risks / Trade-offs

- **Risk:** Developers may forget that endpoints are HTTP-only and expect MCP parity
  - Mitigation: Clear "DEBUG ONLY" markers in the documentation and this design record
- **Risk:** Future endpoints may need similar treatment but be missed
  - Mitigation: Consider documenting this pattern in AGENTS.md or creating a shared exclusion list