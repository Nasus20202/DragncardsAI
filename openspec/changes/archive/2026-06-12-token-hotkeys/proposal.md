## Why

Marvel Champions gameplay involves frequently adding or removing tokens from cards (threat, damage, stunned, confused, toughness, etc.). While the DragnCards Web UI provides Token Hotkeys for this purpose, the game-service lacks a typed endpoint to programmatically add/remove tokens, forcing callers to use the generic `raw` action or `set_card_property` action.

## What Changes

- Add `ModifyTokensAction` model with `instance_id`, `token_type` (enum), and `amount` fields
- Add `/games/{session_id}/actions/modify_tokens` HTTP endpoint
- Add DragnLang translation that uses `INCREASE_VAL` on `/cardById/{id}/tokens/{type}`
- Add `token_type` enum for Marvel Champions tokens (threat, damage, stunned, confused, toughness, ally, hero_ally, villain_ally)

## Capabilities

### New Capabilities
- `token-modification`: Typed action for adding/removing tokens from cards in DragnCards games

### Modified Capabilities
- `typed-game-actions`: Extend with additional Marvel Champions specific action type

## Impact

- **Files added**: `ModifyTokensAction` in `src/game_service/logic/actions.py`
- **Endpoints added**: `modify_tokens` in `src/game_service/api/routers/game_action_helpers.py`
- **Tests added**: Unit tests for translation, integration tests for endpoint

### Non-goals
- No UI changes
- No bulk token operations (one action per card/token type)
- No validation of token amounts beyond the action's own logic