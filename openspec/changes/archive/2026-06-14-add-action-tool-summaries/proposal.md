## Why

MCP tools derived from the game-action-helpers endpoints lack summaries describing their purpose and when to use them. Without clear documentation, LLM agents struggle to choose the correct tool for Marvel Champions game actions, leading to inefficient tool use and potential errors (e.g., using `set_card_property` for flipping when `flip_card` exists).

## What Changes

- Add `summary` parameter to each `@router.post` endpoint in `game_action_helpers.py`
- Summaries will describe the tool's purpose and when to use it, based on Marvel Champions rules
- Include warnings for tools that should be avoided in favor of better alternatives (e.g., `set_card_property` vs `flip_card`)

## Capabilities

### New Capabilities

No new capabilities required - this is an improvement to existing functionality.

### Modified Capabilities

- `game-service`: Adding OpenAPI summaries to action endpoints to improve MCP tool discovery

## Impact

- `services/game-service/src/game_service/api/routers/game_action_helpers.py` - Add summary to each endpoint
- MCP clients will see improved tool descriptions in their tool discovery
- No breaking changes - summaries are optional OpenAPI metadata

## Non-goals

- No changes to action behavior or return types
- No new tools or capabilities
- No changes to the generic `/games/{session_id}/actions` endpoint