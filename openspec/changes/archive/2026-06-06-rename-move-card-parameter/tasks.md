## 1. Code Changes

- [x] 1.1 Rename `card_id` to `instance_id` in `MoveCardAction` model
- [x] 1.2 Update `_to_dragncards` translation to use `action.instance_id`
- [x] 1.3 Rename `card_id` to `instance_id` in `SetCardPropertyAction` model

## 2. Testing

- [x] 2.1 Update tests in `test_actions.py` to use `instance_id`
- [x] 2.2 Update tests in `test_action_translation.py` to use `instance_id`
- [x] 2.3 Update tests in `test_game_action_helpers.py` to use `instance_id`
- [x] 2.4 Update tests in `test_actions_enums.py` to use `instance_id`

## 3. Verification

- [x] 3.1 Run unit tests to verify changes
- [x] 3.2 Run integration tests to verify real DragnCards behavior