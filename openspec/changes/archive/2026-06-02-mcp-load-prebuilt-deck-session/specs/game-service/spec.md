## MODIFIED Requirements

### Requirement: MCP protocol compliance
The Game Service SHALL implement the Model Context Protocol, exposing game capabilities as MCP tools accessible to any MCP-compatible client.

#### Scenario: MCP client connection
- **WHEN** an MCP client connects to the Game Service
- **THEN** the server SHALL complete the MCP handshake and advertise available tools

#### Scenario: Tool discovery
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL return tool definitions for game session management (`create_game`, `list_games`, `delete_game`), state observation (`get_game_state`), action execution (`execute_action`), card catalog discovery (`list_card_providers`, `search_cards_<provider>`), and prebuilt deck loading (`load_prebuilt_deck`), each with proper JSON Schema parameter descriptions

#### Scenario: Tool discovery excludes room-control operations
- **WHEN** an MCP client requests the list of available tools
- **THEN** the server SHALL NOT expose room-control tools including reset, seat assignment, spectator toggles, player-count changes, replay saves, alert broadcasting, or room closure

#### Scenario: MCP error handling
- **WHEN** the Game Service encounters an error processing an MCP tool call
- **THEN** it SHALL return the error as an MCP error response with a descriptive message

#### Scenario: Setup import and export excluded from MCP
- **WHEN** an MCP client requests the list of available tools
- **THEN** the Game Service SHALL NOT expose game-state export or load-state operations through MCP discovery

### Requirement: Session action catalog exposes plugin-specific metadata
The Game Service SHALL make `GET /games/{session_id}/actions` return the global action catalog plus plugin-specific action metadata and affordances for the session's plugin.

#### Scenario: Session action catalog includes plugin-defined action metadata
- **WHEN** a client sends `GET /games/{session_id}/actions` for a Marvel Champions session
- **THEN** the response SHALL include plugin-specific metadata for the session's plugin, including the relevant named action lists, hotkeys, touch-bar entries, default actions, player-count layouts, and load-group information that the provider can derive

#### Scenario: Session action catalog preserves generic execute-action schemas
- **WHEN** a client sends `GET /games/{session_id}/actions`
- **THEN** the response SHALL still include the same generic typed action schemas and generic DragnLang operation catalog returned by `GET /actions`

#### Scenario: Unknown plugin yields only generic catalog
- **WHEN** a session's plugin has no registered provider metadata
- **THEN** the Game Service SHALL return the generic action catalog and empty plugin-specific metadata collections instead of failing the request
