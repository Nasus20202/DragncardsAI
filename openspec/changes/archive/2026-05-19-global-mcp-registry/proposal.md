## Why

The current per-session MCP assignment model doesn't scale well for common use cases. Every session must individually add the game-service MCP, MCP configurations cannot be shared across sessions, and SSE transport is accepted in schema but was not actually supported by the client.

## What Changes

- **BREAKING**: Replace per-session `session_mcp_assignments` with a global `mcp_registries` table plus `session_enabled_mcps`
- Add a global MCP registry with CRUD endpoints for managing available MCPs
- Add a `custom` flag so shipped default registries such as `game-service` can be protected from deletion
- Auto-create the default `game-service` MCP from config on startup
- Auto-enable non-custom default MCPs for new sessions and backfill them for older sessions when loaded
- Add `McpTransport.SSE` support in the runtime MCP client
- Keep explicit session enable/disable support while preserving session-scoped add/remove convenience endpoints

## Capabilities

### New Capabilities
- `global-mcp-registry`: Global MCP management with session-level enablement. Manages a global registry of MCP servers that can be enabled or disabled per session.

### Modified Capabilities
- `agent-orchestrator`: MCP assignment changes from fully per-session definitions to a global registry with per-session enablement. SSE transport support is added.

## Impact

- **Database**: New `mcp_registries` table with `custom`, new `session_enabled_mcps` table, `session_mcp_assignments` dropped
- **API**:
  - New `GET /mcps` to list the global registry
  - New `POST /mcps` to add or update a global registry entry
  - New `DELETE /mcps/{mcp_name}` to remove a custom registry entry
  - New `PATCH /sessions/{session_id}/mcps/{mcp_name}` for explicit enable/disable
  - `POST /sessions/{session_id}/mcps` remains available and upserts a registry entry before enabling it for that session
  - `DELETE /sessions/{session_id}/mcps/{mcp_name}` remains available and disables the MCP for that session
- **Client**: `StreamableHttpMcpClient` becomes `McpClient` with runtime transport dispatch and SSE support
- **Session spawn**: Child sessions inherit the parent's enabled MCP state
