## Context

The Marvel Champions plugin defines common gameplay actions in actionLists.json (exhaust, flip, deal encounter cards, etc.). Currently these are only accessible via the `raw` action type, requiring users to construct DragnLang manually. Adding typed actions will make these discoverable via MCP tool schemas and OpenAPI.

## Goals / Non-Goals

**Goals:**
- Add typed actions for Marvel Champions gameplay patterns
- Make actions discoverable via tool schemas
- Reduce cognitive load for action construction

**Non-Goals:**
- Cover every possible DragnLang operation
- Add plugin-specific actions that change between scenarios
- Modify existing game-service core logic

## Decisions

### Add Marvel Champions specific typed actions

- **Why**: Common gameplay actions like exhaust, flip, and deal encounter are frequently used but require manual DragnLang. Typed actions provide better discoverability.
- **Alternative**: Only use `raw` action type - Rejected because it requires users to understand DragnLang syntax

## Risks / Trade-offs

- **Plugin dependency**: These actions are plugin-specific; other plugins won't have them
- **Mitigation**: Actions will only be useful when the plugin is Marvel Champions; other plugins can ignore or error
- **Naming complexity**: Some actions like `deal_boost` have implicit player context
- **Mitigation**: Follow existing patterns (e.g., `draw_card` infers player_n from destination)