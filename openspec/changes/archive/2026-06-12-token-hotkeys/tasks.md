## 1. Code Changes

- [x] 1.1 Add `ModifyTokensAction` model to actions.py with `instance_id`, `token_type`, and `amount` fields
- [x] 1.2 Add `token_type` enum with Marvel Champions token types (threat, damage, stunned, confused, toughness, ally, hero_ally, villain_ally)
- [x] 1.3 Add DragnLang translation in `_to_dragncards` using `INCREASE_VAL`
- [x] 1.4 Add `ModifyTokensAction` to `GameAction` union type
- [x] 1.5 Add `ModifyTokensAction` to `ACTION_TYPES` tuple
- [x] 1.6 Add `/games/{session_id}/actions/modify_tokens` endpoint in game_action_helpers.py

## 2. Testing

- [x] 2.1 Add test for modify_tokens action translation (positive and negative amounts)
- [x] 2.2 Add test for modify_tokens action helper endpoint
- [x] 2.3 Add integration test for modify_tokens with real DragnCards

## 3. Verification

- [x] 3.1 Run unit tests to verify changes
- [x] 3.2 Run integration tests to verify real DragnCards behavior
- [x] 3.3 Verify MCP tool `modify_tokens` is exposed