## Context

The game-service currently uses only 3 of the ~11 available DragnCards room channel outbound events (`game_action`, `request_state`, heartbeat) and handles only 3 inbound events (`current_state`, `state_update`, `send_update`). The upstream `RoomChannel` exposes rich room control operations — reset, seat assignment, spectator mode, close, replay, alert — that are needed for a complete game loop. Without them, the AI cannot set up a game (assign a bot to a seat), recover from bad state, or cleanly shut down a room.

All new operations are 1:1 mappings to existing DragnCards WebSocket events. No DragnCards backend changes are required.

## Goals / Non-Goals

**Goals:**
- Map every `RoomChannel` client→server event to a `GameSession` method, HTTP endpoint, and MCP tool
- Handle inbound error events (`bad_game_state`, `unable_to_get_state_*`) as proper exceptions rather than silent timeouts
- Surface server-sent alerts (`send_alert`) and GUI update hints (`gui_update`) as observable state on the session
- Keep the HTTP API and MCP tools in strict 1:1 parity (every new session method gets both)

**Non-Goals:**
- Lobby channel (`lobby:lobby`), chat channel (`chat:*`), or LFG channel — out of scope
- DragnCards HTTP endpoints beyond the 3 already used (plugin discovery, deck loading, room CRUD) — separate change
- Replay step-through (`step_through` / `set_replay`) — useful but adds complexity around replay state management; deferred
- Streaming/SSE for live event push to HTTP clients — deferred

## Decisions

### Decision 1: New session methods on `GameSession`, not `SessionManager`

Room-control operations (`reset_game`, `set_seat`, etc.) are per-session — they push events on the session's `Channel`. Adding them as methods directly on `GameSession` keeps the session as the single owner of its channel and avoids routing through `SessionManager`.

**Alternative considered:** Add methods to `SessionManager` that look up the session and delegate. Rejected — this adds indirection with no benefit; `SessionManager` should only own the session pool lifecycle.

### Decision 2: Inbound error events raise `SessionError` subclasses

`bad_game_state`, `unable_to_get_state_on_join`, and `unable_to_get_state_on_request` will be converted to typed exceptions (`BadGameStateError`, `StateUnavailableError`) raised from the relevant `GameSession` methods. The `Channel._handle` listener sets an internal flag; `get_state()` and `execute_action()` check it after their `wait_for_event` calls.

**Alternative considered:** Return a typed error payload from the method instead of raising. Rejected — callers (HTTP handlers, MCP tools) already have exception→HTTP-status and exception→MCP-error mapping infrastructure; raising fits the existing pattern.

### Decision 3: Alerts stored as a bounded deque on `GameSession`

`send_alert` broadcasts arrive asynchronously at any time. Store the last N (default 50) alerts on `GameSession._alerts: deque[dict]` as they arrive. Expose via `GET /games/{id}/alerts` (returns the buffer) and clear-on-read semantics optional. MCP exposes `game://{session_id}/alerts` as a resource.

**Alternative considered:** Push alerts to a callback / asyncio queue that callers must drain. Rejected — complicates the API surface; a buffer readable at any time is simpler for an LLM client that polls.

### Decision 4: `gui_update` stored as latest value, not queued

GUI updates are per-player hints (e.g. "choose a target"). Store the most recent `gui_update` payload per `player_n` in a dict on `GameSession`. Expose via `GET /games/{id}/gui-update` and `game://{session_id}/gui-update` MCP resource.

**Alternative considered:** Queue all gui updates like alerts. Rejected — gui updates are edge-triggered UI hints; only the latest matters for a given player.

### Decision 5: Room-control endpoints under `/games/{id}/` not a separate router prefix

New endpoints follow the existing pattern (`/games/{id}/state`, `/games/{id}/actions`) for consistency: `/games/{id}/reset`, `/games/{id}/seat`, `/games/{id}/spectator`, `/games/{id}/close`, `/games/{id}/alerts`, `/games/{id}/gui-update`. This keeps the API grouped by session ID, matching the mental model.

**Alternative considered:** A nested `/games/{id}/room/reset` prefix. Rejected — adds a path segment with no disambiguation value since all operations are already scoped to a session.

## Risks / Trade-offs

- **`bad_game_state` is a broadcast, not a reply** — It can arrive at any time, not just in response to an action. The flag-based approach (Decision 2) means a bad-state event that arrives between two operations will only surface on the *next* operation. Mitigation: also raise immediately in any active `wait_for_event` call by checking the flag in the wait loop.
- **`set_seat` / `set_spectator` reply with bare `:ok`, not a full state** — These events do not trigger `state_update`; the DragnCards server only broadcasts `seats_changed` / `spectators_changed`. We return those payloads directly rather than waiting for a full state update, so callers must call `GET /games/{id}/state` separately if they need the full state.
- **`close_room` is destructive** — After `close_room` the server saves and tears down the room. We should auto-delete the session from the pool after a successful `close_room` push, mirroring `DELETE /games/{id}` cleanup.
- **DragnCards does not ack `set_seat` / `set_spectator`** — These handlers call `:ok` in the Elixir code (not `{:reply, :ok, socket}`), meaning no `phx_reply` comes back. We fire-and-forget for these and return `204 No Content` from HTTP.
