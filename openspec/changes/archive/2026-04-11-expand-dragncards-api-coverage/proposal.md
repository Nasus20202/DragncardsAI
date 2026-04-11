## Why

The game-service currently maps only 3 of the DragnCards backend's available WebSocket channel events and none of the room management events (reset, seat assignment, spectator, replay, close). This means an AI agent cannot perform essential game operations like resetting a game, changing lobby size/seats, or handling server-side alerts — making it impossible to run a complete game loop end-to-end.

## What Changes

- Add WebSocket channel actions for room control: `reset_game`, `reset_and_reload`, `set_seat`, `set_spectator`, `close_room`, `send_alert`, `save_replay`
- Add inbound event handling for: `send_alert`, `bad_game_state`, `unable_to_get_state_on_join`, `unable_to_get_state_on_request`, `gui_update`
- Expose all new channel actions as HTTP REST endpoints (`POST /games/{id}/reset`, `POST /games/{id}/seat`, etc.) and MCP tools
- Expose new observable events (alerts, gui updates) via the HTTP API and MCP resources
- Add DragnLang action types for `SET_PLAYER_COUNTER`, `LOAD_DECK`, and a generic passthrough for any DragnLang list not covered by typed actions (already exists as `RawAction` — ensure parity)

## Capabilities

### New Capabilities

- `room-control`: New game-service operations mapped 1:1 to DragnCards room channel events — reset, seat assignment, spectator mode, close room, manual alert sending, replay save
- `room-events`: Inbound channel event handling for alerts, bad-state detection, gui updates, and error events (unable_to_get_state_*)

### Modified Capabilities

- `game-service`: New HTTP endpoints and MCP tools for room-control operations and room-event observation

## Impact

- `services/game-service/src/game_service/session/manager.py` — new methods on `GameSession` for each room-control action; event subscriptions for inbound events
- `services/game-service/src/game_service/session/actions.py` — no changes (room-control actions have their own models)
- `services/game-service/src/game_service/api/app.py` — new route group `room` with reset, seat, spectator, close, alert, replay endpoints
- `services/game-service/src/game_service/api/models.py` — new request/response Pydantic models for each new endpoint
- `services/game-service/src/game_service/mcp/server.py` — new MCP tools mirroring each new HTTP endpoint
- Tests: new unit tests for session methods; new integration tests for each new endpoint
