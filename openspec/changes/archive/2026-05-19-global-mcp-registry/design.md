## Context

MCP assignments previously lived in the per-session `session_mcp_assignments` table. Every session had to add the `game-service` MCP individually. The transport schema already allowed `sse`, but the client path only used `streamable_http_client`, so SSE definitions were not functional.

## Goals / Non-Goals

**Goals:**
- Single global registry of MCP servers that sessions can enable or disable
- One default MCP (`game-service`) that is available immediately
- SSE transport support in the MCP client
- Child sessions inherit the parent's enabled MCPs
- Preserve a practical API path for existing dashboard and test flows

**Non-Goals:**
- Per-session private MCP definitions that bypass the registry model
- MCP authentication beyond static headers

## Decisions

### Decision 1: Global MCP Registry Table

**Chosen:** New `mcp_registries` table with `name`, `transport`, `server_url`, `headers_json`, and `custom` columns.

**Rationale:** The registry becomes the single source of truth for MCP configuration. Sessions link to registry entries through `session_enabled_mcps`. The `custom` flag protects shipped defaults such as `game-service` from accidental deletion.

**Alternatives Rejected:**
- Keep the per-session table: does not solve sharing
- Hybrid duplicated storage: adds complexity with little value

### Decision 2: Transport Client Abstraction

**Chosen:** Replace `StreamableHttpMcpClient` with `McpClient` that selects transport at runtime.

**Rationale:** This cleanly supports both `streamable-http` and `sse` in one client surface using conditional logic in `_session()`.

**Implementation:**
```python
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
```

### Decision 3: Default Game-Service MCP

**Chosen:** Auto-create the default MCP entry on app startup from `game_service_mcp_url` config and mark it `custom=False`.

**Rationale:** This removes manual setup for the primary use case and allows the service to protect the shipped default from deletion.

### Decision 4: Default MCPs Are Enabled Automatically

**Chosen:** Non-custom registries are enabled automatically for newly created sessions and are backfilled for older sessions when sessions are listed or loaded.

**Rationale:** The shipped dashboard and smoke flows assume `game-service` tools are available immediately without a separate enable step.

### Decision 5: Session Enablement Tracking

**Chosen:** `session_enabled_mcps` stores `session_id`, `mcp_name`, and `enabled`.

**Rationale:** Sessions can see all registered MCPs, but custom registries remain opt-in while default non-custom registries come pre-enabled.

### Decision 6: Preserve Session-Scoped MCP Add/Remove Endpoints

**Chosen:** Keep `POST /sessions/{session_id}/mcps` as a convenience endpoint that upserts a registry entry and enables it for the session, and keep `DELETE /sessions/{session_id}/mcps/{mcp_name}` as a session-disable endpoint.

**Rationale:** This preserves compatibility with existing dashboard and test flows while still moving the source of truth to the global registry.

## Risks / Trade-offs

- **Breaking Change**: the old table is dropped; dev/test data loss is acceptable
- **Mixed API surface**: both global and session-scoped MCP endpoints exist, which is less pure conceptually but lowers migration cost
- **SSE transport maturity**: start with basic support and expand if real-world edge cases appear
- **Child session inheritance**: copying enabled state is simple and fits current `spawn_subagent` behavior

## Migration Plan

1. Deploy the new schema.
2. Optionally translate existing dev data into registry entries.
3. Remove `session_mcp_assignments`.
