## Why

The current `get_game_state` output is verbose and deeply nested, making it difficult for LLMs to parse and reason about game state efficiently. This complicates prompt construction and increases token usage. Simplifying the output focuses on only the most relevant state information for decision-making.

## What Changes

- **New response model**: Create a simplified schema that extracts essential Marvel Champions state (players, zones with cards, round/mode, HP) while dropping internal fields
- **Always simplified for Marvel Champions**: The endpoint returns the streamlined format automatically for MC sessions (no opt-in required)
- **Zone mapping**: Map cards into their zone arrays directly (hand, play, deck, discard, encounter) instead of requiring LLM to join `cardById` with group lookups
- **Visible cards only**: Filter out attachment tucked-under relationships to present only cards visible as top-level cards

## Capabilities

### New Capabilities
- `simplified-game-state`: Provide a streamlined representation of Marvel Champions game state for LLM consumption

### Modified Capabilities
- `game-service`: Transform state observation to always return simplified format for Marvel Champions sessions

## Impact

- **Affected code**: `game_service/api/routers/game_state.py`
- **APIs**: `GET /games/{id}/state` returns simplified state for Marvel Champions (breaking change for clients expecting raw state)
- **MCP tools**: `get_game_state` returns simplified format for Marvel Champions sessions
- **Dependencies**: None (uses existing plugin metadata and state structures)