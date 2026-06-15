## Why

The game-service already exposes MCP tools for live card search, but there is no way for an LLM client to discover the prebuilt deck and scenario sets that ship with the Marvel Champions plugin. Adding a catalog tool lets clients inspect the available sets before deciding what to load or recommend.

## What Changes

- Add MCP tools for listing and filtering the prebuilt card set catalog sourced from `sets.json`.
- Return a normalized summary for each set with the set `id`, `name`, and `type`.
- Support basic filters so clients can narrow results by name and type.
- Update the game-service MCP tool contract so the new set catalog tools are discoverable alongside the existing card search tools.
- Keep the feature read-only; it only exposes catalog data and does not change how decks are loaded.

## Capabilities

### New Capabilities
- `prebuilt-set-catalog`: list and filter the prebuilt Marvel Champions card sets exposed from plugin data.

### Modified Capabilities
- `game-service`: extend MCP tool discovery to include the new prebuilt set catalog tools.

## Impact

- `services/game-service/` MCP tool registration and catalog logic.
- Marvel Champions plugin data ingestion for `sets.json`.
- OpenSpec requirements for the game-service MCP surface.
