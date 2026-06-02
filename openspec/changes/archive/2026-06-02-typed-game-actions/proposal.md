## Why

Agents currently have to inspect `get_session_actions` and then craft a generic `execute_action` call with a string action name and arbitrary parameters. This is verbose, error-prone, and makes action usage inconsistent across the codebase.

## What Changes

- Introduce typed, per-action helper functions in `game_actions.py` that wrap `execute_action` for each supported action.
- Add request/response models for each action helper to provide validation and better tooling support.
- Keep the existing generic action endpoints for backward compatibility.

## Capabilities

### New Capabilities
- `typed-game-actions`: Typed, per-action wrappers for DragnCards game actions with explicit request/response models.

### Modified Capabilities
- `game-service`: Expose typed action helpers alongside the existing generic action execution interface.

## Impact

- Game service action layer (`services/game-service/`) gains new helper functions and models.
- MCP tool surface becomes more ergonomic for agents, while the raw action interface remains available.
- Tests and documentation for game actions may require updates to cover the new typed helpers.
