## Why

The current `get_game_state` output is verbose and deeply nested, making it difficult for LLMs to parse and reason about game state efficiently. This complicates prompt construction and increases token usage. Simplifying the output focuses on only the most relevant state information for decision-making.

## What Changes

- **New response model**: Create a simplified schema that extracts essential Marvel Champions state (players, zones with cards, round/mode, HP) while dropping internal fields
- **Non-breaking**: Add as an optional transformation layer; existing `get_game_state` behavior unchanged for backward compatibility
- **Zone mapping**: Map cards into their zone arrays directly (hand, play, deck, discard, encounter) instead of requiring LLM to join `cardById` with group lookups
- **Visible cards only**: Filter out attachment tucked-under relationships to present only cards visible as top-level cards

## Capabilities

### New Capabilities
- `simplified-game-state`: Provide a streamlined representation of Marvel Champions game state for LLM consumption

### Modified Capabilities
- `game-service`: Extend state observation to support simplified output format for Marvel Champions sessions

## Impact

- **Affected code**: `game_service/logic/actions.py` and/or new `game_service/logic/state_simplifier.py`
- **APIs**: New optional query parameter or separate endpoint for simplified output
- **MCP tools**: `get_game_state_marvel_champions` variant with simplified schema
- **Dependencies**: None (uses existing plugin metadata and state structures)