## MODIFIED Requirements

### Requirement: MCP protocol compliance
The Game Service SHALL implement the Model Context Protocol, exposing game capabilities as MCP tools accessible to any MCP-compatible client.

#### Scenario: Tool discovery
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL return tool definitions for game session management (`create_game`, `list_games`, `delete_game`), state observation (`get_game_state`), action execution (`execute_action`), typed game action helpers (one tool per action type), card catalog discovery (`list_card_providers`, `search_cards_<provider>`), and prebuilt set catalog discovery (`list_prebuilt_sets_marvel_champions`), each with proper JSON Schema parameter descriptions

#### Scenario: Tool discovery excludes room-control operations
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL NOT expose room-control tools including reset, seat assignment, spectator toggles, player-count changes, replay saves, alert broadcasting, or room closure

#### Scenario: Tool discovery excludes debug endpoints
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL NOT expose tools for `get_raw_game_state`, `execute_action` (generic), or `raw_action` endpoints

#### Scenario: MCP error handling
- **WHEN** the Game Service encounters an error processing an MCP tool call
- **THEN** it SHALL return the error as an MCP error response with a descriptive message

#### Scenario: Setup import and export excluded from MCP
- **WHEN** an MCP client requests the list of available tools
- **THEN** the Game Service SHALL NOT expose game-state export or load-state operations through MCP discovery

### Requirement: Debug endpoints are HTTP-only
The Game Service SHALL expose raw state access, generic action execution, and raw DragnLang action execution endpoints as HTTP-only for debugging purposes.

#### Scenario: Raw state endpoint accessible via HTTP
- **WHEN** a client sends `GET /games/{session_id}/state/raw` via HTTP
- **THEN** the Game Service SHALL return the raw, untransformed game state

#### Scenario: Raw state endpoint not exposed via MCP
- **WHEN** an MCP client queries available tools
- **THEN** the Game Service SHALL NOT include a tool for accessing raw game state

#### Scenario: Generic action endpoint accessible via HTTP
- **WHEN** a client sends `POST /games/{session_id}/actions` with an action payload via HTTP
- **THEN** the Game Service SHALL execute the action and return a success acknowledgment

#### Scenario: Generic action endpoint not exposed via MCP
- **WHEN** an MCP client queries available tools
- **THEN** the Game Service SHALL NOT include a tool for generic action execution

#### Scenario: Raw action endpoint accessible via HTTP
- **WHEN** a client sends `POST /games/{session_id}/actions/raw` with a DragnLang action list via HTTP
- **THEN** the Game Service SHALL execute the raw action list and return a success acknowledgment

#### Scenario: Raw action endpoint not exposed via MCP
- **WHEN** an MCP client queries available tools
- **THEN** the Game Service SHALL NOT include a tool for raw DragnLang action execution

#### Scenario: Debug endpoints marked in documentation
- **WHEN** a developer views the OpenAPI schema or API documentation
- **THEN** the three debug endpoints SHALL be annotated with "DEBUG ONLY" markers indicating they are intended for development and debugging purposes