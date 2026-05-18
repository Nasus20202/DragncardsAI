## 1. Database Schema

- [x] 1.1 Create `mcp_registries` table migration (name, transport, server_url, headers_json)
- [x] 1.2 Create `session_enabled_mcps` table migration (session_id, mcp_name, enabled)
- [x] 1.3 Drop `session_mcp_assignments` table migration

## 2. Model Layer

- [x] 2.1 Add `McpRegistry` model class in models.py
- [x] 2.2 Add `SessionEnabledMcp` model class in models.py
- [x] 2.3 Remove `SessionMcpAssignment` model class

## 3. Repository Layer

- [x] 3.1 Implement `add_mcp_registry()` method in sessions.py
- [x] 3.2 Implement `list_mcp_registries()` method in sessions.py
- [x] 3.3 Implement `remove_mcp_registry()` method in sessions.py
- [x] 3.4 Implement `enable_mcp_for_session()` method in sessions.py
- [x] 3.5 Implement `list_session_enabled_mcps()` method in sessions.py
- [x] 3.6 Implement `get_session_enabled_mcp_state()` method in sessions.py

## 4. MCP Client

- [x] 4.1 Rename `StreamableHttpMcpClient` to `McpClient` in client.py
- [x] 4.2 Add SSE transport support using `mcp.client.sse`
- [x] 4.3 Add transport dispatch in `_session()` context manager

## 5. API Endpoints

- [x] 5.1 Add `GET /mcps` global registry list endpoint while preserving `POST /sessions/{id}/mcps`
- [x] 5.2 Add `POST /mcps` to add MCP to registry
- [x] 5.3 Add `DELETE /mcps/{mcp_name}` to remove from registry
- [x] 5.4 Modify `GET /sessions/{id}/mcps` to show enablement state
- [x] 5.5 Add `PATCH /sessions/{id}/mcps/{mcp_name}` to enable/disable MCP
- [x] 5.6 Preserve `DELETE /sessions/{id}/mcps/{mcp_name}` as a session-disable endpoint

## 6. Default MCP Initialization

- [x] 6.1 Add startup hook to create default game-service MCP
- [x] 6.2 Use `game_service_mcp_url` from settings
- [x] 6.3 Auto-enable non-custom default MCPs for sessions

## 7. Tool Catalog Integration

- [x] 7.1 Modify `McpToolCatalog.list_session_tools()` to use enabled MCPs
- [x] 7.2 Update session tool query to join enabled MCPs

## 8. Spawn Subagent Integration

- [x] 8.1 Modify `spawn_subagent` to copy enabled MCPs to child session

## 9. Tests

- [x] 9.1 Unit tests for new repository methods
- [x] 9.2 Unit tests for SSE transport helpers in `McpClient`
- [x] 9.3 Integration tests for new MCP endpoints
- [x] 9.4 Integration test for spawn_subagent MCP inheritance
