## 1. MCP Endpoint Exclusions

- [x] 1.1 Add RouteMap.EXCLUDE for `/games/{session_id}/state/raw` to mcp/server.py
- [x] 1.2 Add RouteMap.EXCLUDE for `/games/{session_id}/actions` to mcp/server.py
- [x] 1.3 Add RouteMap.EXCLUDE for `/games/{session_id}/actions/raw` to mcp/server.py

## 2. Documentation Markers

- [x] 2.1 Add "DEBUG ONLY" description to `get_raw_game_state` endpoint in game_state.py
- [x] 2.2 Add "DEBUG ONLY" description to `execute_action` endpoint in game_actions.py
- [x] 2.3 Add "DEBUG ONLY" description to `raw_action` endpoint in game_action_helpers.py

## 3. Testing

- [x] 3.1 Add unit test to verify MCP tool discovery excludes the three debug endpoints
- [x] 3.2 Verify HTTP requests to debug endpoints still work correctly