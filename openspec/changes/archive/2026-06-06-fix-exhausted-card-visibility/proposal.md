## Why

Exhausted cards in Marvel Champions are intentionally visible to both players - the card name and all details remain public information. The current implementation incorrectly hides exhausted cards because it checks `rotation != 0` as the condition for hiding, but `rotation` changes for both facedown cards AND exhausted cards. This breaks LLM decision-making since the bot can't see its exhausted upgrades/supports.

## What Changes

- **Fix**: Change the condition for hiding cards from `rotation != 0` to only hide truly facedown cards (where the card is physically rotated and its identity is concealed from players)
- **Keep**: The `exhausted` boolean field will correctly reflect whether an upgrade/support is exhausted
- **Keep**: Player/encounter cards still merge into HIDDEN as before

## Capabilities

### New Capabilities
None - this is a bug fix to existing behavior.

### Modified Capabilities
- `simplified-game-state`: The requirement for when cards are hidden changes - now only facedown cards are hidden, not exhausted cards

## Impact

- **API**: `/games/{session_id}/state` response will now correctly show exhausted cards
- **Behavior**: LLM agents will be able to see exhausted upgrades/supports in their play area
- **Code**: `services/game-service/src/game_service/api/routers/game_state.py:_simplify_marvel_state` logic