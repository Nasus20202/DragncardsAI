## Why

The `move_card` and `set_card_property` actions use `card_id` as their parameter names, but the game state JSON returns `instanceId` for card instances. This naming mismatch creates confusion for users who need to map between action parameters and state fields.

## What Changes

- **BREAKING**: Rename `card_id` parameter to `instance_id` in `MoveCardAction` and `SetCardPropertyAction` models and all related code
- Update the DragnLang translation to use the new parameter name
- Update OpenAPI schema and MCP tool definitions
- Update tests to use the new parameter name

## Capabilities

### Modified Capabilities
- `game-service`: Card action parameter naming for consistency with game state JSON (`instanceId`)