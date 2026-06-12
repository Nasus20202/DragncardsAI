## 1. Implementation

- [x] 1.1 Add `_check_action_messages()` to extract errors from `game.messages` in session.py
- [x] 1.2 Call `_check_action_messages()` after action execution in both success and timeout recovery paths

## 2. Testing

- [x] 2.1 Add unit test verifying error field is populated when action errors appear in messages
- [x] 2.2 Add integration test verifying error handling with real DragnCards