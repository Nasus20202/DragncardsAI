## Why

Marvel Champions action tools return success even when actions fail due to invalid inputs (e.g., nonexistent card ID). DragnCards puts action error messages in the `game.messages` array rather than sending alerts, but the game-service wasn't extracting these. This makes it impossible for callers to detect and handle action failures.

## What Changes

- Added `_check_action_messages()` method to `session.py` to extract "Error in Marvel Champions triggered" messages
- Added unit tests for action error responses in `test_game_action_helpers.py`
- Added integration test verifying error messages are returned when actions fail

## Capabilities

### New Capabilities
None - this is testing infrastructure for existing capabilities

### Modified Capabilities
None

## Impact

- **Files modified**: `services/game-service/src/game_service/logic/session.py`, `services/game-service/tests/unit/test_game_action_helpers.py`, `services/game-service/tests/integration/test_actions.py`

### Non-goals
- No changes to alert-based error capture (remains unchanged)