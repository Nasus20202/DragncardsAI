## 1. MCP tool surface updates

- [x] 1.1 Remove room-control MCP tool registrations (reset, seat, spectator, replay, alert, player-count, close-room) from the game-service MCP tool registry
- [x] 1.2 Ensure MCP tool discovery only exposes create/list/delete game, get game state, and execute action

## 2. Room creation seating behavior

- [x] 2.1 Verify POST /games MCP create_game flow assigns the model to the first available seat and update implementation if needed
- [x] 2.2 Add/update MCP unit tests for create_game confirming auto-seat behavior

## 3. Room attachment seating behavior

- [x] 3.1 Verify POST /games/attach MCP attach_game flow assigns the model to the first available seat and update implementation if needed
- [x] 3.2 Add/update MCP unit tests for attach_game confirming auto-seat behavior

## 4. Documentation and spec alignment

- [x] 4.1 Update MCP documentation to remove room-control endpoints and describe the simplified flow
- [x] 4.2 Adjust MCP contract tests to reflect the reduced tool surface (including negative coverage for removed tools)
