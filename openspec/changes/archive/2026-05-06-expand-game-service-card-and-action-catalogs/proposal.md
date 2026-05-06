## Why

The game-service exposes a useful card catalog and action catalog already, but both are incomplete for agent-driven play. Card search omits important metadata that already exists in the Marvel Champions source data, and the action catalog does not clearly separate generic DragnCards actions from plugin-specific actions and affordances.

## What Changes

- Expand the card search response for registered providers so it returns the relevant gameplay and identification fields present in the provider's base card data, not just the small subset exposed today
- Introduce a modular provider interface so new card/action catalog providers can be added with less registry and router coupling
- Split action catalog responsibilities clearly between the global `GET /actions` endpoint and per-session `GET /games/{session_id}/actions`
- Make the global action catalog describe the generic action surface supported by `@external/dragncards/`
- Make the per-session action catalog extend the global catalog with plugin-specific metadata sourced from `services/game-service/src/game_service/catalog/providers/` and plugin definitions, starting with Marvel Champions
- Add provider-driven metadata for plugin-specific actions and related affordances such as named action lists, hotkeys, touch-bar actions, player-count layouts, and curated load-group data where available
- Update HTTP models, OpenAPI output, and tests so the richer catalog responses are documented and validated end to end

## Non-goals

- Adding new action execution semantics to DragnCards or changing upstream plugin JSON formats
- Building a fully generic plugin parser for every DragnCards plugin in this change
- Replacing the existing typed action wrappers with raw DragnLang-only execution
- Changing room creation, WebSocket protocol handling, or MCP tool dispatch beyond the catalog metadata they expose

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-service`: change the card-catalog and action-catalog requirements so responses expose richer provider metadata and per-plugin action definitions

## Impact

- `services/game-service/src/game_service/catalog/providers/` — richer provider metadata extraction and plugin-specific action catalog definitions
- `services/game-service/src/game_service/catalog/providers/` — modular provider interface plus richer provider metadata extraction and plugin-specific action catalog definitions
- `services/game-service/src/game_service/catalog/providers/base.py` or equivalent — shared provider contract for new catalog integrations
- `services/game-service/src/game_service/catalog/service.py` — provider metadata plumbing for cards and action catalogs
- `services/game-service/src/game_service/api/models.py` — expanded card result and action catalog response models
- `services/game-service/src/game_service/api/routers/cards.py` — richer card search responses
- `services/game-service/src/game_service/api/routers/meta.py` — generic DragnCards action catalog behavior for `GET /actions`
- `services/game-service/src/game_service/api/routers/game_actions.py` — per-session action catalog behavior for `GET /games/{session_id}/actions`
- `services/game-service/tests/unit/test_cards_and_session_actions.py` and related tests — new expectations for expanded card fields and plugin-aware action metadata
- `external/dragncards/backend/lib/dragncards_web/controllers/api/v1/plugins_controller.ex` and plugin payload shape — upstream reference for optional plugin metadata sourcing
