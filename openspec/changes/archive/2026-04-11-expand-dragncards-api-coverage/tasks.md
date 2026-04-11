## 1. Session Layer — Inbound Event Handling

- [x] 1.1 Add `BadGameStateError` and `StateUnavailableError` exception classes to `session/manager.py`
- [x] 1.2 Subscribe `Channel` handler in `GameSession.__post_init__` for `bad_game_state` — set an internal `_bad_state` flag
- [x] 1.3 Subscribe `Channel` handler for `unable_to_get_state_on_join` and `unable_to_get_state_on_request` — set `_state_unavailable` flag
- [x] 1.4 Update `GameSession.get_state()` to check `_bad_state` → raise `BadGameStateError`, check `_state_unavailable` → raise `StateUnavailableError`
- [x] 1.5 Update `GameSession.execute_action()` to check both flags before and after `wait_for_event`
- [x] 1.6 Add `_alerts: deque` (maxlen=50) to `GameSession`; subscribe handler for `send_alert` → append to deque
- [x] 1.7 Add `_gui_updates: dict[str, Any]` to `GameSession`; subscribe handler for `gui_update` → store by `player_n`
- [x] 1.8 Write unit tests for `BadGameStateError` / `StateUnavailableError` flag detection (mock channel broadcasts)
- [x] 1.9 Write unit tests for alert buffer append, eviction at 50, and clear-on-read behaviour
- [x] 1.10 Write unit tests for `gui_update` storage and overwrite per `player_n`

## 2. Session Layer — Outbound Room Control Methods

- [x] 2.1 Add `GameSession.reset_game(save: bool = False, reload_plugin: bool = False)` — pushes `reset_game` or `reset_and_reload`, waits for `current_state`, returns new state
- [x] 2.2 Add `GameSession.set_seat(player_index: int, user_id: int)` — fire-and-forget push of `set_seat` with timestamp
- [x] 2.3 Add `GameSession.set_spectator(user_id: int, spectating: bool)` — fire-and-forget push of `set_spectator`
- [x] 2.4 Add `GameSession.close_room()` — pushes `close_room`, awaits ack, then calls `SessionManager.delete_session` to clean up pool entry
- [x] 2.5 Add `GameSession.send_alert(message: str)` — pushes `send_alert` with `{message}`
- [x] 2.6 Add `GameSession.save_replay()` — pushes `save_replay` with current timestamp
- [x] 2.7 Add `GameSession.get_alerts() -> list[dict]` — returns copy of `_alerts` deque
- [x] 2.8 Add `GameSession.get_gui_updates() -> dict[str, Any]` — returns copy of `_gui_updates`
- [x] 2.9 Write unit tests for each new `GameSession` method (mock `Channel.push`)

## 3. HTTP API — Models

- [x] 3.1 Add `ResetGameRequest` Pydantic model (`save: bool = False`, `reload_plugin: bool = False`) to `api/models.py`
- [x] 3.2 Add `ResetGameResponse` model (wraps `GameStateResponse`)
- [x] 3.3 Add `SetSeatRequest` model (`player_index: int`, `user_id: int`)
- [x] 3.4 Add `SetSpectatorRequest` model (`user_id: int`, `spectating: bool`)
- [x] 3.5 Add `SendAlertRequest` model (`message: str`)
- [x] 3.6 Add `AlertsResponse` model (`alerts: list[dict]`)
- [x] 3.7 Add `GuiUpdateResponse` model (`updates: dict[str, Any]`)

## 4. HTTP API — Endpoints

- [x] 4.1 Add `POST /games/{session_id}/reset` → calls `session.reset_game(...)`, returns `ResetGameResponse` (200) or 404
- [x] 4.2 Add `POST /games/{session_id}/seat` → calls `session.set_seat(...)`, returns 204 or 404
- [x] 4.3 Add `POST /games/{session_id}/spectator` → calls `session.set_spectator(...)`, returns 204 or 404
- [x] 4.4 Update `DELETE /games/{session_id}` to accept optional `?close_room=true` query param; if set, push `close_room` before pool cleanup
- [x] 4.5 Add `POST /games/{session_id}/alert` → calls `session.send_alert(...)`, returns 204 or 404
- [x] 4.6 Add `POST /games/{session_id}/replay` → calls `session.save_replay()`, returns 204 or 404
- [x] 4.7 Add `GET /games/{session_id}/alerts` → returns `AlertsResponse` or 404
- [x] 4.8 Add `GET /games/{session_id}/gui-update` → returns `GuiUpdateResponse` or 404
- [x] 4.9 Add `BadGameStateError` → HTTP 409 exception handler in `app.py`
- [x] 4.10 Add `StateUnavailableError` → HTTP 503 exception handler in `app.py`
- [x] 4.11 Write integration tests for `POST /games/{id}/reset` (unit-level with ASGI transport + mocked session)
- [x] 4.12 Write integration tests for `POST /games/{id}/seat`, `POST /games/{id}/spectator`
- [x] 4.13 Write integration tests for `POST /games/{id}/alert`, `POST /games/{id}/replay`
- [x] 4.14 Write integration tests for `GET /games/{id}/alerts` and `GET /games/{id}/gui-update`
- [x] 4.15 Write integration tests for `BadGameStateError` → 409 and `StateUnavailableError` → 503

## 5. MCP Server — New Tools

- [x] 5.1 Add `reset_game` tool to `mcp/server.py` with `session_id`, `save` (bool, default false), `reload_plugin` (bool, default false) params; returns updated state text
- [x] 5.2 Add `set_seat` tool with `session_id`, `player_index`, `user_id` params; returns confirmation text
- [x] 5.3 Add `set_spectator` tool with `session_id`, `user_id`, `spectating` params; returns confirmation text
- [x] 5.4 Add `send_alert` tool with `session_id`, `message` params; returns confirmation text
- [x] 5.5 Add `save_replay` tool with `session_id` param; returns confirmation text
- [x] 5.6 Register all new tools in `list_tools()` with JSON Schema descriptions
- [x] 5.7 Add dispatch branches for all new tools in `_dispatch_tool()`

## 6. MCP Server — New Resources

- [x] 6.1 Add `game://{session_id}/alerts` resource in `list_resources()` with MIME `application/json`
- [x] 6.2 Add `game://{session_id}/gui-update` resource in `list_resources()` with MIME `application/json`
- [x] 6.3 Implement `read_resource()` handlers for both new resources (format alerts as JSON array text, gui-updates as JSON object text)
- [x] 6.4 Write unit tests for new MCP tool dispatch (mock `GameSession` methods)
- [x] 6.5 Write unit tests for new MCP resource reads
