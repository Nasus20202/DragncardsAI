## 1. Action Model Foundations

- [x] 1.1 Inventory current action definitions and `get_session_actions` schema fields in `services/game-service`
- [x] 1.2 Define per-action request/response models in `services/game-service` aligned with the session action schemas from the example response JSON

## 2. Typed Action Helpers

- [x] 2.1 Implement typed helper functions in `game_actions.py` that wrap the generic action execution path, writing functions explicitly (no dynamic generation)
 - [x] 2.2 Add a raw action helper that accepts arbitrary DragnLang action lists

## 3. MCP Tool Surface

 - [x] 3.1 Expose one MCP tool per typed action helper with JSON Schema parameters
 - [x] 3.2 Update tool discovery tests or fixtures to cover typed action helpers

## 4. Validation and Coverage

 - [x] 4.1 Add unit tests validating required fields and defaults for typed action requests
 - [x] 4.2 Add integration tests that execute a representative typed action against DragnCards
