## Why

The game-service currently exposes generic game actions (`move_card`, `draw_card`, `set_card_property`) and a `raw` action type for arbitrary DragnLang. Marvel Champions has specific gameplay actions defined in the plugin's actionLists.json (exhaust, flip, deal encounter cards, etc.) that would benefit from typed action models, making them discoverable and easier to use.

## What Changes

- Add typed action models for Marvel Champions gameplay actions: `exhaust_card`, `ready_card`, `flip_card`, `discard_random_card`, `shuffle_into_deck`, `zero_tokens`, `deal_encounter`, `draw_boost`, `player_end_phase`
- Each action maps to a DragnLang operation from the plugin's actionLists.json
- Actions follow the same pattern as existing typed actions (move_card, draw_card, etc.)
- No breaking changes - these are additive new capabilities

## Capabilities

### Modified Capabilities
- `game-service`: Typed Marvel Champions actions

## Impact

- `services/game-service/src/game_service/logic/actions.py`: New action models
- MCP tool schema automatically updated via existing discriminated union
- Tests for new action types